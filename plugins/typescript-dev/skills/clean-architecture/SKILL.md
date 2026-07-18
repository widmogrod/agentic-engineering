---
name: clean-architecture
description: Layer rules for clean-architecture TypeScript service modules — domain/application/infrastructure layout, construct responsibilities, dependency direction with the factory composition-root exception, event-based cross-service communication, three-tier DI, and tsarch enforcement. Consult before creating or modifying any file under a service module (src/services/*) or DI wiring (src/di/) in a TypeScript project using the agentic-engineering conventions.
---

# Clean-architecture service modules (TypeScript)

Build each domain service as a self-contained hexagonal module under
`src/services/<name>/` with three layers plus a colocated test folder. Follow
these rules unless the project's own `docs/concepts/` records a deviation.
The rules are executable — they run as tsarch tests (see Enforcement), so a
violation is a failing build, not a style nit.

## Layer layout

```
src/services/<name>/
  domain/          pure business logic, platform-agnostic, zero I/O
  application/     orchestration: service class, factory, event listeners
  infrastructure/  adapters: DB projections/repositories, external SDK clients
  __test__/        mirrors the three layers + *.end-to-end.test.ts
src/di/            InfrastructureProvider + ApplicationContainer (wiring only)
```

DI wiring never lives inside a service — it lives in `src/di/`. Any
`container.ts` must be under a `di/` folder.

## Construct responsibilities

| Construct | File | Responsibility |
|---|---|---|
| Domain events | `domain/events.ts` | Discriminated union, namespaced tags (`"conversation:created"`), `data` + `metadata`. The source of truth. |
| Event reducer | `domain/events.ts` | `applyEvent(prev, event): State \| null` — pure fold of events → state. |
| State | `domain/state.ts` | Aggregate shape: data + free-function selectors, no methods. |
| Commands | `domain/commands.ts` | `z.discriminatedUnion("type", [...])`; the `type` tag drives dispatch. |
| Transition | `domain/transition.ts` | `async function Transition(deps, cmd, prevState): { events }` — the decision function. Clock, policy, etc. arrive via injected `TransitionDeps`, never reached for directly. |
| Policy port | `domain/policy.ts` | Authorization interface the domain depends on; impl in infrastructure. |
| Query | `domain/query.ts` | Serializable actor-first query builder; `for(actor)` bakes in authorization filters. |
| Errors | `domain/errors.ts` | Typed `Error` subclasses for domain failures, discriminated by class. |
| Service class | `application/service.ts` | Thin orchestrator: `Command()` / `Query()` / `Count()`. Loads from the event store, calls `Transition`, appends events, updates the projection in the same transaction. Holds no business rules. |
| Repository port | `application/service.ts` | `interface <Name>ProjectionRepository` — defined in application, implemented in infrastructure. |
| Listener module | `application/listeners.ts` or `*-listeners.ts` | `implements EventListenerModule` with `register(registrar)`; reacts to cross-service events, issues follow-up commands. |
| Contracts (ports) | `application/contracts.ts` | Optional narrow interfaces for non-persistence adapters (webhook verifiers, external clients). |
| Factory | `application/factory.ts` | `create<Name>DI(options)` — the per-service composition root. The ONLY file that imports from `infrastructure/`. |
| Projection adapter | `infrastructure/postgres-projection.ts` | Implements the repository port; `in-memory-projection.ts` is the in-memory adapter satisfying the same contract — kept in the production tree and contract-verified, mirroring the Python pack's "in-memory adapters are production code" rule. |
| SDK / policy adapter | `infrastructure/*-adapter.ts`, `*-client.ts` | Wrap external systems and policy evaluation. |

## Dependency direction

```
application    ──▶ domain          required (asserted "should dependOn")
infrastructure ──▶ domain          adapters implement domain/application ports
application    ──▷ infrastructure  FORBIDDEN — except factory.ts (below)
domain         ──▷ application     FORBIDDEN
domain         ──▷ infrastructure  FORBIDDEN
domain         ──▷ src/db/schemas  FORBIDDEN
domain, application ──▷ src/di     FORBIDDEN
domain         ──▷ lib.dom, node:stream  FORBIDDEN — platform-agnostic
whole service tree                 must be cycle-free
```

**The composition-root exception.** `application/factory.ts` is the only file
in the service allowed to import infrastructure concretes — it instantiates
repos and adapters and wires them into the service. Keep every such import in
that one file and say so at its top ("The ONLY file that imports from
infrastructure."). Everything else in `application/` depends on ports.

## Ports live where they are consumed

Persistence ports sit in `application/service.ts`; policy ports in
`domain/policy.ts`. Implementations live in `infrastructure/`, alongside an
in-memory adapter satisfying the same contract — verify both against a shared
contract spec (`__test__/infrastructure/*.contract.ts`, an exported function
wrapping a `describe` block; each adapter's `*.test.ts` imports and invokes it
with a factory — the TS analogue of the Python pack's `*Contract` base
classes; see the `testing` skill for the file convention).

**Error-channel provenance.** Domain failures are typed `Error` subclasses
(thrown), not `Result` values — this is the mined TS convention, and it
differs deliberately from the Python pack's errors-as-values rule. Contract
specs still assert on failures precisely: `await expect(op).rejects
.toBeInstanceOf(NotFoundError)` discriminates by class the way Python
discriminates by `Err` variant. If a project prefers `Result` in TS, record
it in `docs/concepts/` and keep it consistent across services.

## How services communicate

Never import another service's internals. Two sanctioned channels:

1. **Events at the boundary.** A listener module in `application/` subscribes
   to other services' domain events and issues follow-up commands to its own
   service. This is the default cross-service mechanism. A service that emits
   events for others to consume must register its `DomainEvent` arm in the
   shared typed union (`src/services/shared-events.ts`) — that registration is
   what makes cross-service consumption type-safe.
2. **Narrowed service surfaces wired by the container.** When service B needs
   service A synchronously, the `ApplicationContainer` resolves A's DI bundle
   and passes a narrowed surface (`Pick<StorageService, "Query">`) into
   `createBDI(options)`. Services never resolve each other.

## DI in three tiers

```
InfrastructureProvider  (src/di/)  shared clients, env-backed config,
                                   createBaseOutboxProcessor()
        ▼ injected into
create<Name>DI(options)            per-service composition root; returns
                                   { service, projectionRepo, createOutboxProcessor }
        ▼ assembled by
ApplicationContainer  (src/di/)    lazy singleton per service (Lazy<T> slots);
                                   getXService() memoizes
```

Rules: the factory accepts `createBaseProcessor` injected (it never touches
`InfrastructureProvider`); it returns processor *factories*, not started
processors. Consumers (actions, routers, workers) only touch the container.
Unit tests construct via factories with in-memory doubles — never via the
container (e2e/integration are exempt).

## Not every service is event-sourced

CRUD-shaped services keep the same three layers with a plain
`infrastructure/repository.ts` instead of aggregate + projection; query-only
services may have no aggregate at all, with listeners as the write path. The
layer and dependency rules apply unchanged.

## Enforcement

Three mechanisms, in order of authority (mirroring the Python pack):

1. **Contract specs** — adapter/in-memory parity per port
   (`*.contract.ts`, above): the only mechanism that proves substitutability
   instead of assuming it.
2. **The type checker** — `tsc -p tsconfig.dev.json --noEmit` at full
   strictness over src and tests (see the `qa-toolchain` skill); port
   conformance is structural.
3. **tsarch architecture tests** — the layer and dependency rules as
   executable tests. A shared
   `createServiceArchitectureTests({ serviceName, servicePath, infrastructurePatterns })`
   factory generates the standard rule suite, and each service adds a
   three-line `__test__/architecture.test.ts` invoking it. The rules run in a
   dedicated vitest `arch` project (`pnpm test:arch`) wired as its own CI job
   (see the `qa-toolchain` skill's gate wiring). Setup recipe, full rule
   catalog, and the exemption protocol (rules are carved out explicitly,
   never deleted): see
   [references/architecture-tests.md](references/architecture-tests.md).
