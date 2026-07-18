---
name: qa-toolchain
description: Set up or run the opinionated Python QA chain in a uv project — ruff (lint+format), mypy strict, pytest with coverage, and the CRAP metric gate (complexity² × (1−coverage)³ + complexity). Use when asked to add quality gates, CRAP metric, linting, or test-coverage discipline to a Python project, or to run/fix the QA chain in a project that already has it.
argument-hint: "[setup|run]"
---

# Python QA toolchain

The chain, in order (order is load-bearing — CRAP reads the `coverage.json`
that pytest writes, so pytest MUST run first):

```
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest                      # writes coverage.json
uv run python scripts/crap.py      # the CRAP gate
```

CRAP flags a function only when BOTH hold: `cc > min-complexity` AND
`crap > threshold`. Fix = add tests or reduce complexity. Never fix by raising
the threshold without the user's explicit consent.

## Setup — retrofit an existing uv project

Adapt to what exists; merge into existing config blocks, never clobber them.
If the project already configures a tool differently, prefer its values and
mention the difference instead of overwriting.

1. **Dev dependencies**: `uv add --dev ruff mypy pytest pytest-cov radon`
   (skip ones already present).

2. **Copy the gate script**: copy `${CLAUDE_SKILL_DIR}/scripts/crap.py` to
   `scripts/crap.py` in the project.

3. **pyproject.toml** — add what's missing:

   ```toml
   [tool.ruff]
   line-length = 100

   [tool.ruff.lint]
   select = ["E", "F", "W", "I", "UP", "B", "S", "TRY", "RUF"]

   [tool.ruff.lint.per-file-ignores]
   "tests/**" = ["S101"]
   # The vendored QA gate script legitimately shells out to `radon` by name.
   "scripts/**" = ["S603", "S607"]

   [tool.mypy]
   strict = true
   # The vendored CRAP gate script is a tool, not project source.
   exclude = ["^scripts/"]

   [tool.pytest.ini_options]
   addopts = ["--cov=<package>", "--cov-report=term-missing", "--cov-report=json"]

   [tool.coverage.run]
   source = ["src"]          # or the package dirs for flat layouts
   branch = true

   [tool.coverage.report]
   fail_under = <floor>      # see step 4

   [tool.crap]
   threshold = 30.0
   min-complexity = 5
   ```

   `<package>` is the import name of the project's top-level package.

4. **Calibrate, don't punish.** On a retrofit, run the chain once BEFORE
   choosing gates:
   - Set `fail_under` to the project's CURRENT coverage (rounded down), not 90.
     The floor prevents regression; raise it as coverage grows (ratchet).
   - If existing functions already exceed CRAP 30, report them to the user and
     ask whether to (a) fix now, (b) start with a higher threshold and ratchet
     down. Do not silently pick a threshold that hides existing risk.

5. **Wire the gates** (ask the user which they want):
   - `Makefile`/`justfile` target or a documented command, minimum.
   - pre-commit: ruff + mypy on `pre-commit` stage; pytest + CRAP on
     `pre-push` stage (they are too slow for per-commit).
   - CI: same commands, same order, one job.

6. **Tell the agent**: add the canonical commands to the project's `CLAUDE.md`
   (create it if absent), including the warning that CRAP is stale unless
   pytest ran first.

## Run

Run the chain in order (above). On CRAP failure, for each offender decide:
mostly-uncovered function → add tests for its branches; genuinely complex →
extract smaller functions, then re-run. Report scores before/after.
