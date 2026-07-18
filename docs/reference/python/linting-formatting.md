---
type: reference
status: draft
source:
  - /Users/gabriel/Work/gh/agentic-spreadsheet-workflow/pyproject.toml
  - /Users/gabriel/Work/gh/agentic-spreadsheet-workflow/.pre-commit-config.yaml
  - /Users/gabriel/Work/gh/agentic-spreadsheet-workflow/.github/workflows/qa.yml
  - /Users/gabriel/Work/gh/agentic-spreadsheet-workflow/CLAUDE.md
  - /Users/gabriel/Work/gh/legal-ai/backend/*/pyproject.toml
  - /Users/gabriel/Work/gh/legal-ai/backend/*/.pre-commit-config.yaml
  - /Users/gabriel/Work/gh/legal-ai/.github/workflows/ci.yml
---

# Python Linting & Formatting — Ruff Conventions

Both repos standardize on **Ruff as the single linter + formatter** (replacing black,
isort, flake8, pyupgrade). Nobody runs black at commit time — `ruff format` is the
formatter of record. (`black` still lingers in some legal-ai package dev-deps but no
hook or CI step invokes it; treat it as dead config.)

The two repos sit at opposite ends of a maturity spectrum, so this recipe follows the
richer `agentic-spreadsheet-workflow` config and notes where `legal-ai/backend` is
thinner.

## Observed matrix

| Aspect | agentic-spreadsheet-workflow (single package) | legal-ai/backend (per-service polyrepo) |
|---|---|---|
| Ruff version | `0.15.16`, pinned exactly (dev-dep + pre-commit `rev`) | `v0.9.5` in every `.pre-commit-config.yaml` |
| Rule families | 16 families incl. security (`S`), bugbear, tryceratops | 2–6 families; **no** security rules in ruff |
| line-length | `100` everywhere | mostly `100`; `mini_preview` uses `88`; unconfigured services fall to ruff default `88` |
| target-version | `py313` | `py312` |
| Config home | rich `[tool.ruff]` in `pyproject.toml` | absent in ~half the services (ruff runs defaults) |
| Formatter opts | `docstring-code-format = true` | none |

**Disagreement (honest):** legal-ai is *not* internally consistent — `mini_courtlistener`
and `mini_document_search` select `E,F,I,N,W,UP` (+ ignore `E501`); `mini_late_chunking`
and `mini_preview` select `E,F,I,UP,B,SIM`; and `mini_knowledge`, `mini_workflow`,
`eu_cellar`, `brazil_legislation_apis`, `polish_case_law_apis` ship **no** `[tool.ruff]`
block at all, so ruff-pre-commit lints them with its bare defaults (`E`,`F` only). This is
the anti-pattern the spreadsheet repo's single centralized config avoids.

## Severity philosophy (observed in agentic-spreadsheet-workflow)

The `select`/`ignore` split (`pyproject.toml` `[tool.ruff.lint]`) is deliberately
opinionated — every ignore carries a WHY comment:

```toml
select = [
    "E", "F", "W",   # pycodestyle / pyflakes
    "I",             # isort
    "B",             # bugbear
    "UP",            # pyupgrade
    "SIM",           # simplify
    "C4",            # comprehensions
    "PL",            # pylint
    "RUF",           # ruff-specific
    "N",             # pep8-naming
    "S",             # bandit-style security checks
    "TCH",           # type-checking imports
    "PTH",           # pathlib
    "BLE",           # blind-except: flag except-Exception that swallow errors
    "LOG",           # flake8-logging: correct logger usage
    "TRY",           # tryceratops: exception anti-patterns
]
ignore = [
    "PLR0913",  # too many arguments
    "S101",     # asserts allowed (in tests)
    "TRY003",   # long messages outside exception class — stylistic, too noisy
    "TRY300",   # "move to else block" — stylistic, hurts readability here
]
```

Principle: **turn on broad correctness/security families, then silence only the
individually-justified stylistic false positives** — never blanket-ignore a whole family
to make errors go away. Security (`S`) and exception-hygiene (`BLE`,`TRY`,`LOG`) are
treated as first-class, not optional.

### Per-file relaxation, not global (observed)

Context-specific noise is scoped with `per-file-ignores`, keeping the global ruleset
strict (`pyproject.toml`):

```toml
[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101", "PLR2004"]                       # asserts + magic values ok in tests
"tests/desktop/test_e2e.py" = ["S101","PLR2004","S603","S607"]  # fixed-argv subprocess, no untrusted input
"notebooks/**" = ["E402","E501","F401","B018","PLC0415","N803","N806","PLR0915","PLR1711"]
"scripts/**" = ["S603","S607","T201"]                  # subprocess + print() are the point
```

The `notebooks/**` relaxations exist because marimo generates cell wiring (unusual import
placement, non-PEP8 param names) that must not be "fixed". CLAUDE.md reinforces: *"Per-
directory ruff rules exist (tests/notebooks/scripts) — write each area in its style,
don't add ignores"* and *"No `# noqa` in notebooks."*

## Formatter settings (observed)

```toml
[tool.ruff.format]
docstring-code-format = true   # also format code blocks inside docstrings
```

`extend-exclude` covers generated code so the formatter never touches it:

```toml
extend-exclude = ["notebooks/__marimo__", "src/agentic_spreadsheet_workflow/crbr/models.py"]
src = ["src", "tests"]
```

## Distilled recommended config (prescriptive)

Drop into `pyproject.toml`. Start from the spreadsheet repo's ruleset; adjust
`target-version` to your minimum Python.

```toml
[tool.ruff]
line-length = 100
target-version = "py313"        # or py312
src = ["src", "tests"]
extend-exclude = ["**/generated/**"]   # never lint/format generated code

[tool.ruff.lint]
select = ["E","F","W","I","B","UP","SIM","C4","PL","RUF","N","S","TCH","PTH","BLE","LOG","TRY"]
ignore = [
    "PLR0913",  # too many arguments — DI-heavy code legitimately has many
    "TRY003",   # long exception messages — too noisy
    "TRY300",   # move-to-else — hurts readability
]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101", "PLR2004"]    # asserts + magic numbers are fine in tests
"scripts/**" = ["S603", "S607", "T201"]

[tool.ruff.format]
docstring-code-format = true
```

## Enforcement wiring (observed — both repos)

- **Pre-commit** runs ruff twice, autofixing:
  ```yaml
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.15.16          # legal-ai pins v0.9.5
    hooks:
      - id: ruff-check      # legal-ai id is `ruff` (older hook name)
        args: [--fix]
      - id: ruff-format
  ```
  Keep the pre-commit `rev` == the pinned dev-dep ruff version so local and hook agree.
- **CI** re-runs ruff as a hard gate (no autofix):
  - spreadsheet `qa.yml`: `uv run ruff check .` then `uv run ruff format --check .`
  - legal-ai `ci.yml`: a `backend-precommit` matrix job runs `uv run pre-commit run --all-files` per service.

## Agent-facing instructions (observed)

Only `agentic-spreadsheet-workflow` documents tooling for agents. `CLAUDE.md` gives the
canonical command and rules:

```bash
uv run ruff check --fix . && uv run ruff format .
```

Rules an agent must respect (from CLAUDE.md): write per-directory areas in their existing
style rather than adding ignores; no `# noqa` in notebooks; hit requested scope only (no
drive-by reformatting of untouched files). legal-ai exposes no ruff narrative to agents —
its `.claude/` dirs hold only `settings.local.json` permission lists; READMEs merely say
`uv run pre-commit run --all-files`. *(Inferred:* agents there discover conventions from
the config files, not prose.*)*

## Recommendation for a shared standard

Adopt the spreadsheet repo's centralized, richly-commented `[tool.ruff]` as the template;
port it verbatim into each service (or a shared base) so legal-ai's unconfigured services
stop silently linting at defaults. Standardize `line-length = 100` (retire the `88`
outlier) and pin one ruff version repo-wide via both dev-dep and pre-commit `rev`.
