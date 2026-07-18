---
type: reference
status: draft
source:
  - legal-ai/frontend/packages/event-sourcing-core/src/saga/state-machine.ts
  - legal-ai/frontend/packages/event-sourcing-core/src/saga/saga-processor.ts
  - legal-ai/frontend/packages/event-sourcing-core/src/saga/command.ts
  - legal-ai/frontend/packages/event-sourcing-core/src/saga/saga-repository.ts
  - legal-ai/frontend/packages/event-sourcing-core/src/saga/{types,config,index}.ts
  - legal-ai/frontend/packages/event-sourcing-core/src/infra/saga/aggregate-saga-repository.ts
  - legal-ai/frontend/packages/event-sourcing-core/__test__/saga-polling.example.test.ts
---

# Saga Engine

The third orchestration construct in `@legal-ai/event-sourcing-core`, alongside
the [[event-sourcing-core|suspended-workflow engine]] and plain outbox
listeners. A **MassTransit-inspired, declarative state machine** for
correlated, event-driven processes: each incoming domain event is routed by a
correlation id to a persistent saga instance, run through a
`current state × event → actions + target state` transition table, and its
state changes plus any published events are committed atomically via the
[[outbox-runtime|transactional outbox]].

> **Production status (observed):** the saga engine is **built and tested but
> not wired into any service.** `grep` for `SagaStateMachine` / `SagaProcessor`
> / `registerSaga` across the monorepo finds hits only inside
> `event-sourcing-core` itself (`src/`, `dist/`) and its `__test__/*` examples
> (`saga.spec`, `saga-polling.example`, `saga-command.example`,
> `end-to-end-saga.integration`). **nogai's `src/services` uses zero sagas.**
> The workflow engine, by contrast, is used in production. Treat this doc as the
> map of an available-but-dormant capability.

## How a saga is declared (the DSL)

Subclass `SagaStateMachine<TState, TEvent>` (`state-machine.ts`). States and
events are declared as class fields; transitions are registered in the
constructor with a MassTransit-style fluent DSL. Observed shape:

```ts
class OrderStateMachine extends SagaStateMachine<OrderState, OrderEvents> {
  public readonly Pending = this.State("Pending");
  public readonly Paid = this.State("Paid");
  public readonly OrderPlaced = this.Event<"OrderPlaced">("OrderPlaced");

  constructor() {
    super({
      name: "order-saga",
      correlationProperty: { propertyPath: "orderId" },   // event.data.orderId
      createInitialState: () => ({ orderId: "", total: 0 }),
    });
    this.Initially(                                        // from "Initial" state
      this.When(this.OrderPlaced)
        .Then(ctx => { ctx.instance.state.orderId = ctx.event.data.orderId; })
        .TransitionTo(this.Pending));
    this.During(this.Pending,
      this.When(this.PaymentReceived).Then(...).TransitionTo(this.Paid));
  }
}
```

- `Initially(...)` registers transitions from the reserved `Initial` state;
  `During(state, ...)` from a named state (`SpecialStates` = `Initial`, `Final`).
- Fluent verbs on the event-activity builder (`types.ts`): `.Then(action)`
  (mutate `ctx.instance.state` / run side effects), `.Publish(factory)` (emit a
  domain event), `.ExecuteCommand(cmd, inputFactory)` (resilient command, below),
  `.TransitionTo(state)` (terminates the chain; omit target to stay put).
- `process(instance, event)` (`state-machine.ts`) looks up
  `states[currentState].transitions[event.type]`; **no transition ⇒ event
  silently ignored** (no-op, not an error). Actions run in order, then the state
  advances. Reaching `Final` marks the saga complete.
- Correlation: `extractCorrelationId(event)` reads `event.data[propertyPath]`.
  **One correlation property per saga**, a flat string field on every handled
  event's `data`. Missing/non-string ⇒ event skipped with a warning.

## The processor: riding the outbox

`SagaProcessor` (`saga-processor.ts`) is an `EventListenerModule` — the same
registration surface as any outbox listener (see [[event-driven-communication]]).
On `register(registrar)` it walks every state's transitions, collects the union
of handled event types, and calls `registrar.on(eventType, handler,
"saga:{name}:{eventType}")` for each, **plus** one handler for
`saga.{name}:system.interval.tick` (polling — see [[interval-scheduling]]).

Per event (`processSagaWithEvent`):

1. `extractCorrelationId(event)` → `repository.load(correlationId)`.
2. No instance + `autoStartInstances` (default `true`) ⇒ `createInstance`
   (a *new* saga in `Initial`). `autoStartInstances: false` ⇒ skip. **Interval
   ticks never auto-create** — a tick for an unknown instance is dropped.
3. `stateMachine.process(instance, event)` → `{ stateChanged, publishedEvents }`.
4. `repository.append(previous, updated, triggeredBy, publishedEvents)`.
5. Completion (`Final`) increments metrics.

Because the processor is a listener module, the outbox's at-least-once delivery,
per-aggregate ordering, in-process retry, and DLQ ([[outbox-runtime]]) all apply
unchanged. **Saga handlers must be idempotent** for the same reasons workflow
operations must be.

## State persistence (event-sourced, transactional outbox)

`AggregateSagaRepository` (`infra/saga/aggregate-saga-repository.ts`) stores each
saga instance as an aggregate: `aggregateId = correlationId`,
`aggregateType = "saga.{name}"`, `state = SagaInstance<TState>`. `append` builds
one event list and persists it in a **single `appendEvents` transaction**:

- framework lifecycle events — `saga.instance.started` / `saga.state.transitioned`
  / `saga.instance.completed` (`SagaStateEvent`, `saga-repository.ts`) — which
  `applySagaEvent` folds into `SagaInstance` state; **plus**
- the saga's `publishedEvents` (arbitrary domain events), appended **before** the
  transition event, passed through `applySagaEvent` **unchanged** (they don't
  affect saga state — they are pure outbox payload for downstream consumers).

The call uses **`{ allowMixedAggregateTypes: true }`** — the one place that flag
matters. Normally `appendEvents` asserts every event's type-prefix matches the
aggregate type ([[event-sourcing-core]]); a saga deliberately writes
`saga.order-saga:...` lifecycle events *and* `payment:PaymentRequested` domain
events into the same `saga.order-saga` stream, so the guard is disabled. This is
exactly the transactional-outbox guarantee: **saga state advance and the events
it emits commit or roll back together**, and the returned `version` reflects the
total row count (used as the optimistic-lock `expectedVersion` next time).
Concurrent ticks on one instance conflict on `UNIQUE(type,id,version)` and one
retries — ticks are serialized per instance, same as workflows.

`InMemorySagaRepository` is the test double.

## Compensation / rollback semantics

Compensation lives **entirely in the command layer** (`command.ts`), reached via
`.ExecuteCommand(...)`, and is **in-process, not durable/event-sourced**:

- A `SagaCommand<TInput,TOutput>` has `execute()`, optional `timeout`,
  `retryPolicy`. `CommandExecutor.execute` adds exponential backoff retry, a
  `Promise.race` timeout, and an **implicit circuit breaker** keyed by command
  name (opens after `maxAttempts` failures).
- A `CompensatableCommand` additionally carries a `CompensatingCommand` with
  `compensate(output)`. On each success `CompensationCoordinator.recordExecution`
  pushes `{ compensation, output }` onto an in-memory history. On a **later**
  command failure, `compensateAll()` runs the recorded compensations in **reverse
  (LIFO) order**, best-effort (continues past individual failures, then throws an
  aggregate), and re-throws the original error.

**Limits (observed):** the coordinator's history is a plain in-memory array on
the state-machine singleton — it is **not persisted** and **not scoped per saga
instance**. Compensation therefore only covers commands executed *within a single
synchronous transition*; it does **not** survive a process restart, and there is
no saga-wide "undo everything done across many events" rollback. For durable
cross-step rollback you must model compensating actions as explicit states/events
yourself. This is the classic saga distinction: **there are no distributed
transactions — only forward recovery via compensating actions**, and here the
built-in coordinator is a convenience for intra-transition command chains.

## Polling sagas (interval ticks)

A saga polls by emitting `saga.{name}:system.interval.schedule` (via `.Publish`)
and handling `saga.{name}:system.interval.tick`. The
[[interval-scheduling|interval substrate]] wakes only the specific instance
(routed by `metadata.aggregate.id`); the saga re-checks external state on each
tick and emits `system.interval.cancel` when done. The
`saga-polling.example.test.ts` (payment gateway without webhooks) is the
reference pattern. Mechanically identical to how workflow `ctx.until` rides the
same substrate.

## Choosing an orchestration construct

| Need | Reach for |
| --- | --- |
| Single guarded state change on one entity | plain aggregate + `appendEvents` ([[event-sourcing-core]]) |
| React to one service's event; no long-lived process state | **listener module** ([[event-driven-communication]]) |
| Strongly-consistent read model | `appendEvents` + `onCommit` |
| Eventually-consistent read model | event-processor projection |
| Correlated **state machine** over events — status matters, transitions are the domain, mostly reactive (react to events, maybe poll) | **saga** (`SagaStateMachine` + `SagaProcessor`) — *if you accept it's unproven in prod here* |
| Multi-step process written as **imperative code** — call durable operations, `await` external events, poll, must survive restart mid-flight | **suspended workflow** (`Suspended.program` + `WorkflowExecutor`) — the production choice |
| Query orchestration status/progress | `WorkflowProjection` + `WorkflowQuery` |

### Saga vs. suspended workflow (the real decision)

Both are durable, event-sourced, ride the outbox + interval substrate, serialize
via optimistic lock, and demand idempotent effects. They differ in **authoring
model** and **maturity**:

- **Saga** = explicit `state × event` transition table. Natural when the process
  is genuinely a state machine, is driven by many *inbound* event types from
  other services, and the current state is itself meaningful domain data. The
  logic is spread across transition handlers.
- **Suspended workflow** = one imperative `async` function that reads top-to-
  bottom; suspension points (`ctx.call` / `ctx.awaitEvent` / `ctx.until`) are
  replayed on each tick. Natural when the process is a *procedure* with a clear
  happy path and ordering. Compensation is expressed as ordinary code after a
  caught error.
- **Maturity:** the workflow engine is **used in production**; the saga engine is
  **present and tested but unused**. Absent a specific state-machine fit, prefer
  the workflow engine — it is the trodden path in this codebase.
- **Compensation:** workflows compensate via imperative code you control and that
  replays durably; the saga's `CompensationCoordinator` is in-memory and
  intra-transition only. For durable multi-step rollback neither gives it for
  free — you model it — but the workflow's imperative style makes it more natural.

*Inferred* guidance (the codebase gives no in-repo saga precedent to copy):
reach for a saga only when a problem is unmistakably a reactive multi-event
state machine; otherwise use a workflow.
