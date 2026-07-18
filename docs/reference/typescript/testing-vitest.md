---
type: reference
status: draft
source:
  - /Users/gabriel/Work/gh/legal-ai/frontend/nogai/vitest.config.ts (observed — 5 projects)
  - /Users/gabriel/Work/gh/legal-ai/frontend/packages/*/vitest.config.ts (observed)
  - /Users/gabriel/Work/gh/legal-ai/frontend/nogai/vitest.setup.ts (observed)
  - /Users/gabriel/Work/gh/legal-ai/frontend/*/package.json (observed — test scripts, @vitest/coverage-v8)
  - /Users/gabriel/Work/gh/legal-ai/.github/workflows/ci.yml (observed — frontend-tests matrix)
links: ["[[type-checked-tests]]", "[[linting-eslint]]", "[[qa-chain-typescript]]", "[[architecture-tests]]", "[[crap-typescript]]", "[[mutation-testing-typescript]]"]
---

# Testing setup & conventions — Vitest (as found)

Vitest 4 across the workspace, always `dotenv -- vitest run`, always with
**`test.projects`** (multi-project) to split by environment/cost. Paths
repo-relative to `frontend/`.

## 1. Multi-project split, by environment and by cost (observed)

Projects partition tests so cheap/fast ones run in CI and expensive ones run
out-of-band. `nogai/vitest.config.ts` defines **five** projects:

| Project | env | include glob | why separate |
|---|---|---|---|
| `node` | node | `src/{__test__,config,services,db,lib,di,server}/**/*.{test,spec}.ts` | backend-like unit tests |
| `jsdom` | jsdom | `src/{components,app,api,hooks,contexts,actions,i18n}/**/*.{test,spec}.ts{,x}` + `*.feature.test.ts` | React/UI; `setupFiles: ["./vitest.setup.ts"]`, `css:true` |
| `e2e` | node | `src/**/*.end-to-end.test.ts`, `*.smoke.test.ts` | real services/testcontainers; `testTimeout 180000` |
| `eval` | node | `src/**/*.eval.test.ts` | LLM calls; `testTimeout 1800000`, `retry 0` |
| `arch` | node | `src/**/architecture.test.ts` | tsarch; `isolate:false`, `fileParallelism:false` (share cache — [[architecture-tests]]) |

The distinctions that matter: **environment** (node vs jsdom), **timeout**
(unit 60s → e2e 180s → eval 30min), **retry** (unit `retry:2`; eval/arch
`retry:0` — non-deterministic vs deterministic), and **isolation** (arch shares
a tsarch cache). `node`/`jsdom` `exclude` the slow projects' globs so they never
double-run.

Package configs are smaller variants of the same idea:
`knowledge-graph` → `unit`/`react`/`eval`/`eval-bench`; `agent-react` →
`unit`/`eval`; `cli-v2` → `unit`/`web`/`e2e`. `logger` and `event-sourcing-core`
use a **single** (non-project) config. (observed — per-member variance)

## 2. Test file naming & location (observed)

- **Colocated in `__test__/` dirs** (singular — enforced by the
  `no-tests-directory` ESLint rule, [[linting-eslint]]). Apps put them under
  `src/**/__test__/`; packages under a top-level `__test__/` and/or
  `src/**/__test__/`.
- **Suffix encodes the project**: `*.test.ts` / `*.spec.ts` (unit),
  `*.feature.test.ts` (jest-cucumber BDD), `*.property.test.ts` /
  `*.fuzzy.test.ts` (fast-check — [[qa-chain-typescript]]),
  `*.end-to-end.test.ts` / `*.smoke.test.ts` (e2e), `*.eval.test.ts` (eval),
  `architecture.test.ts` (arch), `*.integration.test.ts`. Globs route each
  suffix to its project.
- **Snapshots** go in `snapshots/`, never `__snapshots__/` — enforced by ESLint
  (`no-dunder-snapshots-directory`) so prettier's ignore catches them, and by a
  custom `resolveSnapshotPath` in `nogai/vitest.config.ts`.

## 3. Setup files & environment shims (observed)

`nogai/vitest.setup.ts` (jsdom project only) does the standard RTL wiring:
`expect.extend(@testing-library/jest-dom matchers)`, `afterEach(cleanup)`, wires
**jest-cucumber** to Vitest's `describe/test`, and polyfills `ResizeObserver` /
`IntersectionObserver` for Radix/animation components.
`knowledge-graph/__test__/react-setup.ts` and `eval/eval-setup.ts` are analogous
per-project setups.

## 4. Assertion style & test utilities (observed)

- **Assertions:** Vitest `expect` + jest-dom matchers (jsdom). Extra assertion
  fns are allow-listed in ESLint `vitest/expect-expect`: `toPassAsync` (tsarch),
  `assertSchemaContainment`, `expectExtractionStatesToMatch`, `expectTypeOf`
  ([[linting-eslint]]). BDD tests use jest-cucumber `then/and` callbacks.
- **Builders/factories:** shared factories live in
  `**/services/__test__/mocks/**` — ESLint `no-local-mock-factories` warns when a
  test hand-rolls a mock instead, and `require-assert-all-overrides-called`
  forces `assertAllOverridesCalled()`. Fixtures as `__test__/**/fixtures.ts`,
  builders as `*.factory.ts` / `test-factory.ts`, fast-check generators as
  `__test__/arbitraries/*.arbitrary.ts`.
- **DI discipline:** `no-container-in-tests` bans `ApplicationContainer` in unit
  tests (factories only); e2e/integration are exempt.

## 5. Coverage provider (observed)

- Provider: **`@vitest/coverage-v8` `^4.0.14`** (dev dep in every test member).
- Packages set it explicitly: `coverage: { provider: "v8", reporter: ["text",
  "html","lcov"], reportsDirectory: "./coverage", exclude: ["**/__test__/**",
  "**/index.ts","**/*.d.ts","vitest.config.ts"] }`.
- `nogai` sets `reporter: ["text","json"]` (json feeds the CRAP script —
  [[crap-typescript]]) and omits `provider` (defaults to v8). **No `thresholds`
  block anywhere** — there is no hard coverage floor. (observed)

## 6. The canonical QA chain (observed — CI is the source of truth)

There is **no single aggregate script**; the chain is four independent,
parallel, all-blocking CI jobs (`.github/workflows/ci.yml`). No husky/lefthook,
no format gate ([[formatting-prettier]]). What a developer/CI runs, from
`frontend/`:

```bash
pnpm -r type-check          # frontend-typecheck: tsc -p tsconfig.dev.json --noEmit (incl. tests)
pnpm -r lint                # frontend-lint: eslint per member
pnpm --filter . lint:knip   # frontend-lint (2nd step): knip dead-code/deps
pnpm --filter nogai lint:i18n
pnpm --filter landing-page lint:i18n   # frontend-i18n: translation parity
pnpm test                   # frontend-tests (matrix per member): dotenv -- vitest run …
```

- `frontend-tests` runs `pnpm test` **once per member** (matrix: logger,
  event-sourcing-core, agent-react, knowledge-graph, nogai). Each member's
  `test` = `dotenv -- vitest run --project …` selecting only the **cheap**
  projects — `nogai`: `--project node --project jsdom`. So `e2e`, `eval`,
  `eval-bench`, and `arch` are **excluded from CI's default run** and invoked
  by hand (`test:e2e`, `test:eval`, `test:arch`). (observed)
- **Order note:** because the four jobs run in parallel, order is not enforced by
  CI. A sensible local order mirrors the Python chain: **type-check → lint (+knip)
  → i18n → test**. There is **no format-check step** — add `prettier --check`
  yourself if you want it gated.
- Out-of-band strength gates (not in CI): `test:crap` ([[crap-typescript]]),
  `test:mutate` ([[mutation-testing-typescript]]), `test:arch`
  ([[architecture-tests]]).

## Recommended distillation

- One `vitest.config.ts` per member with `test.projects` split by env + cost;
  put slow/nondeterministic suites (e2e/eval/arch) in their own projects and
  keep them out of the default `test` script.
- Colocate in `__test__/`, encode the project in the filename suffix, `snapshots/`
  not `__snapshots__/`.
- `@vitest/coverage-v8`, `reporter` include `json` if a CRAP/analysis stage
  consumes it; add `thresholds` if you want a floor (this repo has none).
- Canonical chain: `pnpm -r type-check && pnpm -r lint && pnpm --filter .
  lint:knip && pnpm -r test` (add i18n / format-check as needed).
