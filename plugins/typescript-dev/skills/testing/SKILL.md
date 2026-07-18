---
name: testing
description: Conventions for writing TypeScript tests with vitest — colocated __test__ directories, filename-suffix routing to vitest projects, tests type-checked at full strictness, typed mock factories. Consult before writing or reviewing any test in a TypeScript project using the agentic-engineering conventions.
---

# TypeScript testing conventions (vitest)

## Tests are source code for the type checker

Test files compile under `tsconfig.dev.json` at the SAME strict level as
production code (see the `qa-toolchain` skill). Consequences:

- Never use `any`, `as unknown as`, or `@ts-expect-error` to make a test
  compile. A test that needs them is telling you the types (or the design)
  are wrong — fix that instead.
- Test helpers, fixtures, and builders are fully typed and return real domain
  types, not shaped literals.
- Mock factories live in `__test__/mocks/` and satisfy the real interface —
  `satisfies SomeService` or an implementing class, so interface changes break
  mocks at compile time, not at runtime.

## Location and naming

- Tests are **colocated** in a `__test__/` directory (singular) next to the
  code under test — not in a parallel top-level tree. Snapshots go in
  `__test__/snapshots/`.
- The filename suffix declares the test's kind and routes it to a vitest
  project:

  | Suffix | Kind | Runs in |
  |---|---|---|
  | `*.test.ts` | unit / component | default (every run) |
  | `*.property.test.ts` | property-based (fast-check) | default |
  | `*.integration.test.ts` | real infrastructure | opt-in |
  | `*.end-to-end.test.ts` | full flows, long timeout | opt-in |
  | `architecture.test.ts` | dependency-rule checks | opt-in |

## Vitest projects: split by environment and cost

Single environment → one plain config. Mixed environments or expensive tiers →
`test.projects`, each with its own `include` glob, `environment` (`node` /
`jsdom`), timeout, and setup files. The default `pnpm test` runs only the
cheap, deterministic projects; expensive tiers are invoked explicitly
(`vitest run --project e2e`). CI runs what the default runs — an expensive
project that CI never runs must be invoked somewhere else on a schedule, or
it will silently rot.

## Style

- `describe` per unit under test; test names are behavior sentences
  ("returns Err(NotFound) when the pool id is unknown"), not method names.
- One behavior per test; shared setup in typed builder functions, not
  `beforeEach` mutation chains.
- Assert on values and closed unions, not on internal calls, wherever the
  design allows — mock at the boundary (ports), not inside the domain.
- Property-based tests (fast-check) for pure logic with meaningful input
  spaces; custom arbitraries live next to the mocks in `__test__/`.
- Coverage comes from `vitest run --coverage` (v8 provider); it feeds
  the coverage floor and any risk metrics the QA chain configures.
