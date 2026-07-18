# Reference Catalog — Mined Conventions

Conventions extracted from two production codebases, as raw material for the
`python-dev` / `typescript-dev` knowledge packs (see the
[conceptual outline](../plan/2026-07-10-conceptual-outline.md)).

Sources: `agentic-spreadsheet-workflow` (single Python app, mature QA discipline)
and `legal-ai` (pnpm frontend monorepo + Python backend services). Every file
carries frontmatter, cites concrete file paths as evidence, and marks
observed vs. inferred and plan vs. reality. All `status: draft` — pending review.

## quality/ — gates & metrics

- [crap-metric.md](quality/crap-metric.md) — CRAP formula, philosophy, language-agnostic setup recipe (5 ingredients)
- [crap-python.md](quality/crap-python.md) — radon + coverage.py + `scripts/crap.py`; blocking in pre-push AND CI
- [crap-typescript.md](quality/crap-typescript.md) — hand-rolled TS-AST complexity + vitest v8 coverage; advisory only
- [qa-chain-python.md](quality/qa-chain-python.md) — the ordered blocking chain: hygiene → ruff → format → mypy → bandit → pytest+cov → CRAP → pip-audit (order is load-bearing)
- [qa-chain-typescript.md](quality/qa-chain-typescript.md) — knip, bespoke i18n validator, fast-check; CI-only, no hooks
- [mutation-testing.md](quality/mutation-testing.md) — the six-stage self-improving loop; honest built-vs-planned accounting
- [mutation-testing-typescript.md](quality/mutation-testing-typescript.md) — Stryker/vitest concrete config (incremental cache)

## python/ — service conventions

- [service-layout.md](python/service-layout.md) — flat package for deployables vs `src/` for libraries; `main.py` sole composition root; ports as `Protocol`; `api/<ep>/{router,model,service}.py`
- [service-configuration.md](python/service-configuration.md) — single fail-fast env module; mechanism variance across services
- [linting-formatting.md](python/linting-formatting.md) — ruff-only (lint+format), distilled recommended config
- [type-checking.md](python/type-checking.md) — mypy strict recipe, per-module overrides
- [testing.md](python/testing.md) — tests/ layout, naming, pytest config, marker tiers, fixture philosophy
- [test-doubles.md](python/test-doubles.md) — hand-written typed fakes vs MagicMock vs testcontainers vs record/replay; the two repos' split philosophies

## architecture/ — constructs & patterns

- [clean-architecture-services.md](architecture/clean-architecture-services.md) — hexagonal service modules: domain/application/infrastructure, construct catalog, dependency rules
- [dependency-injection.md](architecture/dependency-injection.md) — InfrastructureProvider → per-service factory → ApplicationContainer (`Lazy` singletons)
- [event-driven-communication.md](architecture/event-driven-communication.md) — typed SharedDomainEvent bus, listener modules, idempotency conventions
- [outbox-runtime.md](architecture/outbox-runtime.md) — outbox worker: cursor polling (no SKIP LOCKED — single instance per group), in-process retry, DLQ
- [event-sourcing-core.md](architecture/event-sourcing-core.md) — aggregates, optimistic lock via UNIQUE constraint, projections, suspended-workflow engine
- [saga-engine.md](architecture/saga-engine.md) — declarative state-machine sagas; **dormant in production**; decision table: listener vs saga vs workflow
- [interval-scheduling.md](architecture/interval-scheduling.md) — durable schedules, ephemeral at-least-once ticks; timeout/polling substrate
- [actor-authorization.md](architecture/actor-authorization.md) — actor-first auth: `Query.for(actor)` structural filtering, actor-stamped events, fail-closed policy document
- [architecture-tests.md](architecture/architecture-tests.md) — tsarch: layering rules as executable tests, `createServiceArchitectureTests()` factory
- [contract-tests.md](architecture/contract-tests.md) — ports as `Protocol`, in-memory adapters as production code, `*Contract` suites proving substitutability
- [errors-as-values.md](architecture/errors-as-values.md) — hand-rolled `Ok`/`Err`, no combinators, per-method error unions, Err-vs-raise rules

## layout/ — workspace topology

- [workspace-principles.md](layout/workspace-principles.md) — language-agnostic essence: apps vs packages, dependency direction, Dockerfile-per-deployable at root
- [pnpm-workspace.md](layout/pnpm-workspace.md) — scoped packages, `workspace:*`, `development` conditional exports, tsconfig split
- [uv-workspace.md](layout/uv-workspace.md) — **inverted topology**: per-service projects + lockfiles; services opt into `members = ["../packages/*"]` only when consuming shared packages

## deployment/ — images & composition

- [docker-pnpm.md](deployment/docker-pnpm.md) — three strategies: next-standalone, esbuild single-bundle, thin migrations image
- [docker-uv.md](deployment/docker-uv.md) — lockfile-first `uv sync --locked`, path-mirroring so `../packages/*` resolves in-image
- [compose-and-ci.md](deployment/compose-and-ci.md) — compose wiring; CI validates source but builds no images (builds live in CodeBuild/CDK)

## contracts/ — cross-language bridges

- [contract-principles.md](contracts/contract-principles.md) — single source of truth per contract, generation direction, drift-check constraints
- [openapi-sdk-generation.md](contracts/openapi-sdk-generation.md) — FastAPI → openapi-ts SDK from live services; committed `*.gen.ts`
- [schema-to-python-types.md](contracts/schema-to-python-types.md) — Zod → JSON Schema → datamodel-codegen → Pydantic, with `_augment.py` + regenerate-and-diff guard

## Also here

- [plugin-marketplace-spec.md](plugin-marketplace-spec.md) — Claude Code plugin/marketplace/SKILL.md spec (distribution mechanics, not a mined convention)

## Flagged but not yet researched

- Observability bootstrap (`instrumentation.py` / OpenTelemetry setup pattern; processor/saga Prometheus metrics)
- Migrations strategy & API versioning (only `mini_workflow` uses `/v1/`)
- `*.feature`-file + projection-repository contract-test style (TS BDD flavor)
- `Literal`-discriminant + `assert_never` exhaustiveness pattern; pipeline `StageError` style
- Secret persistence for packaged apps (keychain layering); marimo notebook conventions
- Image-build pipeline internals (CodeBuild/CDK in `infrastructure/`)
- Saga command resilience layer (retry/timeout/circuit-breaker in `command.ts`) — unused in production
