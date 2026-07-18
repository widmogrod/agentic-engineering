---
type: reference
status: draft
source:
  - /Users/gabriel/Work/gh/agentic-spreadsheet-workflow/.pre-commit-config.yaml (observed)
  - /Users/gabriel/Work/gh/agentic-spreadsheet-workflow/.github/workflows/qa.yml (observed)
  - /Users/gabriel/Work/gh/agentic-spreadsheet-workflow/pyproject.toml (observed)
  - /Users/gabriel/Work/gh/agentic-spreadsheet-workflow/CLAUDE.md (observed)
links: ["[[crap-metric]]", "[[linting-formatting]]", "[[type-checking]]", "[[qa-chain-typescript]]", "[[architecture-tests]]"]
---

# QA gate chain — Python recipe

The full ordered quality chain for a `uv`-managed Python library. Beyond
[[linting-formatting]] (ruff), [[type-checking]] (mypy), and the [[crap-metric]]
gate, the distinctive links are **bandit** (static security) and **pip-audit**
(dependency CVEs). Every gate below is **blocking** — none is advisory.

The chain is defined once and mirrored in three places, in the same order:
local **pre-commit** (fast, on `git commit`), local **pre-push** (slow, on
`git push`), and **CI** (`qa.yml`, on push-to-main / PR). CLAUDE.md states the
contract in one line: *"pre-commit: ruff/mypy/bandit. pre-push: pytest, CRAP,
pip-audit."*

## Gate order

| # | Gate | Checks | Blocking | Where wired | Stage |
|---|------|--------|----------|-------------|-------|
| 1 | Hygiene hooks | trailing-whitespace, end-of-file, check-yaml/toml, large-files, merge-conflict, mixed-line-ending | yes | `.pre-commit-config.yaml` (pre-commit-hooks v5) | pre-commit |
| 2 | ruff-check `--fix` | lint + autofix, incl. `S` (bandit-style) rules — see [[linting-formatting]] | yes | pre-commit + `qa.yml` (`ruff check .`) | pre-commit / CI |
| 3 | ruff-format | formatting — see [[linting-formatting]] | yes | pre-commit + `qa.yml` (`ruff format --check .`) | pre-commit / CI |
| 4 | mypy (strict) | types over src + tests + notebooks — see [[type-checking]] | yes | pre-commit + `qa.yml` (`mypy`) | pre-commit / CI |
| 5 | **bandit** | static security scan of `src` | yes | pre-commit + `qa.yml` (`bandit -c pyproject.toml -r src`) | pre-commit / CI |
| 6 | pytest + coverage | unit tests, branch coverage, **fails < 90%**, writes `coverage.json` | yes | pre-push (local) + `qa.yml` | pre-push / CI |
| 7 | **CRAP** | complexity × coverage risk — see [[crap-metric]]; reads `coverage.json`, so must run **after** pytest | yes | pre-push + `qa.yml` (`python scripts/crap.py`) | pre-push / CI |
| 8 | **pip-audit** | dependency CVE scan | yes | pre-push + `qa.yml` (`pip-audit`) | pre-push / CI |

Ordering is load-bearing at two points: format/lint autofix before type-check,
and **pytest before CRAP** (CRAP consumes the `coverage.json` pytest writes —
"Stale unless pytest ran first", per CLAUDE.md).

## bandit specifics

Two layers of bandit-style scanning run, deliberately:

1. **ruff `S` ruleset** — inline, per-file, on every lint pass. `S101` (asserts)
   is globally ignored and re-permitted for `tests/**` and notebooks via
   per-file-ignores. This is the fast first pass.
2. **bandit proper** — the full scanner, deeper than ruff's port. Wired as its
   own hook and CI step:

```yaml
# .pre-commit-config.yaml
- repo: https://github.com/PyCQA/bandit
  rev: 1.8.6
  hooks:
    - id: bandit
      args: [-c, pyproject.toml, -r, src]
      pass_filenames: false
      additional_dependencies: ["bandit[toml]"]
```

Config lives in `pyproject.toml` (`bandit[toml]==1.9.4` pinned in dev deps):

```toml
[tool.bandit]
exclude_dirs = ["tests", "notebooks", ".venv"]
```

Only `src` is recursively (`-r`) scanned — test/notebook code is out of scope
(asserts and demo code would be noise). `pass_filenames: false` means the hook
always scans the whole `src` tree, not just staged files.

## pip-audit specifics

Runs last, as the final QA link (pinned `pip-audit==2.10.0`). It resolves the
installed dependency tree against known-vulnerability advisories and fails the
build on any match.

```yaml
# .pre-commit-config.yaml — local pre-push hook
- id: pip-audit
  name: pip-audit (dependency vulnerabilities)
  entry: uv run pip-audit --skip-editable
  language: system
  pass_filenames: false
  stages: [pre-push]
```

- `--skip-editable` locally: the project's own editable install has no published
  advisory record, so skip it and audit only third-party deps.
- CI (`qa.yml`) runs plain `uv run pip-audit` (no `--skip-editable`).
- Findings feed back into pins: `pyproject.toml` notes *"Floors carry the
  security patches from the pip-audit pass (starlette/cryptography are transitive
  — pinned here so the bundle can't reselect a vulnerable build)."* — i.e. the
  gate is closed by version floors, not by suppression.

## Local vs CI shape

- **pre-commit stage** (hooks 1–5): runs on `git commit`. Fast, deterministic.
- **pre-push stage** (hooks 6–8): `stages: [pre-push]` local hooks — the slow
  suite runs only when you push. `pass_filenames: false` on all three.
- **CI** (`qa.yml`) has two jobs:
  - `gates` (Linux only, runs once): the whole chain 2→8, in order. These are
    OS-independent and deterministic, so paying for one OS is enough.
  - `test` (windows + macos matrix): **pytest only**, with `--no-cov`
    (coverage/CRAP is the Linux job's responsibility). This exists purely to
    prove the suite passes cross-OS.

Run the whole chain locally with `uv run pre-commit run --all-files`.

## Adjacent

[[crap-metric]] · [[linting-formatting]] · [[type-checking]] — gate internals.
[[qa-chain-typescript]] — the sibling TS chain (knip, i18n, property tests).
