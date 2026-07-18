---
type: reference
status: draft
source:
  - legal-ai/frontend/packages/event-sourcing-core/src/interval-schedule-repository.ts
  - legal-ai/frontend/packages/event-sourcing-core/src/infra/postgres-interval-schedule.ts
  - legal-ai/frontend/packages/event-sourcing-core/src/infra/schemas/interval-schedule.ts
  - legal-ai/frontend/packages/event-sourcing-core/src/processor.ts
  - legal-ai/frontend/packages/event-sourcing-core/src/suspended/executor.ts
---

# Interval-Scheduling Substrate

The generic timer service inside `@legal-ai/event-sourcing-core` that turns
"wake this aggregate up every N ms until deadline" into durable, crash-resilient
outbox events. It is the substrate under **workflow** `ctx.until` / `awaitEvent`
timeouts ([[event-sourcing-core]]) and **saga** polling ([[saga-engine]]).
Lives *on the same `EventProcessor`* that runs the outbox
([[outbox-runtime]]) — a second timer beside the poll loop, enabled by the
`intervalScheduling` config (nogai sets `intervalCheckMs: 1000`).

## The table: `es_interval_schedules`

`infra/schemas/interval-schedule.ts`. **Composite primary key**
`(processor_group_name, aggregate_type, aggregate_id, schedule_id)` — a schedule
belongs to one aggregate instance *and* one processor group (isolation: each
group ticks only its own rows). Columns (all times ms-epoch `bigint`):

- `interval_ms` — cadence; `start_at` — first-fire time; `expires_at` (nullable,
  `null` = never) — deadline; `last_tick_at` (nullable) — cursor for "due".
- `trace_context jsonb`, `correlation_id` — carried onto emitted events for
  distributed tracing and workflow/saga routing.
- Indexes on `expires_at`, `(aggregate_type, aggregate_id)`, `last_tick_at`,
  `start_at`, `processor_group_name`, and a partial
  `(processor_group_name, expires_at) WHERE expires_at IS NOT NULL`.

`IntervalScheduleInputSchema` (Zod) enforces `intervalMs ∈ [100ms, 24h]`,
`expiresAt` in the future and `> startAt`. `PostgresIntervalScheduleRepository`
implements the repo; `InMemoryIntervalScheduleRepository` is the test double.

## Lifecycle: schedule → tick → expired

Five framework event types flow, all prefixed with an aggregate type, e.g.
`ocr.job:system.interval.schedule`. Note the **asymmetry in durability**:

**schedule / cancel — durable, ride the outbox.** A producer (workflow executor,
saga) emits `…:system.interval.schedule` / `…:system.interval.cancel` via
`appendEvents` — they land in `es_aggregate_events` like any event. The
processor's `processSingleEvent` (`processor.ts`) intercepts them *by name*
(`extractEventName`), routes to `handleScheduleEvent` / `handleCancelEvent`
**internally instead of dispatching to user listeners**, and upserts/deletes the
`es_interval_schedules` row. So the *intent* to schedule is as durable and
at-least-once as any outbox event.

**tick / expired — ephemeral, in-process.** The interval checker
(`startIntervalChecker`, a `setTimeout(check, intervalCheckMs)` loop) runs
`checkAndEmitDueIntervals` every `intervalCheckMs`:

1. `checkAndEmitExpiredSchedules(now)` first — `getExpiredSchedules` (rows with
   `expires_at <= now`) → emit `…:system.interval.expired` → `deleteExpired`.
2. `getDueSchedules(now)` — rows where started, not expired, and
   (`last_tick_at IS NULL` **or** `last_tick_at + interval_ms <= now`) → emit
   `…:system.interval.tick` for each → `batchUpdateLastTick(keys, now)`.

Both `emitIntervalTickEvent` / `emitIntervalExpiredEvent` call
**`eventBus.dispatch(event)` directly** — the tick/expired events are **not
written to the outbox**. They are delivered in-process to whichever listener the
consumer registered (`…:system.interval.tick`). Registering a tick listener
**auto-subscribes** the group to that aggregate's `schedule`/`cancel`/`expired`
events (`autoSubscribeIntervalEvents`).

## How workflows and sagas ride it

- **Workflow** (`suspended/executor.ts`): `ctx.until` / `ctx.awaitEvent(timeout)`
  cause `tick()` to emit `workflow.poll-started` / `workflow.event-awaited`; the
  executor turns those into `system.interval.schedule` (via `appendEvents`, with
  `expiresAt = now + timeout_s + one-interval buffer`). Each `system.interval.tick`
  re-ticks the workflow to re-evaluate the condition; `poll-completed` /
  `event-timeout` emit `system.interval.cancel`. `correlationId` on the schedule
  routes ticks back to the right instance.
- **Saga** ([[saga-engine]]): emits `saga.{name}:system.interval.schedule` and
  handles `saga.{name}:system.interval.tick`, routing by
  `metadata.aggregate.id`. Ticks **never auto-create** an instance.

## Delivery guarantees (observed)

- **Schedules are durable.** The row survives restarts; `setupIntervalScheduling`
  on `start()` calls `getActiveSchedules` and (lazily) restarts the checker if
  any exist. `register` is **idempotent** on the composite key: identical params
  → no-op; changed params → logged warn + UPDATE.
- **Ticks are best-effort, not exactly-once.** They are dispatched in-process and
  not persisted; if the process dies mid-cycle a tick is simply missed — but
  because `last_tick_at` is only advanced *after* the batch dispatches, the same
  schedule is **re-evaluated next cycle** and fires again. Consumers therefore
  get **at-least-once, roughly-periodic** wake-ups, never a precise timer.
  Downstream effects must be idempotent / edge-checked (workflows re-derive
  state from recorded operations; sagas re-check external status).
- **Cadence is `intervalCheckMs`-granular** (1s in nogai) and drifts under load —
  a schedule fires no sooner than its `interval_ms` but may be late.
- **Replay self-heals.** If a replayed `schedule` event is already past
  `expiresAt`, `handleScheduleEvent` emits `expired` immediately and cancels the
  row, so no stale schedule lingers and the consumer's state machine is notified.
- **Single-consumer, per group.** Like the outbox cursor, the checker assumes one
  processor instance per group name; the `processor_group_name` key isolates
  groups but does **not** coordinate replicas of the same group
  ([[outbox-runtime]]). Two instances of one group would double-tick.
- **Cancel/expire cleanup is non-transactional across chunks** — partial deletes
  are re-picked-up on the next cycle by design.

## Production status

**In use.** Unlike the saga engine, this substrate is live: it is enabled on
nogai's base outbox processor and is the timeout/polling engine for the
production suspended-workflow runtime. Standalone use (scheduling ticks directly
without a workflow or saga) is supported by the API but not observed in
`nogai/src/services`.
