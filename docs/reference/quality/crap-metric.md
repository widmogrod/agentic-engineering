---
type: reference
status: draft
source:
  - /Users/gabriel/Work/gh/agentic-spreadsheet-workflow (Python)
  - /Users/gabriel/Work/gh/legal-ai/frontend/nogai (TypeScript)
---

# CRAP metric — language-agnostic essence

CRAP (Change Risk Anti-Patterns) collapses two per-function measurements —
cyclomatic **complexity** and test **coverage** — into a single risk number.
Both studied repos implement the *identical* formula; they differ only in the
language tooling that feeds it. This file extracts the reusable core so the
workflow can be dropped onto any language.

## The formula

```
CRAP(f) = complexity(f)² · (1 − coverage(f))³ + complexity(f)
```

- `complexity(f)` — cyclomatic complexity of function `f` (integer ≥ 1).
- `coverage(f)` — fraction of `f`'s statements/branches exercised by tests,
  in `[0, 1]`.

Observed verbatim in both repos:
- Python: `scripts/crap.py::crap_score` → `complexity**2 * uncovered**3 + complexity`
- TypeScript: `nogai/scripts/crap-analysis.ts` L109-111 →
  `complexity * complexity * Math.pow(1 - cov, 3) + complexity`

## Why complexity × uncovered = risk (the philosophy)

Quoting the Python docstring (`scripts/crap.py` L8-13, observed):

> Complex code that is well tested stays low; complex code that is poorly
> tested grows fast. It is a clear, deterministic signal — for both developers
> and coding agents — that a function needs either tests or simplification.

The exponents encode the intent:
- **complexity²** — risk grows super-linearly with branchiness. A 20-branch
  function is far more than 2× as dangerous as a 10-branch one.
- **(1 − coverage)³** — coverage buys down risk aggressively. At 100% coverage
  the whole first term vanishes and `CRAP = complexity` (a floor: complex code
  is never risk-free, but tests cap the penalty). At 0% coverage the function
  pays the full `complexity² + complexity`.
- The metric therefore has exactly **two escape hatches**: add tests (drive
  `coverage → 1`) or reduce complexity (split the function). Both are the
  desired remediations — the score never rewards suppression.

It is **deterministic** — same code + same tests ⇒ same score — which is what
makes it usable as an automated gate and as an unambiguous instruction to an
agent ("bring these functions under threshold").

## The workflow pattern

```
   test runner ──(coverage artifact, machine-readable)──┐
                                                         ▼
   complexity tool ──(per-function CC + line ranges)──▶ compositing script
                                                         │
                                                         ▼
                                          per-function CRAP, sorted desc
                                                         │
                                    ┌────────────────────┴───────────────┐
                                    ▼                                     ▼
                         gate: exit≠0 if any offender          human/agent report
                         (pre-push hook / CI step)             (top-K offenders)
```

Key invariants seen in both repos:
1. **Coverage must be fresh.** CRAP reads a coverage file the test run wrote;
   the ordering "run tests first, then CRAP" is enforced/documented in both
   (`CLAUDE.md` L25: "run pytest FIRST (reads coverage.json)"; the TS
   `test:crap` script chains `vitest run --coverage … && tsx …crap-analysis.ts`).
   A stale coverage file yields a wrong score — this is the main footgun.
2. **Join key = per-function line ranges.** Coverage is reported per line;
   complexity is reported per function with a `[startLine, endLine]` span. The
   script intersects them to get per-function coverage. Functions are the unit,
   not files.
3. **Sort descending, report offenders, non-zero exit on any offender.** Both
   scripts `process.exit(1)` / `return 1` when the offender list is non-empty.
4. **Test/generated code is excluded** from scoring (both skip `node_modules`
   / test files; Python only points radon at `src`).

Consumers:
- **Humans / CI** read the ranked table and the "N functions exceed threshold"
  summary.
- **Agents** are told (in `CLAUDE.md`) that CRAP is a gate and that the only
  fixes are "add tests or reduce complexity" — no config-tweaking to pass.

## Prescriptive recipe for a NEW language

You need five ingredients. Map each to a tool in your target language:

1. **A cyclomatic-complexity source, per function, with line ranges.**
   - Prefer an existing tool that emits JSON (Python: `radon cc --json`).
   - If none exists, walk the language's AST and count branch points yourself
     (TS repo does this via the `typescript` compiler API: `if`, `for`, `while`,
     `case`, `?:`, `&&`, `||`, `??` each add 1, base 1, don't recurse into
     nested functions). See `crap-typescript.md` for the branch-kind list.

2. **A coverage tool that emits a *parseable per-line or per-statement* report.**
   - Python: `coverage.py` JSON (`executed_lines` / `missing_lines` per file).
   - JS/TS: Istanbul/V8 `coverage-final.json` (`statementMap` + `s`, `branchMap`
     + `b`). Text/HTML reports are useless here — you need JSON/XML.
   - Enable **branch coverage** if the tool supports it (Python sets
     `branch = true`; TS folds branch hits into the fraction).

3. **A compositing script** (~150-200 lines) that:
   - parses the coverage artifact into `{file → covered/uncovered lines}`,
   - parses complexity into `{file → [{name, startLine, endLine, cc}]}`,
   - for each function computes `coverage = covered / (covered+uncovered)`
     over its line span (return `1.0`/fully-covered when it has 0 measurable
     statements),
   - computes `CRAP = cc² · (1−cov)³ + cc`,
   - sorts descending and prints a table.

4. **Threshold config** with two knobs:
   - `threshold` — CRAP value above which a function fails.
   - `min-complexity` — floor below which functions are never flagged (so
     trivial-but-untested code doesn't spam the gate). *(Python has this; TS
     omits it — see disagreement below. Recommended: keep it.)*
   - Store it where the language keeps config (Python: `[tool.crap]` in
     `pyproject.toml`; a JSON/env fallback works too).

5. **Gate integration points** — wire the script into:
   - the **test dev loop** as a runnable command (`pnpm crap`, `uv run python
     scripts/crap.py`),
   - a **pre-push hook** (cheap, blocks bad pushes) and/or a **CI job**, always
     *after* the coverage-producing test step in the same job,
   - **agent instructions** (`CLAUDE.md`): state the gate, the threshold, and
     that the only remedies are tests or simplification.

Pair CRAP with a **hard coverage floor** (`fail_under`) so coverage can't
silently rot underneath the CRAP score — the Python repo does this
(`fail_under = 90`); the TS repo does not.

## Where the two repos disagree (resolve deliberately when templating)

| Concern | Python (`agentic-spreadsheet-workflow`) | TypeScript (`nogai`) |
|---|---|---|
| Complexity source | external tool `radon==6.0.1` | hand-rolled AST walk over `typescript` compiler |
| Coverage granularity | line-level (`executed`/`missing`) | statement **+ branch** maps |
| Flag condition | `cc > min-complexity(5) AND crap > threshold(30)` | `crap > threshold(8)` only |
| Threshold source | `[tool.crap]` in `pyproject.toml` | env vars (`CRAP_THRESHOLD`, default 8) |
| Coverage floor | hard `fail_under = 90` | none configured |
| Enforcement | pre-push hook **and** CI (blocking) | manual script only — **not in CI**, no git hook |
| Score rounding | float (`30.0`) | `Math.round` to integer |

The thresholds are **not comparable** (30 with a cc>5 guard vs 8 with no guard)
— each was tuned to its own codebase. A template should ship a sensible default
plus documentation that the number must be calibrated per project, not copied.

The load-bearing divergence: **Python treats CRAP as an enforced gate; TS
treats it as an advisory dev-loop tool.** A skill should let the setter choose
the enforcement level explicitly rather than assume one.
