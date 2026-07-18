---
type: reference
status: draft
source:
  - /Users/gabriel/Work/gh/agentic-spreadsheet-workflow (tests/, pyproject.toml, CLAUDE.md)
  - /Users/gabriel/Work/gh/legal-ai/backend (mini_*/tests, packages/*/tests, mini_*/pyproject.toml)
---

# Python Testing Conventions

Prescriptive recipe distilled from two repos. Where they agree it is **the standard**;
where they diverge it is called out. Markers: `[observed]` = read directly in a repo,
`[inferred]` = pattern deduced from multiple examples.

## 1. Directory layout

Both repos use a top-level `tests/` directory, **not** colocated `_test.py` next to source.
`src`-layout: source under `src/<pkg>/`, tests under `tests/`.

- **agentic-spreadsheet-workflow** — single `tests/` tree. Flat `test_<topic>.py` for the
  main pipeline (`tests/test_pipeline_fetch.py`, `test_pipeline_decide.py`) plus subpackage
  dirs that loosely mirror `src/` (`tests/xlsx/`, `tests/lifecycle/`, `tests/desktop/`).
  `[observed]`
- **legal-ai/backend** — one `tests/` per service (`mini_*/tests`, `packages/*/tests`), each
  split into `tests/unit/` and `tests/integration/` (some add `tests/api/`, `tests/services/`).
  `[observed]`

**Standard:** `tests/` mirrors the package it covers (per-package in a monorepo of services).
Non-test helper modules live beside tests without a `test_` prefix so pytest skips them:
`tests/_helpers.py`, `tests/unit/fakes.py`, `tests/integration/search_assertions.py`.

## 2. File & function naming

- Files: `test_<subject>.py` `[observed, both]`.
- Functions: `test_<behaviour_in_words>()` — long, sentence-like names describing the
  asserted behaviour, e.g. `test_fetch_pages_blocked_returns_error_with_cost`,
  `test_worker_lock_held_false_for_a_stale_record`. `[observed, spreadsheet]`
- Classes: `class Test<Thing>` only where grouping/inheritance helps (contract suites,
  API groups). Function-style tests are the default; test classes are the exception.
- Helper (non-collected) fns are `_`-prefixed: `_getter`, `_b64`. Fake classes are
  `Fake<Interface>` (`FakeResp`, `FakeClient`, `FakeEmbeddingService`). `[observed]`

## 3. pytest configuration

Config lives in each package's `pyproject.toml` under `[tool.pytest.ini_options]`.
**Shared across both:** `asyncio_mode = "auto"` (pytest-asyncio; async tests need no
per-test decorator) and marker-based deselection of expensive tests by default via
`addopts`.

Fullest example — `agentic-spreadsheet-workflow/pyproject.toml` `[observed]`:

```toml
[tool.pytest.ini_options]
minversion = "8.0"
addopts = [
    "-ra", "--strict-markers", "--strict-config",
    "-m", "not eval and not e2e and not browser",   # cheap tests only by default
    "--cov=agentic_spreadsheet_workflow",
    "--cov-report=term-missing", "--cov-report=json", "--cov-report=xml",
]
testpaths = ["tests"]
pythonpath = ["src"]
asyncio_mode = "auto"
markers = [
    "eval: real-API evaluation tests; deselected by default, run with `-m eval`",
    "e2e: desktop-app end-to-end smoke; run with `-m e2e --no-cov`",
    "browser: Playwright behavioral tests; run with `-m browser --no-cov`",
]
```

`legal-ai/mini_document_search` adds the integration-oriented knobs `[observed]`:

```toml
asyncio_default_fixture_loop_scope = "function"
timeout = 600                       # pytest-timeout: kill hung tests
addopts = "-m 'not evaluation'"     # exclude slow evals by default
filterwarnings = ["ignore::DeprecationWarning"]
markers = ["unit", "integration", "slow", "evaluation"]
```

**Recipe / standard:**
- Always set `--strict-markers` and `--strict-config` (spreadsheet does; adopt everywhere).
- `asyncio_mode = "auto"`.
- Register every marker in `markers = [...]`; never use an unregistered marker.
- Deselect expensive tiers by default in `addopts` (`-m "not <tier>"`); opt in explicitly.
- **Marker vocabulary differs** and is the main divergence: spreadsheet tiers by
  *cost/environment* (`eval`, `e2e`, `browser`); legal-ai tiers by *kind* (`unit`,
  `integration`, `slow`, `evaluation`). Choose one taxonomy per repo. `[observed]`
- Run xdist (`-n auto`) for unit tests only; integration/testcontainer tests run serially
  (`-n 0`) because of session-scoped shared containers. `[observed, legal-ai comment]`

## 4. Marker application

- Per-function decorator: `@pytest.mark.browser` (spreadsheet), `@pytest.mark.unit` (legal-ai).
- **File-level via `pytestmark`** for whole integration modules, combined with skip guards
  `[observed, legal-ai]`:

```python
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not is_openai_available(), reason="OpenAI API key not configured"),
]
```

## 5. Fixtures & conftest organization

- **conftest placement:** one `tests/conftest.py` per package for shared fixtures; a nested
  `tests/api/conftest.py` holds fixtures specific to that subtree (e.g. mock-based API
  fixtures separate from the container-backed ones above). `[observed, legal-ai]`
  - Divergence: spreadsheet has **no conftest.py at all** — fixtures are defined inline in the
    test module that uses them (only ~6 `@pytest.fixture` in the whole suite). Fakes are plain
    functions/classes, not fixtures. `[observed]`
- **Fixture scoping for expensive resources:** `scope="session"` for the container and its
  derived config; `scope="function"` for anything holding per-test state, with a unique id per
  test for isolation. `[observed, legal-ai]`

```python
@pytest.fixture(scope="session")
def opensearch_container(): ...          # start once, share
@pytest.fixture(scope="function")
async def opensearch_store(opensearch_config, opensearch_container):
    test_user_id = f"test_{uuid.uuid4().hex[:8]}"   # per-test isolation → parallel-safe
    ... ; yield store, test_user_id ; await store.delete_index(test_user_id)
```

- **Isolation over teardown-trust:** each test gets a unique namespace (unique `user_id` →
  unique index) so parallel runs don't collide; cleanup still runs in the `yield` teardown but
  swallows errors. `[observed, legal-ai]`
- **Fixtures return typed data or `(obj, id)` tuples**, with docstrings explaining the isolation
  contract. `[observed]`
- **Reusable skip decorators** are module-level `pytest.mark.skipif(...)` bound to a name and
  applied where needed: `requires_jina_tokenizer = pytest.mark.skipif(not cached, ...)`. `[observed]`

## 6. Parametrization

- `@pytest.mark.parametrize` is the default way to cover input variants (51 uses in the
  spreadsheet suite). Prefer one parametrized test over many near-duplicate functions. `[observed]`
- Per-file ruff ignores `PLR2004` (magic numbers) under `tests/**` so table-driven cases stay
  readable. `[observed, spreadsheet]`

## 7. Coverage configuration

Only **agentic-spreadsheet-workflow** configures coverage; legal-ai has none (no
`[tool.coverage]`, no `--cov`). This is a real divergence, not an omission on our part. `[observed]`

Spreadsheet standard `[observed]`:

```toml
[tool.coverage.run]
source = ["src"]
branch = true            # branch coverage, not just line
omit = ["*/crbr/models.py", "*/pipeline/deps.py", "*/desktop/_shell.py", ...]

[tool.coverage.report]
show_missing = true
skip_covered = true
fail_under = 90          # gate: build fails below 90%
```

- Measure `src`, `branch = true`.
- `omit` = generated code and the impure I/O boundary (real network/LLM/GUI/subprocess glue,
  entry points). The rule: **cover pure/domain logic; exclude the thin impure edge** that is
  only exercised by `eval`/`e2e` tiers.
- `fail_under = 90`; enforced in pre-push. New code needs tests (CLAUDE.md). `[observed]`
- Emits `json`+`xml` reports because the CRAP gate consumes `coverage.json` (see below).

## 8. Relation to the CRAP gate (pointer only)

Spreadsheet layers a **CRAP** metric on top of coverage: `scripts/crap.py` reads
`coverage.json` + radon complexity and fails when a function has `cc > 5 AND crap > 30`
(`[tool.crap] threshold = 30.0`, `min-complexity = 5`). Pytest must run first to refresh
`coverage.json`. This is why coverage emits JSON. legal-ai has no CRAP gate. Full treatment is
out of scope here — covered by a separate pass. `[observed]`

## 9. Quick divergence table

| Aspect | spreadsheet | legal-ai |
|---|---|---|
| unit/integration split | by cost markers, flat-ish tree | by directory `unit/` vs `integration/` |
| conftest.py | none (inline fixtures) | per-package + nested |
| test doubles | DI + hand fakes, **zero `unittest.mock`** | `MagicMock`/`AsyncMock` + testcontainers + fakes |
| coverage / CRAP | 90% gate + CRAP | none |
| marker taxonomy | eval/e2e/browser | unit/integration/slow/evaluation |
| async | `asyncio_mode=auto` | `asyncio_mode=auto` (same) |

See `test-doubles.md` for the mocking-vs-fakes-vs-real philosophy.
