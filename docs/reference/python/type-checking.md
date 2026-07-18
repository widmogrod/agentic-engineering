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

# Python Type Checking — Mypy Conventions

Both repos gate on **mypy in `strict` mode**. There is one shared non-negotiable:
**strict everywhere, then relax narrowly per-module with a written reason.** How that
strictness is *expressed* differs sharply.

## Observed matrix

| Aspect | agentic-spreadsheet-workflow | legal-ai/backend |
|---|---|---|
| How strict is set | `strict = true` in `[tool.mypy]` (config-driven) | mostly `--strict` **CLI flag** in pre-commit + CI; pyproject often thin/absent |
| mypy version | dev-dep `mypy==2.1.0`; pre-commit `mirrors-mypy` `v1.18.2` | `mypy>=1.x` per service; CLI-invoked |
| Extra strict flags | `warn_unreachable`, `warn_unused_ignores`, `pretty` | none beyond `--strict`; some set `warn_return_any`, `warn_unused_ignores` |
| Missing-imports | narrow per-module `ignore_missing_imports` overrides | blanket `--ignore-missing-imports` on the CLI for every service |
| pydantic plugin | not used | `plugins = ["pydantic.mypy"]` in courtlistener + document_search |
| Second checker | `[tool.pyright]` kept in sync for IDE | none |

**Key mechanism difference (observed):** legal-ai's pre-commit and CI pass
`--strict --ignore-missing-imports` on the command line, which **overrides** whatever the
per-service `[tool.mypy]` says. So even services whose pyproject has an empty or lax mypy
table (e.g. `brazil_legislation_apis` has only an override stanza; `mini_knowledge`/
`mini_workflow` have no `[tool.mypy]` at all) are still checked strictly in the gate. The
spreadsheet repo instead makes `pyproject.toml` the single authority and invokes bare
`uv run mypy`.

## Strict config (observed — agentic-spreadsheet-workflow)

```toml
[tool.mypy]
python_version = "3.13"
strict = true
warn_unreachable = true
warn_unused_ignores = true
pretty = true
files = ["src", "tests", "notebooks"]
```

`strict = true` bundles `disallow_untyped_defs`, `disallow_incomplete_defs`,
`disallow_untyped_calls`, `warn_return_any`, `no_implicit_optional`, etc.
`warn_unused_ignores` keeps stale `# type: ignore` from accumulating; `warn_unreachable`
catches dead branches; `pretty` is for human-readable output.

## Per-module override philosophy (observed)

Overrides are the interesting part — each is a *scoped* strictness relaxation with a
rationale comment, never a global loosening:

```toml
# 3rd-party libs with no/partial stubs — silence missing-import only:
[[tool.mypy.overrides]]
module = ["marimo.*","openpyxl.*","markdownify.*","playwright.*","dotenv.*", ...]
ignore_missing_imports = true

# SOAP/xsdata libs: also skip following imports so untyped-call checks don't fire:
[[tool.mypy.overrides]]
module = ["zeep.*","xsdata.*","lxml.*","requests.*", ...]
ignore_missing_imports = true
follow_imports = "skip"

# Generated code — mirror of schema, not hand-maintained:
[[tool.mypy.overrides]]
module = "agentic_spreadsheet_workflow.crbr.models"
ignore_errors = true

# marimo notebooks: relax "annotate everything" (cell signatures are generated)
# but KEEP check_untyped_defs so cell BODIES are still type-checked:
[[tool.mypy.overrides]]
module = "notebooks.*"
disallow_untyped_defs = false
disallow_incomplete_defs = false
disallow_untyped_calls = false
warn_return_any = false
check_untyped_defs = true
```

The notebook override is the sharpest lesson: **relax annotation-requirement rules but
keep body-checking on** so the typed library surface imported inside a cell is still
validated. legal-ai's overrides are simpler and cover the same two needs: stub-less
imports (`ignore_missing_imports = true` for `pymupdf`, `markdownify`, etc.) and
loosening tests (`mini_preview` sets `disallow_untyped_defs = false` for `tests.*`).

## Stubs must be installed where mypy runs (observed)

Because pre-commit runs mypy in an **isolated env**, the spreadsheet repo mirrors typed
deps into the hook so it sees the same stubs as `uv run mypy` (`.pre-commit-config.yaml`):

```yaml
- repo: https://github.com/pre-commit/mirrors-mypy
  rev: v1.18.2
  hooks:
    - id: mypy
      additional_dependencies:
        - "pandas>=2.2"
        - "pandas-stubs>=2.2"
        - "pytest>=8.3"
        - "google-genai>=2.8"    # typed; notebooks import it, so must resolve
        - "starlette>=1.3"
        - "keyring>=25.7"
      args: [--config-file=pyproject.toml]
      pass_filenames: false
```

`pass_filenames: false` + `--config-file=pyproject.toml` makes the hook check the whole
project via the config's `files`, not just staged files. legal-ai instead runs mypy as a
`language: system` local hook (`uv run mypy <service> --strict --ignore-missing-imports`),
inheriting the already-synced uv env, so it needs no `additional_dependencies` and sees
installed stubs like `pandas-stubs`, `types-cachetools`, `types-Markdown` directly.

## Distilled recommended config (prescriptive)

```toml
[tool.mypy]
python_version = "3.13"          # your minimum
strict = true
warn_unreachable = true
warn_unused_ignores = true
pretty = true
files = ["src", "tests"]

# Stub-less third-party libs: silence ONLY missing-import.
[[tool.mypy.overrides]]
module = ["some_untyped_lib.*"]
ignore_missing_imports = true

# Generated code: not hand-maintained.
[[tool.mypy.overrides]]
module = "mypkg.generated.*"
ignore_errors = true
```

Prefer config-driven strictness (spreadsheet style) over CLI `--strict` flags (legal-ai
style): the config is discoverable, versioned, and lets IDEs/pyright read the same intent.
Install stubs (`pandas-stubs`, `types-*`) as dev-deps and, if using `mirrors-mypy`, mirror
the typed ones into `additional_dependencies`.

## Enforcement wiring (observed)

- **Pre-commit** — spreadsheet: `mirrors-mypy` `v1.18.2`, `pass_filenames: false`.
  legal-ai: local `mypy-uv` hook running `uv run mypy <dir> --strict --ignore-missing-imports`.
- **CI** — spreadsheet `qa.yml`: `uv run mypy` (bare; config-driven), once, Linux.
  legal-ai `ci.yml`: a `backend-typecheck` matrix job per service runs
  `uv run mypy . --strict --ignore-missing-imports`.

## Second-checker sync (observed — spreadsheet only)

A `[tool.pyright]` block mirrors mypy's *intent* (not rule-for-rule) purely to stop the
IDE flooding diagnostics that the mypy overrides already silence. mypy remains the
authoritative gate; pyright is editor-only. `executionEnvironments` re-relax the notebook
dir the same way the `notebooks.*` mypy override does.

## Agent-facing instructions (observed)

`agentic-spreadsheet-workflow/CLAUDE.md` is explicit:

- Command: `uv run mypy` (strict; src + tests + notebooks).
- *"src-layout, PEP 561, mypy `strict`. Modern syntax: `type X = ...`,
  `dataclass(slots=True)`, `from __future__ import annotations`."*
- *"No `# type: ignore`/`# noqa` in notebooks. Cell parameters are `Any` — import typed
  symbols inside the cell that uses them to get type-checking."*
- Keep `notebooks/__init__.py` (exists for mypy).

legal-ai ships no mypy narrative to agents (only `.claude/settings.local.json` permission
lists); *(inferred)* agents infer strictness from the `--strict` gate and per-service
`[tool.mypy]` tables.
