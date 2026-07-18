---
type: reference
status: draft
source:
  - /Users/gabriel/Work/gh/agentic-spreadsheet-workflow
---

# CRAP — Python implementation (as found)

Repo: `agentic-spreadsheet-workflow` (Python 3.13, managed with `uv`). This is
the **fully-enforced** variant: CRAP is a blocking gate in both the pre-push
hook and CI.

All paths below are repo-relative to `agentic-spreadsheet-workflow/`.

## Tools (observed)

- **Complexity:** `radon==6.0.1` (declared as a dependency in `pyproject.toml`
  L52). Invoked as `radon cc --json <targets>`.
- **Coverage:** `coverage.py` via `pytest-cov` — `pytest` writes `coverage.json`
  (and `.xml`). Branch coverage is on.
- **Compositing script:** `scripts/crap.py` (191 lines, stdlib only:
  `json`, `subprocess`, `tomllib`).

Note: there is a stale duplicate `crap.py` at the repo root (an earlier TS-style
version); the **live** gate is `scripts/crap.py`, per `CLAUDE.md` L25/L36 and
both the pre-commit and CI wiring. No unit test for the script exists
(`tests/` has no `*crap*` file — inferred: the gate is trusted, not tested).

## The score (observed, `scripts/crap.py` L54-57)

```python
def crap_score(complexity: int, coverage: float) -> float:
    """Return ``comp**2 * (1 - cov)**3 + comp``."""
    uncovered = 1.0 - coverage
    return complexity**2 * uncovered**3 + complexity
```

## How coverage per function is derived (observed L95-108)

Coverage is line-based. For a function's `[lineno, endline]` span, it counts how
many of those lines are in coverage.py's `executed_lines` vs `missing_lines`:

```python
span = range(lineno, endline + 1)
covered = sum(1 for ln in span if ln in executed)
uncovered = sum(1 for ln in span if ln in missing)
statements = covered + uncovered
if statements == 0:
    return 1.0          # no measurable statements ⇒ treated as fully covered
return covered / statements
```

`load_coverage` (L69-80) reads `coverage.json`'s `files.<path>.executed_lines`
and `.missing_lines` into `{posix_path → (executed_set, missing_set)}`.
`run_radon` (L83-92) shells out to `radon cc --json` and only keeps blocks whose
`type` is `"function"` or `"method"` (L121); methods are qualified as
`ClassName.method` (L129).

## Threshold config (observed)

`pyproject.toml` L247-251:

```toml
[tool.crap]
# Functions scoring above this are flagged and fail the gate.
threshold = 30.0
# Functions at or below this cyclomatic complexity are never flagged.
min-complexity = 5
```

`load_config` (L60-66) reads these with defaults `30.0` / `5`. CLI flags
(`--threshold`, `--min-complexity`, `--coverage-json`, positional `targets`
default `["src"]`) override config (L166-171).

## The flag / gate condition (observed L151, L179-186)

A function is an **offender** only when **both** hold:

```python
flag = s.complexity > min_complexity and s.crap > threshold
```

i.e. `cc > 5 AND crap > 30`. `main` returns `1` (non-zero exit) if any offender
exists, printing each as `path:lineno name (CRAP=…, CC=…)` and the line
"Add tests or reduce complexity to bring these down." `CLAUDE.md` L36 restates
it: "fails when cc > 5 AND crap > 30."

## Coverage config that feeds it (observed `pyproject.toml`)

```toml
[tool.pytest.ini_options]
addopts = [ …, "--cov=agentic_spreadsheet_workflow",
            "--cov-report=term-missing", "--cov-report=json", "--cov-report=xml" ]

[tool.coverage.run]
source = ["src"]
branch = true                 # branch coverage on
omit = [ … generated / impure-boundary modules … ]

[tool.coverage.report]
fail_under = 90               # hard coverage floor — separate gate from CRAP

[tool.coverage.json]
output = "coverage.json"      # exactly what scripts/crap.py reads
```

So there are **two independent gates**: `fail_under = 90` (coverage floor,
enforced by pytest itself) and the CRAP threshold (enforced by `scripts/crap.py`).

## Gate wiring (observed)

**Pre-push hook** — `.pre-commit-config.yaml` L63-85, a local hook that runs
tests then CRAP (ordering matters — CRAP reads the coverage the tests wrote):

```yaml
- id: pytest        # stages: [pre-push]
  entry: uv run pytest -q
- id: crap
  name: CRAP metric (complexity x coverage risk)
  entry: uv run python scripts/crap.py
  stages: [pre-push]
```

(pre-*commit* runs only ruff/mypy/bandit; pytest + CRAP + pip-audit are
pre-*push*.)

**CI** — `.github/workflows/qa.yml` L61-65, same order in one Linux job:

```yaml
- name: Pytest + coverage
  run: uv run pytest
- name: CRAP gate
  run: uv run python scripts/crap.py
```

The workflow comment (L58-60) is explicit: "pytest writes coverage.json …,
which the CRAP gate then reads — so it MUST run before crap, in this order, in
the same job."

**Agent instruction** — `CLAUDE.md` L25, L34-36:

> `uv run python scripts/crap.py` — CRAP gate — run pytest FIRST (reads coverage.json)
> **CRAP** (`scripts/crap.py`): fails when cc > 5 AND crap > 30. Fix = add tests
> or reduce complexity. Stale unless pytest ran first.
