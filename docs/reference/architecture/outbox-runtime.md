---
type: reference
status: draft
source:
  - legal-ai/frontend/outbox_processor/src/index.ts
  - legal-ai/frontend/nogai/src/di/infrastructure-provider.ts
  - legal-ai/frontend/packages/event-sourcing-core/src/processor.ts
  - legal-ai/frontend/packages/event-sourcing-core/src/infra/postgres-processor.ts
  - legal-ai/frontend/packages/event-sourcing-core/src/infra/schemas/{aggregates,processor,deadletter}.ts
  - legal-ai/frontend/packages/event-sourcing-core/src/{deadletter,dead-letter-reprocessor,retry-policy}.ts
  - legal-ai/frontend/packages/event-sourcing-core/src/eventbus.ts
---

# Outbox Processor Runtime

How the outbox worker actually runs. This is the runtime companion to
[[event-driven-communication]], which covered *what* services publish and *how*
listeners subscribe. Here: the deployable that polls the outbox and delivers
those events, its delivery guarantees, and its DLQ. Don't re-read that doc for
the listener/`.on()` API.

## The deployable

`outbox_processor/` is a **separate Node process** (not the API server). Entry:
`outbox_processor/src/index.ts`. It imports OTel instrumentation first, builds
one `ApplicationContainer` (the same nogai DI graph, resolving DB + service
deps), then pulls ~16 named processors off it and calls `.start()` on all of
them in one `Promise.all`. It exposes an HTTP server on **:9615** with
`/health` (per-processor `getStatus()`) and `/metrics` (Prometheus via
`prom-client`). Build is esbuild → `dist/index.cjs`, run via `node`.

**Observed:** there is *no* `getAllProcessors()` — index.ts enumerates each
`container.getXProcessor()` explicitly (storage, ocr, summarization,
substantiation executor+projection, conversation, message, compliance-review
executor+projection, documentSearch, name-generation, research-artefact-search,
message-search, knowledge-graph, + s3-cleanup variants). A code comment flags
the current shape as provisional: *"each deployment should run its own
processor, to make consumption of events independent"* — today it is **one
process running all groups**.

## The outbox table (schema)

One unified table backs event-sourcing *and* the outbox
(`infra/schemas/aggregates.ts`), `es_aggregate_events`:

- `id bigint GENERATED ALWAYS AS IDENTITY` — monotonic, the **cursor axis**.
- `aggregate_id`, `aggregate_type`, `aggregate_state jsonb` (snapshot per row),
  `event_type`, `event_data jsonb`, `event_metadata jsonb`, `version int`,
  `created_at`.
- `UNIQUE(aggregate_type, aggregate_id, version)` — ordering integrity +
  optimistic lock (see [[event-sourcing-core]]).
- Index `(event_type, id)` — serves the processor's filtered cursor scan.

Cursors live in `es_processor_groups` (`name UNIQUE`, `start_position`,
`last_processed_id bigint`). DLQ lives in `es_dead_letter_queue`.

## Polling model (observed)

`PostgresProcessorRepository.getUnprocessedEvents` is the whole read path:

```sql
SELECT ... FROM es_aggregate_events
WHERE id > :lastProcessedId AND event_type IN (:subscribedTypes)
ORDER BY id LIMIT :batchSize
```

- **Cursor-based, NOT `SKIP LOCKED`.** There is no row locking, no advisory
  lock, no lease. Each group is a single logical consumer tracked by
  `last_processed_id`. `event_type IN (...)` is built from the types the group's
  listeners registered via `.on()`, so a group only scans its own events.
- **Poll loop** (`EventProcessor.start` → `loop`): `processOnce()` then
  `setTimeout(loop, pollIntervalMs)`. Default `pollIntervalMs: 500`,
  `batchSize: 100`, `concurrency: 10` (`processor.ts` constructor).
- **Batch dispatch** (`processOnce`): events are grouped by `aggregateId`.
  Different aggregates run **concurrently** (up to `concurrency`); events within
  one aggregate run **strictly sequentially** (preserves per-aggregate order).
- **Cursor advance is contiguous-only** (`findMaxContiguousId`): the cursor
  moves to the highest *gap-free* successfully-processed id. A failed event in
  the middle stops the cursor there so the whole tail is retried next poll. A
  gap *at the start* (missing lower ids) is logged + a metric incremented, then
  skipped.

### Scaling caveat (observed, from README)

One instance **per processor-group name**. Two instances of the same group both
read the same cursor and the same batch → **listeners run twice**. The cursor is
for single-instance crash recovery, not multi-instance coordination. Horizontal
scaling would need `SKIP LOCKED` / advisory locks / optimistic cursor CAS —
explicitly *not implemented*. Scale by splitting event types into distinct
group names, not by replicating a group.

## Delivery guarantees & retry/backoff

**At-least-once.** An event is redelivered on crash (cursor not yet advanced) or
on transient listener failure. Production config comes from
`infrastructure-provider.ts::createBaseOutboxProcessor` — every nogai processor
is built on it:

```ts
errorHandling: { mode: "deadletter", maxRetries: 3,
                 backoff: { initialDelayMs: 10, maxDelayMs: 900000 },
                 deadLetterRepo: this.deadLetterRepo },
intervalScheduling: { intervalCheckMs: 1000, intervalScheduleRepo },
```

Retry is **per-event, inside `EventBus.dispatch`** (`eventbus.ts`), not a
requeue: a `while (attempt <= maxRetries)` loop re-runs the failed listeners,
sleeping `calculateBackoffDelay(attempt, backoff)` between attempts (exponential
× 2.0, ±10% jitter, capped at `maxDelayMs`; attempt 0 is immediate). Because the
sleep is in-process, retries **block that group's poll loop** for their
duration — a poison event with 900s backoff stalls its group. All listeners for
the event run together (parallel `allSettled`); only failed ones are retried.

**Error-handling modes** (`ErrorHandlingMode`, `processor.ts`):
- `strict-no-error` (library default) — stop the whole processor on any failure.
- `skip-on-error` — after retry exhaustion, log + skip, advance cursor.
- `deadletter` (nogai's choice) — after retry exhaustion, write to DLQ, continue.

**`NonRetryableError`** (`errors.ts`) thrown by a listener short-circuits the
retry loop → straight to DLQ. Encoded in the DLQ `retryCount` as a **negative**
value (`-(attempt+1)`); positive/zero means exhausted transient retries. Helpers
`isNonRetryableDlqEntry` / `getAttemptFromDlqRetryCount` decode it.

## Dead-letter queue

On retry exhaustion, `handleEventFailure` calls
`deadLetterRepo.addToDeadLetter(...)` capturing `eventId`, `processorGroupName`,
`eventListenerName` (the stable `.on()` handler id), aggregate + event type,
error message/stack, `retryCount`, and a **full copy** of `originalEventData` /
`originalEventMetadata` (so replay needs no join back to the source row). Table
`es_dead_letter_queue` indexes by processor group, aggregate, `failed_at`, and a
replay-ordering index `(dlq_replay_count, created_at)` plus a partial index
`WHERE retry_count >= 0` for the retryable filter.

### Reprocessing

`DeadLetterReprocessor` (`dead-letter-reprocessor.ts`) replays DLQ rows through
**the same `EventListenerModule`s** the live processor uses (guaranteeing
identical handling). Constructed via `createBaseDeadLetterReprocessor`, keyed by
matching `processorGroupName`. Modes: one-shot (`replayAll`, `replayById`,
`replayByAggregateType`, `replayByEventType`) or background `start()/stop()`
polling (default `pollIntervalMs: 30_000`, `batchSize: 50`). Success →
`removeFromDeadLetter`; failure → increment `dlq_replay_count` + record error.
Bulk replay **excludes** entries past `maxDlqRetries` (default 10) and
NonRetryable (negative `retryCount`) entries — ordered least-replayed-first so
poison messages don't starve fresh ones. `replayById` is the manual escape hatch
that ignores those exclusions.

**Observed deployment detail:** index.ts wires two DLQ reprocessors
(research-artefact-search, message-search) as **temporary, time-boxed** — a
`DLQ_CUTOFF = 2026-02-26` after which a `setTimeout` calls `.stop()`. These are
one-off backfill/recovery jobs, not permanent infrastructure.

## Idempotency contract (what consumers MUST uphold)

At-least-once + in-process retry + the possibility of duplicate delivery means
**every listener must be idempotent**. Observed disciplines (see
[[event-driven-communication]] for the consumer-side patterns):
- Re-query current state and bail if the effect already happened (name-gen
  checks `name !== null`; index listeners re-check the file exists).
- Use natural upserts (`onConflictDoNothing`) keyed by aggregate/event id.
- Return (log-and-skip) on expected/non-retryable conditions to avoid DLQ
  pollution; only *throw* on genuinely retryable failures.

## Graceful shutdown

`EventProcessor.stop()`: flips `isRunning=false`, clears the poll + interval
timers, and **awaits any in-flight `processOnce()` and interval check** before
returning — no batch is abandoned mid-flight. (Observed: index.ts installs no
SIGTERM handler wiring `stop()`; shutdown of the whole process relies on the
container/runtime. The `stop()` machinery exists and is used by the DLQ cutoff
`setTimeout`.)

## Also on this processor: interval scheduling

The same `EventProcessor` runs a second timer (`intervalCheckMs: 1000`) that
polls `es_interval_schedules` for due/expired schedules and emits
`aggregate:system.interval.tick` / `.expired` events. Registering a
`:system.interval.tick` listener auto-subscribes the group to the
schedule/cancel/expired lifecycle. This is the substrate the suspended-workflow
poll/timeout engine rides on — see [[event-sourcing-core]].
