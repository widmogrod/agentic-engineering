---
type: reference
status: draft
source:
  - /Users/gabriel/Work/gh/agentic-spreadsheet-workflow (src/agentic_spreadsheet_workflow/lifecycle/, tests/lifecycle/)
  - /Users/gabriel/Work/gh/legal-ai/backend (mini_courtlistener/contracts.py, mini_document_search/services/, tests/unit/fakes.py)
---

# Contract-test suites for ports & adapters

A prescriptive recipe for the pattern that binds a `typing.Protocol` **port** to
multiple **adapters** and proves they behave identically with one shared
behavioural suite. Distinct from generic testing mechanics — see [[testing]] and
[[test-doubles]] for pytest/fakes conventions this builds on. Markers: `[observed]`
read directly, `[inferred]` deduced.

This is an architectural convention, not a testing trick: the port is the seam the
pure application layer depends on; the contract suite is the executable definition of
what "satisfies the port" means, so any adapter (in-memory, filesystem, db) is
substitutable (LSP) by construction.

## The four moving parts

1. **Port** — a `Protocol` (methods only, no IO). `[observed]`
2. **Adapters** — concrete classes that structurally satisfy the port. The
   *in-memory* one is production code, not a test double. `[observed]`
3. **Contract suite** — a non-`Test`-prefixed base class holding the behavioural
   checklist plus abstract factory hooks. `[observed]`
4. **Binding subclasses** — one `Test<Adapter>` per adapter, implementing the hooks;
   each inherits the whole suite. `[observed]`

## 1. Port: a Protocol, IO-free, in `…/ports.py`

Ports live in their own module of pure interfaces. From
`src/agentic_spreadsheet_workflow/lifecycle/ports.py` `[observed]` — the module
docstring states the discipline: *"These are `Protocol` seams only: no
implementations, no IO … the adapter layer satisfies them. Tests pass fakes."*

```python
class RunRepo(Protocol):
    def get(self, run_id: RunId) -> Result[Run, GetErr]: ...
    def find(self, query: RunQuery, page: PageRequest) -> Result[Page[Run], ReadErr]: ...
    def count(self, query: RunQuery) -> Result[int, ReadErr]: ...
    def save(self, run: Run) -> Result[Run, RunSaveErr]: ...   # terminal run immutable → Conflict
    def delete(self, run_id: RunId) -> Result[None, DeleteErr]: ...
```

Conventions `[observed]`:
- Methods return a `Result[T, Err]` (errors-as-values), never raise for expected
  failures — so the contract can assert on returned types.
- Behavioural promises that adapters must share (e.g. *"a terminal run is an
  immutable snapshot — overwriting with a different value is a `Conflict`"*) are
  written as docstring comments on the port method; the contract suite turns each
  into a test.
- Conformance is checked by mypy structurally: `test_ports.py` assigns each adapter
  to a port-typed variable (`runs: RunRepo = InMemoryRunRepo()`) — *"the annotations
  are the assertion"*. `[observed, tests/lifecycle/test_ports.py]`

## 2. Adapters: in-memory is production, not a fake

`InMemoryRunRepo` lives in `src/…/lifecycle/memory.py`, NOT in `tests/`. Its
docstring: *"These are real (not test) implementations."* `[observed]` It is the
default adapter the application runs on and simultaneously the seam higher layers
fake against. The filesystem twin `FsRunRepo` lives in `src/…/lifecycle/fsrepo.py`
(*"the durable `ports` adapters"*). Shared query/pagination logic sits in
`_query.py` so both adapters share a byte-identical implementation — the contract
suite is what guarantees that parity holds. `[observed]`

## 3. Contract suite: checklist + abstract hooks

`tests/lifecycle/test_repo_contract.py`. The base class is **not** `Test`-prefixed,
so pytest does not collect it directly. Docstring: *"The `*Contract` base classes
hold the checklist every repo must satisfy … A new adapter (filesystem, db) gets
full coverage for free by adding one more `Test*` subclass."* `[observed]`

```python
class RepoContract:                              # not Test-prefixed → not collected
    kind: str = ""
    def make_repo(self) -> Any: raise NotImplementedError      # abstract factory hook
    def make_entity(self, key, *, order=0.0): raise NotImplementedError
    def wrap_id(self, key): raise NotImplementedError
    def match_all(self): raise NotImplementedError

    def test_save_get_round_trip(self) -> None:               # shared behaviour method
        repo = self.make_repo()
        saved = repo.save(self.make_entity("a"))
        got = repo.get(self.wrap_id("a"))
        assert isinstance(got, Ok) and got.value == saved.value
    # …empty-store, pagination, ordering, malformed-cursor tests, all via the hooks
```

Structure `[observed]`:
- **Abstract fixture = a `make_repo()` method** that raises `NotImplementedError`,
  not a pytest fixture. Every test calls `self.make_repo()` for a fresh instance.
  Auxiliary hooks (`make_entity`, `wrap_id`, `match_all`, `entity_key`) abstract away
  the aggregate type so one suite serves Template/Analysis/Run.
- **Shared test methods** are ordinary `test_*` methods on the base — they run once
  per binding subclass, driving only the port surface.
- **Layered contracts via inheritance:** a `PlainSaveContract(RepoContract)` adds
  last-write-wins tests mixed into only Template+Analysis; `RunRepoContract` instead
  adds a terminal-immutability test. Per-aggregate contracts
  (`TemplateRepoContract(PlainSaveContract)`) fill in the hooks and add
  filter-specific tests.

## 4. Binding: one `Test<Adapter>` subclass per adapter

The subclass is the *only* collected class; it supplies `make_repo` and inherits the
suite. `[observed]`

```python
# in test_repo_contract.py — the in-memory binding
class TestInMemoryRunRepo(RunRepoContract):
    def make_repo(self) -> InMemoryRunRepo:
        return InMemoryRunRepo()

# in test_fs_repo_contract.py — the filesystem binding, same suite, real IO
class TestFsRunRepo(_FsTempMixin, RunRepoContract):
    def make_repo(self) -> FsRunRepo:
        return FsRunRepo(self._fresh_layout())   # each call → own temp dir
```

`test_fs_repo_contract.py` imports the contract classes and binds the fs adapters,
then adds *fs-only edge tests* the in-memory backend cannot produce (corrupt JSON,
directory-where-a-file-should-be, failed atomic write, odd-character ids). `[observed]`
So: shared behaviour lives in the suite; adapter-specific failure modes live beside
the binding.

The same shape recurs for non-repo ports: `IdGenContract` in `test_ports.py` is bound
by `TestFakeIdGen` and `TestUuidIdGen`, running the "N distinct non-empty ids" checklist
against both the deterministic fake and the real uuid generator. `[observed]`

## How in-memory fakes double as production seam + test infra

The key move `[observed]`: the in-memory adapter is *real production code* in `src/`.
Higher layers (queue, services) depend on the port; in tests they are handed
`InMemoryRunRepo` — no mock, no separate fake repo. The contract suite is what makes
this safe: it proves `InMemoryRunRepo` and `FsRunRepo` are observably identical, so a
service tested against the in-memory one behaves the same in production against the
filesystem one. Purely-scripted collaborators that have no production analogue (a
stepping `FakeClock`, a scripted `FakeEngine`) DO live in `tests/lifecycle/fakes.py`;
the distinction is: *a real alternate implementation → `src/`; a scripted stand-in →
`tests/`.* `[observed, fakes.py docstring]`

## Guarantees the pattern buys

- **Substitutability / LSP** — every adapter passes the same behavioural spec, so
  swapping adapters cannot change observed behaviour. `[inferred from suite design]`
- **Fake-realism** — the "fake" used by higher-layer tests is a contract-verified
  production adapter, not a hand-wave that drifts from reality. `[observed]`
- **Free coverage for new adapters** — a db adapter needs only a new `make_*` hook +
  subclass to inherit the entire checklist. `[observed, docstring]`
- **Executable interface docs** — the suite is the machine-checkable definition of the
  port's semantics (what `NotFound` vs `Conflict` means, cursor edge behaviour).

## Naming & location conventions (the recipe)

| Element | Convention | Location |
|---|---|---|
| Port | `class <Name>(Protocol)`, methods only | `src/<pkg>/<area>/ports.py` |
| In-memory adapter | `InMemory<Name>` (production) | `src/<pkg>/<area>/memory.py` |
| Durable adapter | `Fs<Name>` / `<Backend><Name>` | `src/<pkg>/<area>/fsrepo.py` |
| Contract base | `<Name>Contract` (NOT `Test`-prefixed) | `tests/<area>/test_<name>_contract.py` |
| Abstract hook | `make_<thing>()` raising `NotImplementedError` | on the contract base |
| Binding | `class Test<Adapter>(<Name>Contract)` | contract file (in-mem) / adapter-specific file (fs) |
| Adapter-only edges | plain `test_*` functions | beside the binding |

## Language-agnostic essence (TypeScript + vitest)

The pattern is not Python-specific. In TS the port is an `interface`, the contract
suite is a function taking a factory, and each adapter calls it: `[inferred]`

```ts
interface RunRepo {
  get(id: RunId): Promise<Result<Run, GetErr>>;
  save(run: Run): Promise<Result<Run, SaveErr>>;
}

// contract suite: a function of the adapter factory (the "make_repo" hook)
export function runRepoContract(makeRepo: () => RunRepo) {
  describe("RunRepo contract", () => {
    it("round-trips save→get", async () => {
      const repo = makeRepo();
      const saved = await repo.save(makeRun("a"));
      expect(await repo.get(wrapId("a"))).toEqual(ok(saved.value));
    });
    it("rejects overwriting a terminal run with Conflict", async () => { /* … */ });
  });
}

// bindings — one per adapter, same suite
runRepoContract(() => new InMemoryRunRepo());
runRepoContract(() => new FsRunRepo(freshTmpDir()));
```

Mapping: `Protocol` → `interface`; the `make_repo()` abstract method → a factory
callback; the non-collected `*Contract` base class → the exported `describe`-wrapping
function; each `Test<Adapter>` subclass → one call of that function. The essence is
constant: **one behavioural spec, parametrised by an adapter factory, invoked once per
implementation.**

## Cross-repo note: legal-ai/backend

legal-ai uses the *ports* half of this pattern but **not** the class-based contract
suite. `[observed]` It defines Protocol ports explicitly
(`mini_courtlistener/contracts.py` — *"Protocol definitions for all dependency
boundaries. Clients and storage implement these Protocols"*; `EntityStoreProtocol` in
`mini_document_search/services/entity_store.py`) and hand-written in-memory fakes
(`FakeEntityStore`, `FakeEmbeddingService` in `tests/unit/fakes.py`). But there is **no
shared behavioural base class run against multiple implementations** — no
`class Test…(…Contract)` binding exists in the backend. Parity between fake and real is
instead trusted via `MagicMock(spec=…)` at unit tier and real containers at integration
tier (see [[test-doubles]]). So the contract-suite mechanism is a spreadsheet-repo
convention, not (yet) a shared house standard. `[observed]`
