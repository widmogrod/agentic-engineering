---
type: reference
status: draft
source:
  - /Users/gabriel/Work/gh/legal-ai/frontend/nogai (implemented, minimal)
  - /Users/gabriel/Work/gh/legal-ai/frontend/packages/knowledge-graph/docs/2026-04-08-mutation-testing-plan.md (design, not yet implemented)
---

# Mutation testing loop — language-agnostic recipe

Mutation testing measures **test-suite strength**, not code coverage: a tool
mutates the source (flip `<` to `<=`, `&&` to `||`, delete a statement) and
re-runs the tests. A mutant that tests still pass on is a **survivor** — a hole
in the suite. Coverage says a line *ran*; a killed mutant says the line's
behaviour is actually *asserted*.

This file is the **prescriptive recipe** drawn from the `legal-ai/frontend`
repo. Read it with one honesty caveat up front: the full self-improving loop
below is **designed in a plan doc, only partially built in reality** (see
[Plan vs. implemented](#plan-vs-implemented)). The recipe is still sound; treat
the un-built stages as "wire these yourself".

For the complexity/coverage risk score used as the prioritisation stage, see
[[crap-metric]] (and its per-language notes [[crap-typescript]], [[crap-python]]).

## The loop, stage by stage

The design (KG plan, "The Loop in Practice") is a six-stage cycle whose *memory*
is the mutation tool's incremental cache — each pass only re-checks changed or
still-surviving mutants, so runs get cheap after the first.

| # | Stage | Input | Output | Built? |
|---|-------|-------|--------|--------|
| 1 | **baseline** — run tests with coverage | source + tests | `coverage-final.json` (Istanbul shape) | ✅ observed |
| 2 | **CRAP / risk** — score functions by complexity × (1−coverage) | coverage JSON + source AST | ranked risk table, exit 1 over threshold | ✅ observed ([[crap-metric]]) |
| 3 | **prioritize** — sort files by coverage%, pick high-coverage-but-untested-behaviour targets | coverage JSON | ordered file list (or bare paths for piping) | ⛔ planned only |
| 4 | **mutate** — run the mutation tool | source (targeted globs) + tests | mutation report (JSON) | ✅ config exists; JSON reporter ⛔ planned |
| 5 | **analyze** — categorize survivors into real-gap / low-coverage / noise | mutation JSON × coverage JSON | `survivors.md` + `survivors.json` | ⛔ planned only |
| 6 | **kill & repeat** — write tests for real-gap survivors, re-run | new tests | shrinking survivor list, incremental cache updated | manual |

Stages 1, 2, 4 exist as runnable scripts. Stages 3 and 5 — the "prioritize" and
"analyze" glue that make it a *loop* rather than a raw mutation run — are
specified in the plan but **not implemented in either studied package**.

## Script composition: chained, not orchestrated

The governing convention (KG plan, "Architecture: Composable Scripts"):

> Separate npm scripts chained via `&&`. Each step has a distinct failure mode
> and can run independently. The `mutate:loop` script chains them all.

Each stage is its own package.json script; a top-level script `&&`-chains them.
No orchestrator process, no config DSL — the package-manager script table *is*
the pipeline. Language-agnostic restatement: **each stage is a standalone CLI
with its own exit code; the pipeline is a chain of `&&` in a task runner** (npm
scripts, Make, Justfile, `poethepoet`, tox). A stage that fails (non-zero exit)
halts the chain, so ordering encodes the data dependency (tests-then-coverage,
coverage-then-mutate).

Planned chain (KG plan, Step 7 — *aspirational, not built*):

```
mutate:loop = test:crap && mutate && mutate:report
              └ coverage+CRAP  └ stryker  └ survivor-report.ts
```

## Thresholds & config choices

- **Incremental mode ON** is the load-bearing choice: the tool caches per-mutant
  results (`stryker-incremental.json`) so re-runs only re-test the delta. The
  plan calls this file "the loop's memory — gitignored but never deleted on the
  same machine." Without it the loop is too slow to iterate (first run cited as
  ~15–30 min).
- **Concurrency** capped (3 workers observed) to bound resource use.
- **Targeted `mutate` globs**: the plan excludes non-behavioural code from
  mutation — re-export barrels (`index.ts`), UI/DOM-bound code, test
  infrastructure, and string-template/prompt files. Mutating those produces
  noise, not signal. (Observed nogai config does **not** set `mutate` globs — it
  mutates everything; the exclusion list is a plan-only refinement.)
- **CRAP threshold** for the risk stage: `8` (TS). This gates stage 2, not the
  mutation run. See [[crap-metric]].
- **No mutation-score threshold is enforced** in either package — the mutation
  report is advisory, read by a human, not a CI gate.

## Survivor-analysis workflow (the feedback edge)

This is what turns a report into a *loop*. The plan's `survivor-report.ts`
cross-references the mutation JSON against coverage JSON and bins each survivor:

- **real-gap** — survived in a file with **>60% coverage** and complexity >1.
  The line runs but nothing asserts its behaviour. **Actionable: write a test.**
- **low-coverage** — survived in a file with **<60% coverage**. The line barely
  runs. **Fix coverage first**, then re-mutate.
- **noise** — string literals, log messages, non-behavioural mutants.
  **Document and move on** — never chase these.

Outputs are dual: `survivors.md` (human reads the tables) and `survivors.json`
(machine input for the next iteration). The kill step is manual: a developer (or
agent) reads the real-gap list, writes assertions, runs the suite to confirm
green, then re-runs the loop — the incremental cache means only the touched
mutants re-execute, and the real-gap list shrinks. *(This entire stage is
designed but unimplemented — see below.)*

## How the loop is driven

**Observed: human-driven, developer-invoked.** Neither CRAP nor mutation runs in
CI (the frontend CI runs test/type-check/lint/knip/i18n only — see
[[crap-typescript]]), and there is no git hook. The scripts are run manually from
the package directory.

**Inferred (agent-driven):** the composable-CLI-with-exit-codes design and the
dual human/machine report outputs (`survivors.md` + `survivors.json`) are
exactly the shape an agent needs — deterministic stages, structured output to
read back, incremental cache so iterations are cheap. The plan frames the cycle
as "self-improving," which reads as intended for an agent or human to run
repeatedly. No agent instruction is actually wired up (no CLAUDE.md entry).

**CI:** not currently; the mutation run is too slow for per-commit CI. Incremental
mode + targeted globs would be the enabling pieces if moved to CI (e.g. nightly).

## Plan vs. implemented

Honest gap accounting across the two packages studied:

| Artifact | KG plan says | nogai reality | KG reality |
|----------|--------------|---------------|-----------|
| `stryker.config.json` | rich: JSON reporter, `mutate` globs | **minimal**: no JSON reporter, no globs | **absent** |
| `crap-analysis.ts` | copy from nogai | **present** (385 lines) | **absent** |
| `coverage-priority.ts` (stage 3) | new, ~80 lines | **absent** | **absent** |
| `survivor-report.ts` (stage 5) | new, ~120 lines | **absent** | **absent** |
| `mutate:loop` chained script | `test:crap && mutate && mutate:report` | **absent** | **absent** |
| reports/ dir | tracked | **absent** | **absent** |

So the "documented nogai pattern" over-states nogai: nogai implements
**stages 1, 2, 4 only** (coverage, CRAP, a bare `stryker run`). The
prioritize/analyze/loop glue lives **only in the KG plan doc**, and the KG
package has not implemented *any* of it. The self-improving loop is, as of this
research, an **aspiration built on a working-but-partial foundation**.

## Language-agnostic ingredients

To set this loop up in another language (e.g. Python with `mutmut` or
`cosmic-ray`), you need these interchangeable parts:

1. **A test runner with machine-readable coverage** producing a structured
   coverage artifact (Istanbul JSON in TS; `coverage.py` XML/JSON in Python).
   Stage 1 & the risk score both consume this.
2. **A mutation engine** with:
   - an **incremental / resumable cache** (Stryker `incremental`; `mutmut`
     keeps a results DB; `cosmic-ray` uses a session SQLite DB) — mandatory for
     iteration speed.
   - a **machine-readable report** of survivors (Stryker `json` reporter;
     `mutmut results` / `cosmic-ray dump`).
   - **mutant targeting** to exclude non-behavioural code (barrels, UI, string
     templates, generated code).
3. **A complexity source** to compute the risk score — a language AST walker
   (TS compiler API in TS; `radon`/`ast` in Python). See [[crap-metric]].
4. **A survivor-categorizer** that joins mutation-report × coverage to bin
   survivors real-gap / low-coverage / noise, emitting both a human `.md` and a
   machine `.json`.
5. **A task runner** to `&&`-chain the stages as independent exit-coded CLIs
   (npm scripts / Make / Just / `poethepoet` / tox).

The essence is orthogonality: coverage, complexity, mutation, and analysis are
four separate tools joined by structured files and exit codes — swap any one per
language without touching the others.

## See also

- [[crap-metric]] — the risk score used as the prioritisation stage
- [[crap-typescript]], [[crap-python]] — per-language risk-score implementations
- `mutation-testing-typescript.md` — the concrete Stryker/vitest config as found
