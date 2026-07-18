---
type: reference
status: draft
source:
  - /Users/gabriel/Work/gh/legal-ai/frontend/nogai
---

# CRAP — TypeScript implementation (as found)

Repo: `legal-ai/frontend`, package `nogai` (Next.js / TypeScript, pnpm
workspace, Vitest). This is the **advisory** variant: CRAP is a runnable dev-loop
script, **not** wired into CI and **not** behind a git hook (no husky/lefthook/
pre-commit present anywhere in the frontend).

All paths below are repo-relative to `legal-ai/frontend/` unless noted.

## Tools (observed)

- **Complexity:** hand-rolled — no external tool. `nogai/scripts/crap-analysis.ts`
  walks the AST via the `typescript` compiler API and counts branch points.
- **Coverage:** Vitest with `@vitest/coverage-v8` → Istanbul-shaped
  `coverage-final.json` (`statementMap`/`s`, `branchMap`/`b`, `fnMap`/`f`).
- **Compositing script:** `nogai/scripts/crap-analysis.ts` (385 lines), run with
  `tsx`.

## The score (observed, `crap-analysis.ts` L1-3, L109-111)

```ts
// CRAP(f) = comp² × (1 - cov)³ + comp
const crap = Math.round(
  complexity * complexity * Math.pow(1 - cov, 3) + complexity,
);
```

Note `Math.round` — the TS score is an **integer**; Python keeps it a float.

## Complexity: computed from the AST (observed L251-287)

Base complexity 1, +1 for each branch point, not recursing into nested
functions (L281). The counted node kinds (L256-277):

```
IfStatement, ForStatement, ForInStatement, ForOfStatement,
WhileStatement, DoStatement, CaseClause, ConditionalExpression (?:),
BinaryExpression where operator is  &&  ||  ??
```

Function-like nodes recognized (L220-227): function declarations, function
expressions, arrow functions, method declarations. Names are recovered including
`const foo = () => …` variable-assigned arrows (L229-249).

## Coverage per function (observed L291-327)

Uses **statements + branches** within the function's location range (Istanbul
`fnMap[*].loc`), unlike Python's line-only approach:

```ts
// statements whose loc is inside the function range
totalStatements++;  if ((s[key] ?? 0) > 0) coveredStatements++;
// branch arms inside the function range
totalBranches++;    if (h > 0) coveredBranches++;

const total = totalStatements + totalBranches;
if (total === 0) return 1;        // nothing measurable ⇒ fully covered
return (coveredStatements + coveredBranches) / total;
```

Complexity is matched to each coverage function by name + line-range, with a
line-range-only fallback, then a hard fallback of complexity `1` (L353-378).

## Skips (observed L82-83)

`node_modules`, and any path containing `__test__` or `.test.` are excluded.

## Threshold config — env vars, not a file (observed L60-62)

```ts
const threshold = Number(process.env.CRAP_THRESHOLD ?? "8");   // default 8
const topK      = Number(process.env.CRAP_TOP_K     ?? "20");  // rows shown
const showAll   = process.env.CRAP_SHOW_ALL === "1";
```

There is **no `min-complexity` guard** — any function with `crap > 8` fails
(L127). Threshold default is `8` (Python's is `30` with a `cc>5` guard — not
comparable; each is tuned to its own codebase).

## The gate condition (observed L127, L167-176)

```ts
const failed = results.filter((r) => r.crap > threshold);
…
if (failed.length > 0) process.exit(1);   // non-zero exit on any offender
```

Same exit-1 contract as Python, but nothing in CI calls it (see below).

## npm scripts (observed `nogai/package.json` L23-25)

```json
"crap":      "tsx scripts/crap-analysis.ts coverage/coverage-final.json",
"test:crap": "dotenv -- vitest run --coverage --coverage.reporter=json --coverage.clean=false --project node --project jsdom && tsx scripts/crap-analysis.ts coverage/coverage-final.json",
"test:mutate": "stryker run"
```

`test:crap` is the self-contained entry: it produces fresh JSON coverage, then
runs CRAP over it — the "run tests first" ordering baked into one `&&` chain.

## Coverage config (observed `nogai/vitest.config.ts` L27-30)

```ts
coverage: {
  reporter: ["text", "json"],       // json ⇒ coverage/coverage-final.json
  reportsDirectory: "./coverage",
},
```

No `thresholds` block — the TS repo has **no hard coverage floor** (Python has
`fail_under = 90`).

## Gate wiring — advisory only (observed)

- **CI** (`legal-ai/.github/workflows/ci.yml`) runs `pnpm test`, `pnpm -r
  type-check`, `pnpm -r lint`, `lint:knip`, `lint:i18n`. It **does not** run
  `crap`, `test:crap`, or `test:mutate`. CRAP is a developer-invoked tool.
- **No git hook** — no husky/lefthook/pre-commit config exists in the frontend
  (grep for `husky|lefthook|pre-commit|prepare` in the package.jsons returns
  nothing). Contrast with Python's enforced pre-push hook.
- **No CLAUDE.md** in the frontend — no agent-facing CRAP instruction is
  documented (inferred from absence; Python documents it explicitly).

## Adjacent: this is part of a mutation-testing loop

`nogai` also has **Stryker** mutation testing configured
(`nogai/stryker.config.json`: vitest runner, incremental, `test:mutate` script;
devDeps `@stryker-mutator/core` + `…/vitest-runner`). A design doc,
`packages/knowledge-graph/docs/2026-04-08-mutation-testing-plan.md`, describes
porting the pattern (calls it "the nogai pattern"): copy `crap-analysis.ts`
(path-agnostic), add `coverage-priority.ts` and `survivor-report.ts`, chained
via `&&` as composable scripts. CRAP there is one stage of a
baseline→coverage→prioritize→mutate→analyze loop. That mutation loop deserves
its own research pass — see the summary.
