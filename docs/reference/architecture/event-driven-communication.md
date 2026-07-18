---
type: reference
status: draft
source:
  - legal-ai/frontend/nogai/src/services/shared-events.ts
  - legal-ai/frontend/nogai/src/services/*/application/*listeners*.ts
  - legal-ai/frontend/nogai/src/services/*/domain/events.ts
  - legal-ai/frontend/packages/event-sourcing-core
---

# Event-Driven Cross-Service Communication

Services in `nogai` do not call each other's write paths directly. A service
mutates only its own aggregate; **other services react** to the resulting domain
events. This keeps each service's dependency graph acyclic (enforced by the
`beFreeOfCycles` architecture test) and gives at-least-once, retryable,
dead-letter-backed cross-service side effects.

There are two distinct channels — don't conflate them:

1. **Direct query calls** (synchronous, read-only). A service may call another
   service's `Query` to enrich data — e.g. `DocumentSearchService` calls
   `StorageService.Query` to attach file metadata. These are injected as narrowed
   `Pick<Service, "Query">` deps, never as full services. This is a read
   dependency, not event flow.
2. **Event listeners** (asynchronous, write side effects). The subject of this
   doc.

## `shared-events.ts` — the typed event bus contract

`src/services/shared-events.ts` (39 lines) declares one union:

```ts
export type SharedDomainEvent =
  | ConversationEvent | FeedbackEvent | KnowledgeGraphEvent | MessageEvent
  | OcrEvent | ResearchArtefactEvent | StorageEvent | SummarizationEvent
  | WorkflowEvent;   // from @legal-ai/event-sourcing-core
```

Each arm is that service's `domain/events.ts` `DomainEvent` union, re-aliased.
The whole event bus, every `EventProcessor` and every `EventListenerModule` is
parameterized by `SharedDomainEvent`, which buys:

- compile-time exhaustiveness — a handler's event is narrowed by tag via
  `Extract<SharedDomainEvent, { type: "message:sent" }>`;
- autocomplete of event types and payload fields across service boundaries;
- refactor safety — renaming a payload field breaks consumers at compile time.

Adding a service that emits cross-service events means adding one arm here.
Purely internal services (waitlist, user's CRUD) are absent — they emit nothing
others consume.

## Event shape (per-service `domain/events.ts`)

A discriminated union, tag = `"<namespace>:<past-tense>"` or
`"<namespace>.<entity>:<event>"`:

```ts
export type DomainEvent =
  | { type: "conversation:created";
      data: { aggregateId: string; actor: Actor; createdAt: Date };
      metadata: EventMetadata }
  | { type: "conversation:file-added"; data: {...}; metadata: EventMetadata }
  | ...
```

Observed tag styles: `conversation:created`, `message:sent`,
`ocr.job:job-completed`, `storage.file:file-uploaded`,
`storage.file:file-deleted`. Every event carries `data.actor` and
`metadata: EventMetadata` (from `event-sourcing-core` — trace context, aggregate
context, etc.). Events are produced only inside a `Transition` and are the
argument to the pure `applyEvent` reducer.

## Listener modules — the consumer construct

A cross-service reaction is an `EventListenerModule<SharedDomainEvent>` living in
the **consuming** service's `application/` folder:

```ts
export class NameGenerationListeners implements EventListenerModule<SharedDomainEvent> {
  constructor(private readonly deps: NameGenerationListenersDeps) {}   // narrowed deps

  register(registrar: EventRegistrar<SharedDomainEvent>): void {
    registrar.on(
      "message:sent",                                   // event tag
      this.handleMessageSent,                           // handler
      "conversation.name-generation.on-message-sent",   // stable handler id (idempotency/DLQ key)
    );
  }

  private handleMessageSent = async (
    event: Extract<SharedDomainEvent, { type: "message:sent" }>,
  ): Promise<void> => { /* ... issue a command on THIS service ... */ };
}
```

`register(registrar)` may chain multiple `.on(...)` calls
(`DocumentSearchIndexListeners` binds `ocr.job:job-completed`,
`storage.file:file-uploaded`, `storage.file:file-deleted` in one module).

### Conventions & invariants (observed)

- **Consumer-owned:** the listener lives with the service that *reacts*, and its
  handler ends by calling that service's own `Command`/adapter — never another
  service's write path. `NameGenerationListeners` reacts to a *message* event and
  issues a *conversation* `rename-conversation` command.
- **Narrowed deps:** `Pick<ConversationService, "Query" | "Command">`,
  `Pick<StorageService, "Query">`, `Pick<MiniDocumentSearchClient, "indexDocument"
  | "deleteDocument">`. A listener declares only what it uses.
- **Idempotency is the handler's job.** `NameGenerationListeners` re-queries
  state and bails if `conversation.name !== null`; index listeners re-check the
  file still exists. Handler ids are stable strings so re-delivery is
  deduplicable.
- **Actor discipline.** Handlers skip system-initiated events where a user
  association is required (`isUserActor(actor)` guard) and preserve the original
  actor when issuing follow-up commands.
- **Retryable vs terminal.** Throwing from a handler triggers retry → dead
  letter; handlers deliberately *return* (log-and-skip) on non-retryable/expected
  conditions (empty OCR, already-named) to avoid DLQ pollution, and only *throw*
  on genuinely retryable failures.

## Wiring: modules → processors (the outbox)

Listeners are registered onto an `EventProcessor` inside the service factory. The
factory returns processor *factories* built on a base processor injected from
`InfrastructureProvider.createBaseOutboxProcessor`:

```ts
createOutboxProcessor: (cfg) => {
  const processor = options.createBaseProcessor(cfg);
  processor.registerModule(new ConversationLoggingListeners());
  return processor;
},
createNameGenerationProcessor: (cfg) => {
  const processor = options.createBaseProcessor(cfg);
  processor.registerModule(new NameGenerationListeners({ conversationService, generateConversationName }));
  return processor;
},
```

The base processor (`createBaseOutboxProcessor`) supplies the delivery
guarantees: `errorHandling: { mode: "deadletter", maxRetries: 3, backoff → 900s }`
against a shared `PostgresDeadLetterRepository`, interval scheduling, shared
metrics, reading from `PostgresProcessorRepository` (the outbox). So the flow is:

```
Transition emits event
  → appendEvents writes event + updates projection in ONE Postgres tx (outbox row)
  → EventProcessor polls outbox, delivers SharedDomainEvent to registered modules
  → listener handler runs; throw ⇒ retry/backoff ⇒ dead-letter
  → DeadLetterReprocessor drains DLQ (createBaseDeadLetterReprocessor)
```

Each processor is an independently-named consumer group with its own start
position (`FROM_INITIAL` / `FROM_LATEST`), enumerated in
`ApplicationContainer.getAllProcessors()`.

## `event-sourcing-core` — the substrate

The `@legal-ai/event-sourcing-core` package (`frontend/packages/`) provides the
generic machinery; services only supply domain types:

- `AggregateRepository` / `PostgresAggregateRepository` — `load`, `appendEvents`
  (optimistic-locked, with `onCommit` for same-tx projection), `OptimisticLockError`.
- `EventProcessor` + `PostgresProcessorRepository` — the outbox consumer with
  deadletter + interval scheduling.
- `EventListenerModule` / `EventRegistrar` — the `.on(tag, handler, id)` API.
- `DeadLetterReprocessor` / `PostgresDeadLetterRepository` — DLQ drain.
- `EventMetadata`, `BaseEvent`, `DomainEvent` (base), `ProcessorMetrics`.
- Suspended-workflow engine (`WorkflowExecutor`, `WorkflowEvent`,
  `WorkflowDefinition`, projection storage) — the substrate under the
  substantiation / compliance-review workflow services; `WorkflowEvent` is folded
  into `SharedDomainEvent` so workflow progress is observable cross-service.

The internals of that package (outbox polling, optimistic-lock protocol, suspended
workflow serialization) are a worthwhile **separate** research pass.
