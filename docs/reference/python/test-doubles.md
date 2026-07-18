---
type: reference
status: draft
source:
  - /Users/gabriel/Work/gh/agentic-spreadsheet-workflow (tests/, CLAUDE.md)
  - /Users/gabriel/Work/gh/legal-ai/backend (mini_document_search/tests, packages/*/tests conftest)
---

# Test Doubles: mocking, fakes, and the integration boundary

How the two repos decide what to fake, what to run for real, and where the seam sits.
This is the most substantive divergence between them, so it earns its own file. Markers:
`[observed]` read directly, `[inferred]` deduced.

## The two philosophies

### A. Dependency injection + hand-written fakes (agentic-spreadsheet-workflow)

The repo uses **zero `unittest.mock`** — grep for `MagicMock`/`patch`/`mock` across `tests/`
returns nothing. `[observed]` Instead, impurity is injected and tests pass in fakes.

CLAUDE.md states the design rule directly `[observed]`:

> **DI for everything impure**: fetch takes `get`/`limiter`, resolve takes `search`, classify
> takes `judge`. Tests pass fakes; no real network/LLM.

> **Domain functions are DataFrame-agnostic**: typed models in/out … Errors-as-values in the
> signature: `f(x: T | StageError) -> U | StageError`. Keeps them unit-testable without pandas.

So the seam is a **function parameter**, and the double is a small local class/closure:

```python
class FakeResp:                       # tests/test_pipeline_fetch.py
    def __init__(self, status=200, text="ok", content=b"ok"): ...

def _getter(*, fail=False, status=200):     # returns an async get(url) closure
    async def get(url): ...
    return get

result = await fetch_pages("http://acme.pl", get=_getter(), limiter=HostLimiter())
```

Errors-as-values (`StageError` returned, not raised) means tests assert on returned types
rather than on mock call records: `assert isinstance(result, StageError); assert result.kind == "fetch_blocked"`. `[observed]`

**Contract test suites** verify that fakes and real implementations behave identically.
A `*Contract` base class (not `Test`-prefixed, so uncollected) holds the behaviour checklist;
`TestInMemory*` binds the in-memory repo and `TestFs*` binds the filesystem repo via a
`make_repo` hook — a new adapter gets the whole suite for free. `[observed,
tests/lifecycle/test_repo_contract.py, test_fs_repo_contract.py]`

> The `*Contract` base classes hold the checklist every repo must satisfy … A new adapter
> (filesystem, db) gets full coverage for free by adding one more `Test*` subclass.

This is the in-memory-implementation strategy: the production `InMemory*Repo` is itself the
"fake" for higher layers, and the contract suite guarantees parity with the real `Fs*Repo`.

### B. Mocks for units, real containers for integration (legal-ai/backend)

legal-ai splits doubles by test tier `[observed]`:

- **`tests/unit/` → mock or typed fake, no I/O.** API-endpoint unit tests use
  `MagicMock(spec=OpenSearchStore)`, `MagicMock(spec=EntitySearchService)`, `AsyncMock`, in a
  dedicated `tests/api/conftest.py` whose docstring says: *"These tests mock the
  UnifiedSearchService to test endpoint behavior without requiring OpenSearch."* `[observed]`
- Where behaviour (not just a call) matters, unit tests use **typed fakes** instead of mocks —
  `tests/unit/fakes.py` defines `FakeEmbeddingService(EmbeddingService)` returning deterministic
  vectors and recording calls, and `FakeEntityStore` backed by a dict. `[observed]` So even in
  the mock-friendly repo, real fakes are preferred for stateful collaborators.
- **`tests/integration/` → the real thing via testcontainers.** `tests/conftest.py` spins a real
  `OpenSearchTestContainer(DockerContainer)` (also Redis Stack elsewhere), session-scoped, and
  runs actual queries against it. `[observed]`

```python
class OpenSearchTestContainer(DockerContainer):
    ...
    def start(self):
        super().start()
        wait_for_logs(self, "ML configuration initialized successfully", timeout=180)

@pytest.fixture(scope="session")
def opensearch_container():
    with OpenSearchTestContainer() as c:
        os.environ["OPENSEARCH_ENDPOINT"] = c.get_connection_url()
        yield c
```

- **External HTTP APIs → cached-response fakes**, not live and not mocks. The
  `packages/*/tests/conftest.py` (polish_case_law, brazil_legislation) and `mini_knowledge`
  implement a deterministic on-disk response cache keyed by a hash of
  `url+params+headers`; `REGENERATE_TEST_CACHE=1` refreshes it against the live API.
  `[observed]` This is a record/replay fake for third-party services.
- **Real API keys / third-party models → skip, don't mock.** Integration modules guard with
  `pytestmark = [pytest.mark.integration, pytest.mark.skipif(not is_openai_available(), ...)]`
  and skip when creds/resources are absent. `[observed]`

## Where the integration boundary sits

Both repos draw the same conceptual line — **pure domain logic is always tested for real; the
impure edge (network, LLM, DB, GUI, subprocess) is the boundary** — they just cross it
differently:

- spreadsheet **never crosses it in the default suite**: the edge is injected and faked; real
  crossings live behind the `eval`/`e2e`/`browser` markers and are excluded by default, and
  the impure modules are `omit`-ed from coverage (`pipeline/deps.py`, `desktop/_shell.py`).
  `[observed]`
- legal-ai **crosses it in `integration/`** with real containers and cached HTTP, excluded from
  the default run via `-m "not evaluation"` and directory/marker selection. `[observed]`

## Decision guide (synthesized)

1. **Pure function?** Test it directly, real inputs/outputs. No double.
2. **Impure collaborator with behaviour that matters?** Prefer a **typed hand fake** implementing
   the real interface (both repos do this) over `MagicMock`. Inject it via a parameter (DI).
3. **Just checking an endpoint wires calls through?** A `MagicMock(spec=...)` is acceptable in a
   unit tier (legal-ai) — but keep it in an api/unit-scoped conftest.
4. **Multiple implementations of one interface?** Write a **contract suite** and run every
   implementation (incl. the in-memory fake) through it. `[observed, spreadsheet]`
5. **Real datastore/search engine?** **testcontainers**, session-scoped, per-test unique
   namespace for isolation. `[observed, legal-ai]`
6. **Third-party HTTP API?** **Record/replay cache** keyed by request hash, regenerable via env
   flag. `[observed, legal-ai]`
7. **Real LLM/paid API / GUI / built app?** Put it behind a deselected marker
   (`eval`/`e2e`/`integration`) and **skip when creds/resources absent** — never mock the model
   to fake a passing result.

## The one hard rule both repos share

Do not mock what you can inject-and-fake, and do not fake what you should run for real behind a
marker. `unittest.mock` is a last resort (absent entirely in one repo), reserved for asserting
wiring — never for standing in for stateful behaviour that a typed fake or a real container can
represent honestly.
