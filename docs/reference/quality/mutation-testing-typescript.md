---
type: reference
status: draft
source:
  - /Users/gabriel/Work/gh/legal-ai/frontend/nogai (implemented)
  - /Users/gabriel/Work/gh/legal-ai/frontend/packages/knowledge-graph/docs/2026-04-08-mutation-testing-plan.md (design)
---

# Mutation testing — TypeScript implementation (as found)

Repo: `legal-ai/frontend`, package `nogai` (Next.js / TypeScript, pnpm
workspace, Vitest). Mutation engine: **Stryker** with the **vitest** runner.
All paths repo-relative to `legal-ai/frontend/` unless noted.

For the language-agnostic recipe and the full six-stage loop design see
`mutation-testing.md`. For the risk-score stage see [[crap-typescript]].

## What actually exists

Observed in `nogai`:

- `nogai/stryker.config.json` — Stryker config (below).
- `test:mutate` script = `stryker run` (`nogai/package.json`).
- devDeps `@stryker-mutator/core` `^9.6.0` + `@stryker-mutator/vitest-runner`
  `^9.6.0`.
- `nogai/scripts/crap-analysis.ts` — the CRAP risk stage ([[crap-typescript]]).

**Not** present anywhere in the frontend (grep-verified): `survivor-report.ts`,
`coverage-priority.ts`, `mutate:loop` / `mutate:report` scripts, a JSON mutation
reporter, or a `reports/` dir. Those are **plan-only** — see "Plan vs reality".

## Stryker config (observed, full file `nogai/stryker.config.json`)

```json
{
  "$schema": "https://raw.githubusercontent.com/stryker-mutator/stryker/master/packages/core/schema/stryker-core.json",
  "testRunner": "vitest",
  "plugins": ["@stryker-mutator/vitest-runner"],
  "reporters": ["progress", "clear-text"],
  "concurrency": 3,
  "incremental": true,
  "vitest_comment": "configFile is passed via vitest runner plugin",
  "warnings": { "unknownOptions": false }
}
```

Config choices, observed:

- **`testRunner: "vitest"`** + vitest-runner plugin — Stryker drives the same
  Vitest suite used for normal tests. No separate test config; the vitest runner
  discovers `vitest.config.ts` (which defines projects `node`, `jsdom`, `e2e`,
  `eval`, `arch`).
- **`incremental: true`** — the load-bearing choice. Stryker writes
  `stryker-incremental.json` and only re-tests changed/surviving mutants on
  re-runs. This is what makes an iterative loop viable.
- **`concurrency: 3`** — cap worker count.
- **`reporters: ["progress", "clear-text"]`** — **no `json` reporter.** Output
  is terminal-only; there is nothing for a programmatic survivor-analysis stage
  to consume. (The KG plan adds `"json"` + `jsonReporter.fileName` — not done
  here.)
- **No `mutators` block** — Stryker's default JS/TS mutator set is used (arithmetic,
  conditional-boundary, logical, string-literal, block-statement, etc.). Default
  mutators are **inferred** from the absence of an override; not explicitly set.
- **No `mutate` globs** — Stryker mutates its default target (`src/**` minus test
  files). The KG plan proposes excluding `index.ts`, `react/`, `testing/`,
  `prompts/`, `__test__/` — **not applied in nogai**; nogai mutates broadly.
- **`warnings.unknownOptions: false`** — silence config warnings (note the
  `vitest_comment` non-standard key parked in the file).

## Scripts (observed, `nogai/package.json`)

```json
"test": "dotenv -- vitest run --project node --project jsdom",
"test:coverage": "dotenv -- vitest run --coverage --project node --project jsdom",
"crap": "tsx scripts/crap-analysis.ts coverage/coverage-final.json",
"test:crap": "dotenv -- vitest run --coverage --coverage.reporter=json --coverage.clean=false --project node --project jsdom && tsx scripts/crap-analysis.ts coverage/coverage-final.json",
"test:mutate": "stryker run"
```

- `test:mutate` is a **bare `stryker run`** — no chaining, no report step. The
  composable-`&&`-chain pattern the plan describes is realised only for CRAP
  (`test:crap` chains coverage → CRAP), **not** for mutation.
- `test:crap` is the closest thing to a working composed stage: generate JSON
  coverage (`--coverage.reporter=json --coverage.clean=false`), then run CRAP
  over `coverage/coverage-final.json`. This is stage 1 + stage 2 of the loop.
- `--coverage.clean=false` preserves prior coverage output so the JSON accretes
  rather than being wiped — relevant when composing multiple coverage runs.

## Coverage config (observed, `nogai/vitest.config.ts` L27-30)

```ts
coverage: {
  reporter: ["text", "json"],       // json ⇒ coverage/coverage-final.json
  reportsDirectory: "./coverage",
},
```

`@vitest/coverage-v8` emits Istanbul-shaped `coverage-final.json`
(`statementMap`/`s`, `branchMap`/`b`, `fnMap`/`f`) — the shared input for both
the CRAP stage and (in the plan) the prioritize/survivor stages.

## How it's driven (observed)

- **Manual.** Run `pnpm test:mutate` from `nogai/`. Read the clear-text report in
  the terminal; there is no persisted artifact to feed a next stage.
- **Not in CI** — frontend CI runs test/type-check/lint/knip/i18n only; no
  mutation or CRAP step (see [[crap-typescript]] "Gate wiring").
- **No git hook, no CLAUDE.md instruction** — no automation or agent-facing doc
  wires the mutation run into any workflow.

## Plan vs reality (this package)

The KG design doc (`packages/knowledge-graph/docs/2026-04-08-mutation-testing-plan.md`)
calls this "the nogai pattern" and proposes porting a **richer** config to the
knowledge-graph package:

```json
// PLANNED (KG plan, Step 2) — NOT present in nogai:
"reporters": ["progress", "clear-text", "json"],
"jsonReporter": { "fileName": "reports/mutation.json" },
"mutate": [
  "src/**/*.ts", "!src/**/__test__/**", "!src/**/index.ts",
  "!src/react/**", "!src/testing/**", "!src/prompts/**"
]
```

Reality check:

- nogai's actual config is the **minimal** version above — no JSON reporter, no
  `mutate` targeting. The "pattern" the plan generalises from is thinner than the
  plan implies.
- The knowledge-graph package has implemented **none** of the plan: no
  `stryker.config.json`, no `scripts/crap-analysis.ts`, no `reports/`. Its
  `package.json` has no mutation scripts (only build/test/lens/schema scripts).
- Net: in TypeScript, the concretely working mutation surface is **`stryker run`
  with incremental caching over the Vitest suite, invoked by hand** — plus a
  separate, working CRAP script. The prioritize → mutate → survivor-analyze loop
  is documented intent, not running code.

## Reproduce it in a fresh package

Minimal working setup (matching nogai's observed reality):

```bash
pnpm add -D @stryker-mutator/core @stryker-mutator/vitest-runner tsx
```

Add the `stryker.config.json` above, add `"test:mutate": "stryker run"`, ensure
`vitest.config.ts` includes `"json"` in coverage reporters, then
`pnpm test:mutate`. To reach the full loop, add the plan's `json` reporter +
`mutate` globs and build the missing `coverage-priority.ts` /
`survivor-report.ts` stages (see `mutation-testing.md`).

## See also

- `mutation-testing.md` — language-agnostic recipe + full loop design
- [[crap-typescript]] — the CRAP risk stage in this same package
- [[crap-metric]] — the risk score, language-agnostic
