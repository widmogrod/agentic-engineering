---
type: reference
status: draft
source:
  - legal-ai/frontend/nogai/src/di
  - legal-ai/frontend/nogai/src/services/*/application/factory.ts
  - legal-ai/frontend/nogai/src/actions
  - legal-ai/frontend/nogai/src/server/routers
---

# Dependency Injection & Wiring Recipe

DI in `nogai` is hand-rolled — no framework, no decorators. It is a three-tier
composition: a shared **InfrastructureProvider**, per-service **factories**, and
a single **ApplicationContainer** service locator with lazy singletons. All
paths below are relative to `frontend/nogai/`.

## The three tiers

```
InfrastructureProvider  (src/di/infrastructure-provider.ts)
   shared clients + config: S3Client, TextractClient, GoogleGenAI, db,
   ProcessorMetrics, DeadLetterRepository, env-backed getters, and
   createBaseOutboxProcessor() — the standard EventProcessor factory.
        │  injected into
        ▼
create<Name>DI(options)  (src/services/<name>/application/factory.ts)
   the per-service composition root: news up repos + adapters, builds
   TransitionDeps + ServiceDeps, returns { service, projectionRepo,
   createOutboxProcessor, ... }.
        │  assembled by
        ▼
ApplicationContainer  (src/di/application-container.ts)
   Service-Locator singleton. One `Lazy(() => create<Name>DI({...}))` field
   per service; getXService() returns the memoized instance.
```

Consumers (`server actions`, tRPC routers, API routes, workers) only ever touch
the container:

```ts
import { getApplicationContainer } from "@/di";
const svc = getApplicationContainer().getConversationService();
```

`src/di/index.ts` re-exports `ApplicationContainer`, `getApplicationContainer`,
`InfrastructureProvider`.

## `Lazy<T>` — the memoization primitive

`src/di/lazy.ts`: a tiny box, `new Lazy(factory)` + `.get()` (create-once) +
`.reset()`/`.isInitialized()`. Every service slot and every shared client is a
`Lazy`, so nothing is constructed until first requested. This is what makes a
single container safe to hold ~20 services with heavyweight clients.

## Recipe: add a new event-sourced service

1. **Define the port in application.** In `application/service.ts`, declare the
   `interface <Name>ProjectionRepository` and `ServiceDeps { aggregateRepo,
   projectionRepo }`. The service constructor takes `ServiceDeps & TransitionDeps`.

2. **Write the factory** `application/factory.ts`:

   ```ts
   export function createConversationDI(options: CreateConversationDIOptions): ConversationServiceDI {
     const database = options.database ?? db;
     const policy = new ConversationPolicyAdapter(new PolicyEvaluator(POLICY_DOCUMENT));
     const aggregateRepo = new PostgresAggregateRepository<State, DomainEvent>(database);
     const projectionRepo = new PostgresConversationProjectionRepository(database);
     const transitionDeps: TransitionDeps = { policy, timeNow: () => new Date() };
     const service = new ConversationService({ aggregateRepo, projectionRepo, ...transitionDeps });
     return {
       service, projectionRepo, drizzle: database,
       createOutboxProcessor: (cfg) => {
         const p = options.createBaseProcessor(cfg);   // ← base processor injected in
         p.registerModule(new ConversationLoggingListeners());
         return p;
       },
       // additional named processors (e.g. createNameGenerationProcessor)
     };
   }
   ```

   Rules the factory must honor: it is the **only** file importing from
   `infrastructure/`; it accepts `createBaseProcessor` as an injected dependency
   (it never touches `InfrastructureProvider` directly); it returns processor
   *factories*, not started processors.

3. **Register a lazy slot** in `ApplicationContainer`:

   ```ts
   private conversationServiceDI = new Lazy(() =>
     createConversationDI({
       database: this.infra.database,
       googleGenAI: this.infra.googleGenAI,
       createBaseProcessor: (config) => this.infra.createBaseOutboxProcessor(config),
     }));

   getConversationService(): ConversationService {
     return this.conversationServiceDI.get().service;
   }
   getConversationProcessor(name = "conversation-processor", startPosition = "FROM_INITIAL") {
     return this.conversationServiceDI.get().createOutboxProcessor({ name, startPosition });
   }
   ```

4. **Cross-service deps go through the container, not through infra.** When
   service B needs service A, resolve A's DI first and pass the narrow surface:

   ```ts
   private messageServiceDI = new Lazy(() => {
     const conversationDI = this.conversationServiceDI.get();
     return createMessageDI({
       conversationService: conversationDI.service,
       conversationProjectionRepo: conversationDI.projectionRepo,
       ...
     });
   });
   ```

   Listeners and services accept **narrowed** dependencies via `Pick<>` (e.g.
   `Pick<StorageService, "Query">`, `Pick<ConversationService, "Query" | "Command">`)
   so the wiring only grants the methods actually used.

## Configuration & environment

`InfrastructureConfig` (all optional) overrides env-var defaults. Every getter
follows `this.config.x ?? process.env.X` (throwing for required secrets like
`GOOGLE_GENERATIVE_AI_API_KEY`, `PADDLE_API_KEY`). This makes the whole graph
constructible with an in-memory/config override — the basis for tests.

`ApplicationContainerConfig = InfrastructureConfig`. The container exposes three
constructors:

- `ApplicationContainer.getInstance(config?)` — global singleton (used in prod
  via `getApplicationContainer()`).
- `ApplicationContainer.create(config?)` — fresh isolated instance (tests).
- `ApplicationContainer.reset()` — drop the global singleton.

## Shared infrastructure the provider owns

- Clients: `s3Client`, `textractClient`, `googleGenAI`, `database` (Drizzle),
  `deadLetterRepo` (`PostgresDeadLetterRepository`), `metrics`.
- `createBaseOutboxProcessor(config)` → `EventProcessor<SharedDomainEvent>` with
  deadletter error handling (`maxRetries: 3`, exponential backoff to 900 s),
  interval scheduling (`PostgresIntervalScheduleRepository`), and shared metrics.
- `createBaseDeadLetterReprocessor(config, modules, overrides?)` → the DLQ drain.
- File-type helpers (`shouldConvertToMarkdown`, allowed/text MIME lists).

## Workflow services (deviation)

`substantiation` and `compliance-review` are wired through
`src/di/workflow-container.ts` (`createWorkflowDI(common, hooks)`) instead of a
per-service `factory.ts`. The container's private
`createSubstantiationWorkflowDI()` / `createComplianceReviewWorkflowDI()` supply
`createWorkflow`, `createExecutor`, `userAttributesExtractor`,
`buildWorkflowDeps`. The service object itself is `new`-ed on each getter call
(`new SubstantiationWorkflowService(di)`) rather than memoized — the *DI bundle*
is lazy, the thin service wrapper is not.

## Who runs the processors

`ApplicationContainer.getAllProcessors()` returns the full processor list
(storage, ocr, summarization, conversation, message, both search indexers, both
workflow executor+projection pairs, S3 cleanup, name-generation). The Next.js
request path only calls `getXService()`; the outbox/event processors are started
by a separate runner (**inferred** — `getAllProcessors` and `.start()` are only
referenced in `application-container.ts` and `instrumentation.node.ts`; no
in-repo worker entrypoint was located under `src/`, so processor startup lives in
a deployment/worker outside `nogai/src`). Confirming that runner is a good
follow-up research pass.
