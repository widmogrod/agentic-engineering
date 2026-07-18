---
type: reference
status: draft
source:
  - legal-ai/frontend/packages/event-sourcing-core/src/aggregate.ts
  - legal-ai/frontend/packages/event-sourcing-core/src/infra/postgres-aggregate.ts
  - legal-ai/frontend/packages/event-sourcing-core/src/infra/schemas/aggregates.ts
  - legal-ai/frontend/packages/event-sourcing-core/src/suspended/{workflow,executor,suspension,context,state}.ts
  - legal-ai/frontend/packages/event-sourcing-core/src/suspended/projection/*
  - legal-ai/frontend/packages/event-sourcing-core/README.md
---

# event-sourcing-core: the substrate

Internals of `@legal-ai/event-sourcing-core` — the generic machinery services
build on. The outbox *runtime* that consumes what this produces is
[[outbox-runtime]]; the cross-service event contract is
[[event-driven-communication]]. This doc: the aggregate/decider model, the
optimistic-lock protocol, projection storage, and the suspended-workflow engine
— and **when to reach for each**.

## Aggregate / decider model

An aggregate is `{ id, type, state, version }` (`AggregateEntity`, `aggregate.ts`).
State is folded from events by a **pure reducer** supplied per call — the
`applyEvent(state, event) => state` "decider". The library owns persistence;
the service owns only its `TState`, its event union, and `applyEvent`.

`AggregateRepository<TState, TEvent>` (interface, `aggregate.ts`):
- `appendEvents(id, type, expectedVersion, events, applyEvent, options?)`
  → `{ version, finalState }`, throws `OptimisticLockError`.
- `load(type, id)` — reads the **latest row's snapshot** (fast, no replay).
- `loadFromHistory(type, id, applyEvent)` — replays all events from scratch.
- `loadWithHistory(type, id)` — state + full event array.
- `listEvents({ aggregateTypes?, afterId?, limit? })` — cursor scan (also what
  the outbox reads).

**Key design (observed):** every row in `es_aggregate_events` stores *both* the
event *and* the resulting `aggregate_state` snapshot. So `load()` is a single
`ORDER BY version DESC LIMIT 1` — no replay on the hot path. Replay
(`loadFromHistory`) exists for rebuild/audit only.

## Optimistic-locking protocol (appendEvents)

`PostgresAggregateRepository.appendEvents` (`infra/postgres-aggregate.ts`) runs
one DB transaction:

1. Validate each event's `type` shape; unless `allowMixedAggregateTypes`, assert
   every event's aggregate-type prefix matches `aggregateType`.
2. `load()` current state inside the tx; set `version = expectedVersion`.
3. For each event: `version++`, `state = applyEvent(state, event)`, enrich
   metadata with OTel trace context, `INSERT` the row at that `version`.
4. **The lock is the DB, not a read-check.** Concurrent appenders both compute
   the same next `version`; the `UNIQUE(aggregate_type, aggregate_id, version)`
   constraint makes the loser's INSERT fail with PG code `23505` on constraint
   `es_aggregate_events_type_id_version_unique`. That is caught, re-`load()`ed
   for the actual version, and rethrown as `OptimisticLockError(id, expected,
   actual)`. (Observed: the current version is read *only* on conflict, for the
   error message — the happy path never does a compare-and-set read.)

### `onCommit` — synchronous projections in the same tx

`AppendEventsOptions.onCommit(ctx)` runs **inside the append transaction** after
the inserts, receiving `{ state, aggregateType, aggregateId, version, writer }`.
`writer.execute(tx => ...)` performs additional writes (projection upserts) on
the *same* transaction handle, so **events + read-model commit or roll back
together** — strong consistency. A throw in `onCommit` rolls back the events too.
Intended for critical read models only; keep it to simple upserts (README: "keep
fast — avoid queries/external calls"). Everything else should be an
eventually-consistent projection updated by an outbox processor.

## Projection storage

Two flavors (README "Synchronous vs Workflow Projection"):
- **Synchronous** — via `onCommit`, strong consistency, hand-written SQL, blocks
  the commit. Use for account-balance-grade invariants.
- **Async/event-processor** — a listener module updates a read model off the
  outbox; eventually consistent, non-blocking. Default choice.

The workflow subsystem ships a ready-made async one: `WorkflowProjection` +
`ProjectionStorage` (`Postgres`/`InMemory`), backed by `workflowInstancesTable`.
It listens for `workflow.state-changed` and upserts one row per instance
(O(1) write, no aggregate load), queryable via a fluent `WorkflowQuery`
(`.whereStatus`, `.whereUserAttribute`, `.whereCorrelationId`,
`.whereExecutionProgress`, `orderBy/limit/offset`). A `userAttributesExtractor`
projects domain fields you want to filter on. Optional `trackExecutionProgress`
records which operation each running workflow is currently in.

## Suspended-workflow engine

A **durable, event-sourced workflow runtime** layered on the aggregate model.
Use it when a process spans multiple async steps, external events, or timed
polling and must survive process restarts mid-flight — *not* for a single
state transition (use a plain aggregate + listener for that).

### The pieces

- **`Suspended.program(name, program, config)`** (`workflow.ts`) → a
  `WorkflowDefinition`. `program` is an `async (input, ctx) => output` written in
  ordinary imperative style.
- **`ctx`** (`WorkflowContext`, `context.ts`) offers three suspending calls:
  - `ctx.call(fn, ...args)` — run a durable operation (memoized by a
    deterministic `operationId = sha256(fn.name + serialized args)`).
  - `ctx.awaitEvent(type, timeout_s?)` — pause until an external domain event
    correlates in.
  - `ctx.until(cond, { timeout_s, every_s })` — poll a condition on an interval.
- **`SUSPENSION_SYMBOL` / `Suspension`** (`suspension.ts`) — the algebraic-effect
  trick. Each suspending call **throws** a `Suspension` carrying its `Operation`.
  `isSuspension(err)` (symbol check) lets `tick()` distinguish a *pause* from a
  real error. This is why a workflow body reads as straight-line code but is
  actually re-entrant: each `tick()` re-runs the program from the top, replays
  already-completed operations from recorded state, and re-throws at the first
  not-yet-done step.
- **`WorkflowInstance.tick()`** (`workflow.ts`) — one step. Runs the program;
  on `Suspension` emits the right lifecycle event
  (`operation-scheduled`/`poll-started`/`event-awaited`, or `...-completed`);
  on return emits `workflow.completed`; on real throw `workflow.failed`. Always
  appends a `workflow.state-changed`. It **emits events; it does not execute
  side effects or persist** — that's the executor.
- **`WorkflowExecutor`** (`executor.ts`) — an `EventListenerModule` that drives
  the loop. It registers on the workflow's lifecycle events and on
  `system.interval.tick`, and on each: `load()` the aggregate, `fromState().
  tick()`, `appendEvents(...)`. So **progress is itself outbox events** — the
  processor re-invokes the executor, which ticks again, until completion.
  `operation-scheduled` is the one tick that actually invokes the user's
  operation fn; its result is recorded as `operation-completed` and the next
  tick consumes it.

### How suspension maps to the runtime

- `ctx.until` / `awaitEvent` timeouts ride the **interval-scheduling** substrate
  described in [[outbox-runtime]]: the executor emits `system.interval.schedule`;
  the processor's interval checker emits `.tick`/`.expired`; the executor ticks
  the workflow to re-evaluate or time out, then emits `system.interval.cancel`.
- `awaitEvent` correlation: `WorkflowDefinition` statically extracts awaited
  event types from the program source (`extractAwaitedEvents`) and builds a
  correlation map; the executor dynamically subscribes to those external event
  types and, on arrival, emits `workflow.event-received` for the matching
  workflow ids (`handleExternalEvent`). `awaitId = hash(eventType)` — **one await
  per event type per workflow** is the current limit (documented in-code).

### Guarantees & the idempotency rule

- **Optimistic-lock serialization:** all ticks for a workflow go through
  `appendEvents` on the same aggregate, so concurrent ticks conflict and one
  retries — ticks are effectively serialized. Late events on a finished workflow
  are guarded (`status !== "running"` → no-op).
- **Operations run BEFORE the lock check and may re-run** (retry / replay /
  lock-conflict). README's ⭐ rule: **make every `ctx.call` operation idempotent
  using `ctx.getCorrelationId()`** as the idempotency key (dedupe row, or
  `Idempotency-Key` header to external APIs). The engine gives durable
  *orchestration*, not exactly-once *execution*.
- **Serializability:** `ctx.call` args must be JSON-serializable
  (`validateSerializable` throws `SerializationError` on Dates, class instances,
  functions) because the `operationId` and replay depend on deterministic
  serialization. Pass IDs, not objects.

## Choosing a construct

| Need | Reach for |
| --- | --- |
| Single guarded state change on one entity | plain aggregate + `appendEvents` |
| React to another service's event | listener module ([[event-driven-communication]]) |
| Read model, strong consistency | `appendEvents` + `onCommit` (sync projection) |
| Read model, scalable / eventual | event-processor projection |
| Multi-step process, external events, timed polling, restart-safe | suspended workflow (`Suspended.program` + `WorkflowExecutor`) |
| Query workflow status/progress | `WorkflowProjection` + `WorkflowQuery` |
