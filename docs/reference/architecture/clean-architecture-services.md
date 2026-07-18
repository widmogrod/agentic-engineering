---
type: reference
status: draft
source:
  - legal-ai/frontend/nogai/src/services
  - legal-ai/frontend/nogai/src/services/__test__/architecture.contract.ts
  - legal-ai/frontend/packages/event-sourcing-core
---

# Clean-Architecture Service Construct Catalog

How `src/services/*` in the `nogai` Next.js app is organized. Each domain
service is a self-contained hexagonal module with three enforced layers plus a
test folder. The rules below are not aspirational — they are executed as
`tsarch` tests (`architecture.contract.ts`), so they are **observed**, not
inferred, unless marked otherwise.

## Layer layout (observed)

Every event-sourced service uses the same three top-level folders:

```
src/services/<name>/
  domain/          pure business logic, platform-agnostic, zero I/O
  application/     orchestration: service class, factory, event listeners
  infrastructure/  adapters: Postgres projections, external SDK clients
  __test__/        mirrors the three layers + *.end-to-end.test.ts
```

DI wiring does **not** live inside the service — it lives in `src/di/` (see
`dependency-injection.md`). The contract test asserts any `container.ts` must be
under a `di/` folder.

## Constructs

| Construct | Layer | File convention | Responsibility |
|---|---|---|---|
| Domain events | `domain/events.ts` | `type DomainEvent = \| {...}` discriminated union | The source of truth. Namespaced string tags (`"conversation:created"`), `data` + `metadata: EventMetadata`. |
| Event reducer | `domain/events.ts` | `export function applyEvent(prev, event): State \| null` | Pure fold of events → state. Used both by the aggregate repo and projections. |
| State | `domain/state.ts` | `type State = {...}` + pure selectors (`getActiveFileContexts`) | The materialized aggregate shape. No methods, just data + free functions. |
| Commands | `domain/commands.ts` | `CommandSchema = z.discriminatedUnion("type", [...])`, `type Command = z.infer<...>` | Zod-validated inputs. `type` tag drives dispatch. |
| Transition | `domain/transition.ts` | `async function Transition(deps, cmd, prevState): { events }` | The decision function: validate command, apply guards/policy, emit events. Takes `TransitionDeps` (policy, `timeNow`) injected — never reaches for a clock or DB directly. |
| Policy port | `domain/policy.ts` | `interface ConversationPolicy` | Authorization interface the domain depends on. Impl lives in infrastructure. |
| Query | `domain/query.ts` | `interface <Name>QueryData` + `class <Name>Query` builder | Serializable, actor-first query objects. `for(actor)` auto-injects authorization filters; presets (`byId`, `paginated`) + fluent builder. |
| Errors | `domain/errors.ts` | typed `Error` subclasses | Domain-specific failures (`ConversationDeletedError`, `InvalidTransitionError`). |
| Service class | `application/service.ts` | `class <Name>Service` with `Command()` / `Query()` / `Count()` | Thin orchestrator. Loads aggregate, calls `Transition`, appends events via the repo, updates projection in the same transaction (`onCommit`). Retries `OptimisticLockError`. Holds no business rules. |
| Repository port | `application/service.ts` (co-located `interface`) | `interface <Name>ProjectionRepository` | The persistence contract the service needs. Defined in application, implemented in infrastructure. |
| Listener module | `application/*-listeners.ts` or `listeners.ts` | `class X implements EventListenerModule<SharedDomainEvent>` with `register(registrar)` | Reacts to cross-service events; issues follow-up commands. This is how services talk to each other (see `event-driven-communication.md`). |
| Contracts (ports) | `application/contracts.ts` | narrow `type`/`interface` | Optional. Used when the service needs external adapters beyond persistence (e.g. subscription's `SignatureVerifier`, `PaddlePortalClient`). |
| Factory | `application/factory.ts` | `create<Name>DI(options): <Name>ServiceDI` | The **only** file allowed to import from `infrastructure/`. Instantiates repos + adapters, wires `serviceDeps`, returns `{ service, projectionRepo, createOutboxProcessor, ... }`. |
| Projection adapter | `infrastructure/postgres-projection.ts` | `class Postgres<Name>ProjectionRepository` | Implements the repository port against Drizzle/Postgres. `in-memory-projection.ts` is the test double satisfying the same contract. |
| SDK / policy adapter | `infrastructure/*-adapter.ts`, `*-client.ts` | classes/factories | Wrap external systems (Paddle, GoogleGenAI, S3, mini_* HTTP services) and the `PolicyEvaluator`. |

## Dependency direction (enforced by `architecture.contract.ts`)

```
infrastructure ──▶ domain          (adapters implement domain/application ports)
application    ──▶ domain          (allowed, asserted "should dependOn")
application    ──▷ infrastructure  (FORBIDDEN except factory.ts¹)
domain         ──▷ application     (FORBIDDEN)
domain         ──▷ infrastructure  (FORBIDDEN)
domain         ──▷ src/db/schemas  (FORBIDDEN)
domain         ──▷ src/di          (FORBIDDEN)
domain must be platform-agnostic  (no lib.dom, no node:stream)
whole service must be cycle-free
```

¹ The contract test scopes the "application must not import infrastructure" rule
to the `application/` folder; `factory.ts` lives there yet imports
infrastructure. This is the deliberate composition-root exception — subscription's
factory documents it literally: *"The ONLY file that imports from infrastructure."*
Every factory re-instantiates infra concretes (`new PostgresAggregateRepository`),
so the rule is honored in spirit by keeping all such imports in one file per service.

## Annotated example tree: `conversation`

```
conversation/
  domain/
    events.ts        DomainEvent union + applyEvent() reducer      [source of truth]
    state.ts         State shape + getActiveFileContexts()/hasLink() selectors
    commands.ts      CommandSchema (zod discriminatedUnion) + Command type
    transition.ts    Transition(deps, cmd, prev) → {events}; guards + MAX_* limits
    policy.ts        ConversationPolicy interface (port)
    query.ts         ConversationQuery.for(actor).nameContains(...).build()
    errors.ts        ConversationDeletedError, InvalidTransitionError, ...
    actor.ts         re-exports/narrows core Actor for this aggregate
  application/
    service.ts       ConversationService.Command/Query/Count
                     + ConversationProjectionRepository interface (port)
                     + ServiceDeps { aggregateRepo, projectionRepo }
    factory.ts       createConversationDI(options) → ConversationServiceDI
    name-generation-listeners.ts     on "message:sent" → rename-conversation cmd
    conversation-logging-listeners.ts
  infrastructure/
    postgres-projection.ts    PostgresConversationProjectionRepository
    in-memory-projection.ts   test double (same contract)
    policy-adapter.ts         ConversationPolicyAdapter implements ConversationPolicy
    name-generator.ts         GoogleGenAI-backed NameGeneratorClient
  prompts/
    name-generator.prompt.ts  + __test__/snapshots
  __test__/
    architecture.test.ts      calls createServiceArchitectureTests({...})
    conversation.end-to-end.test.ts
    application/ domain/ infrastructure/   (mirror layers)
    infrastructure/projection-repository.contract.ts   shared contract test
```

### The `Command` flow (from `application/service.ts`)

```ts
async Command(cmd: Command, options?): Promise<State> {
  const entity = await this.deps.aggregateRepo.load(AGGREGATE_TYPE, id);   // event store, not projection
  const { events } = await Transition(this.deps, cmd, entity?.state ?? null); // pure decision
  // empty events == idempotent no-op → return prev state
  const { finalState } = await this.deps.aggregateRepo.appendEvents(
    id, AGGREGATE_TYPE, prevVersion, events, applyEvent,
    { onCommit: async ({ state, version, writer }) =>              // same tx as event append
        writer.execute(tx => this.deps.projectionRepo.upsert(id, state, version, tx)) },
  );
  // OptimisticLockError → retry up to retryOptimisticLockFailure (default 3)
}
```

Key invariants: reads for command handling come from the **event store**
(`.load`) not the projection (so deleted aggregates are visible); the projection
is updated **synchronously inside the append transaction** via `onCommit`;
authorization on `Query` is baked into the query object, not re-checked per row.

## Core module: `services/core/`

Shared, service-agnostic domain primitives — no event sourcing of its own:

- `domain/actors.ts` — canonical `Actor` discriminated union
  (`UserActor` / `AdminActor` / `SystemActor`), Zod schemas, guards
  (`isUserActor`), `createSystemActor(serviceId)`, `actorsEqual`, `formatActor`.
  Individual services re-export/narrow this in their own `domain/actor.ts`.
- `domain/policy.ts` — `PolicyDecision = { allow: true } | { allow: false; reason }`.
- `domain/pagination.ts`, `domain/errors.ts` (`EmptyArrayFilterError`).
- `domain/document-text-provider.ts` — a port; `infrastructure/document-text-provider.ts`
  and `infrastructure/mini-document-search-client.ts` implement/adapt it.

## Honest deviations from the pattern

- **No factory / not event-sourced:** `core`, `substantiation`,
  `compliance-review`. The two workflow services build on the
  `WorkflowExecutor`/`WorkflowEvent` machinery from `event-sourcing-core`
  (suspended workflows), wired via `src/di/workflow-container.ts`, and their
  service classes are `new`-ed directly in the container rather than via a
  `createXDI` factory.
- **CRUD, not event-sourced:** `waitlist`, `feedback`, `user`,
  `assistant-specialization`, `subscription` have a plain
  `infrastructure/repository.ts` (row store) instead of aggregate + projection.
  `subscription` is a hybrid — it *is* event-sourced (aggregate + projection)
  but also exposes a `repository.ts` and an `application/contracts.ts` ports file
  plus a `PaddleWebhookHandler` that depends only on those contracts.
- **Query-only / no aggregate:** `document-search`'s `DocumentSearchService`
  holds no state — it fans a query out to `mini_document_search` and enriches
  results from `StorageService.Query`. Its `application/listeners.ts` is the real
  write path (indexes on `ocr.job:job-completed` / `storage.file:file-uploaded`).
- **Listener naming:** most services use `application/listeners.ts`; conversation
  splits into `name-generation-listeners.ts` + `conversation-logging-listeners.ts`.
  Both forms are accepted by the contract test (`listeners.ts` pattern only pins
  location, not count).
