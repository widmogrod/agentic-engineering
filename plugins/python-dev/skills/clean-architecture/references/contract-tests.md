# Contract-test suites: the enforcement recipe

One behavioural spec per port, parametrised by an adapter factory, run once per
adapter. This is what makes "the in-memory adapter is production code" safe:
the suite is the executable definition of what *satisfies the port* means, so
every adapter is substitutable by construction.

## The four moving parts

1. **Port** — a `typing.Protocol` (methods only, no IO), returning
   `Result[T, E]` so the suite can assert on failures as values.
2. **Adapters** — concrete classes satisfying the port structurally. The
   in-memory one lives in the production tree.
3. **Contract suite** — a base class holding the behavioural checklist plus
   abstract factory hooks. It is **NOT `Test`-prefixed**, so pytest never
   collects it directly.
4. **Binding subclasses** — one `Test<Adapter>` class per adapter, each
   supplying `make_repo()` and inheriting the entire suite.

## Worked example (signature altitude)

The port, in `ports.py` — behavioural promises as docstrings:

```python
class RunRepo(Protocol):
    def get(self, run_id: RunId) -> Result[Run, GetErr]: ...
    def find(self, query: RunQuery, page: PageRequest) -> Result[Page[Run], ReadErr]: ...
    def save(self, run: Run) -> Result[Run, RunSaveErr]:
        """A terminal run is an immutable snapshot — overwriting is a Conflict."""
    def delete(self, run_id: RunId) -> Result[None, DeleteErr]: ...
```

The contract suite, in `tests/<area>/test_run_repo_contract.py`:

```python
class RunRepoContract:                       # not Test-prefixed → not collected
    def make_repo(self) -> Any:              # abstract factory hook, NOT a
        raise NotImplementedError            # pytest fixture — every test calls
    def make_run(self, key: str) -> Run:     # it for a fresh instance
        raise NotImplementedError

    def test_save_get_round_trip(self) -> None:
        repo = self.make_repo()
        saved = repo.save(self.make_run("a"))
        got = repo.get(RunId("a"))
        assert isinstance(got, Ok) and got.value == saved.value

    def test_overwrite_terminal_run_is_conflict(self) -> None:
        ...  # assert isinstance(out, Err) and isinstance(out.error, Conflict)
             # and out.error.kind == "run" and out.error.id == "a"
    # ...empty-store, pagination, ordering, malformed-cursor tests — all
    # driving ONLY the port surface, via the hooks
```

The bindings — the only collected classes:

```python
# same file — the in-memory binding
class TestInMemoryRunRepo(RunRepoContract):
    def make_repo(self) -> InMemoryRunRepo:
        return InMemoryRunRepo()

# tests/<area>/test_fs_run_repo_contract.py — the durable binding, real IO
# (_FsTempMixin: a small mixin whose _fresh_layout() hands each call its own
#  tempfile directory, keeping bindings isolated without pytest fixtures)
class TestFsRunRepo(_FsTempMixin, RunRepoContract):
    def make_repo(self) -> FsRunRepo:
        return FsRunRepo(self._fresh_layout())   # each call → own temp dir
```

Rules that make this work:

- **Every test calls `self.make_repo()`** for a fresh, isolated instance —
  never share state between tests via fixtures.
- **Assertions check three things** on failure paths: it failed
  (`isinstance(out, Err)`), it failed the *right way* (variant type), and the
  error's fields carry the right data. Raw `isinstance` narrowing — no
  `assert_ok`/`unwrap` helpers.
- **Adapter-specific failure modes live beside the binding**, not in the
  suite: the fs binding file adds plain `test_*` functions for corrupt JSON,
  failed atomic writes, odd-character ids — edges the in-memory backend cannot
  produce. Shared behaviour in the suite; adapter-only edges next to the
  binding.
- **Layer contracts via inheritance** when aggregates differ: a shared
  `RepoContract` base plus per-aggregate contracts
  (`RunRepoContract(RepoContract)`) that add aggregate-specific tests (e.g.
  terminal-immutability only for runs, last-write-wins only for templates).
- **The same shape works for non-repo ports**: an `IdGenContract` bound by
  `TestFakeIdGen` and `TestUuidIdGen` runs one checklist against both the
  deterministic fake and the real generator.

## Naming & location conventions

| Element | Convention | Location |
|---|---|---|
| Port | `class <Name>(Protocol)`, methods only | `contracts.py` (flat service) / `src/<pkg>/<area>/ports.py` (library) |
| In-memory adapter | `InMemory<Name>` — production code | `memory.py` next to the port |
| Durable adapter | `Fs<Name>` / `<Backend><Name>` | `fsrepo.py` / `<backend>_store.py` |
| Contract base | `<Name>Contract` — NOT `Test`-prefixed | `tests/<area>/test_<name>_contract.py` |
| Abstract hook | `make_<thing>()` raising `NotImplementedError` | on the contract base |
| Binding | `class Test<Adapter>(<Name>Contract)` | contract file (in-mem) / adapter-specific file (durable) |
| Adapter-only edges | plain `test_*` functions | beside the binding |
| Structural conformance | port-typed annotation assignments | `tests/<area>/test_ports.py` |

## What the pattern buys

- **Substitutability (LSP) by construction** — every adapter passes the same
  behavioural spec, so swapping adapters cannot change observed behaviour.
- **Fake-realism** — the "fake" that higher-layer tests use is a
  contract-verified production adapter, not a hand-rolled double that drifts
  from reality.
- **Free coverage for new adapters** — a db adapter needs only one new
  `Test<Adapter>` subclass with a `make_repo()` to inherit the whole checklist.
- **Executable interface docs** — the suite is the machine-checkable meaning
  of the port's semantics: what `NotFound` vs `Conflict` means, cursor edge
  behaviour, ordering guarantees.

## Layer enforcement beyond contracts

The mined reference repos enforce dependency direction with **discipline +
contract tests + mypy strict** — no automated import checker. (The TypeScript
sibling runs `tsarch` architecture tests; Python has no dogfooded equivalent
here.)

If you want mechanical layer enforcement, [import-linter](https://import-linter.readthedocs.io/)
can express "only `main.py` imports adapters" and "domain must not import
infrastructure" as CI-checked contracts. **NOT yet dogfooded in our reference
repos** — treat it as an optional addition, propose it to the user rather than
adding it silently, and never let it substitute for the contract suite (it
checks imports, not behaviour).

## Provenance

The class-based contract-suite mechanism is mined from one reference repo; the
other defines Protocol ports and in-memory fakes but has no shared behavioural
suite bound to multiple adapters — its fake/real parity is trusted via
`MagicMock(spec=...)` plus integration-tier containers. We prescribe the
contract suite pack-wide because it is the only mechanism of the three that
*proves* adapter parity instead of assuming it.
