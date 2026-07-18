---
name: clean-architecture
description: Ports-and-adapters discipline for Python services and libraries — ports as typing.Protocol, the sole composition root, in-memory adapters as production code, errors-as-values (Result/Ok/Err) at port boundaries, and dependency-direction rules. Consult whenever writing or reviewing Python code that touches a boundary (storage, external APIs, clocks), defines or implements a port, wires dependencies, or handles expected failures.
---

# Clean architecture for Python services

Prescriptive rules distilled from production repos. Follow them unless the
project's own `docs/concepts/` records a deviation.

## 1. Ports are `typing.Protocol`

Every dependency boundary (storage, external API, clock, id generation) is a
`Protocol` — methods only, no implementations, no IO.

- **Location**: flat-layout services put all ports in one root-level
  `contracts.py`; `src/`-layout libraries put them in `<area>/ports.py` next to
  the code that owns the boundary.
- **Adapters** are concrete classes that satisfy the port *structurally* — no
  inheritance, no registration. Name them by implementation:
  `InMemoryRunRepo`, `FsRunRepo`, `OpenSearchStore` in `memory.py`,
  `fsrepo.py`, `opensearch_store.py`. The port stays abstract; the adapter
  filename carries the backend prefix.
- **Business code imports the Protocol, never an adapter.** Services take their
  collaborators via `__init__`, typed as the port.
- **Conformance is a mypy assertion**: a `test_ports.py` that assigns each
  adapter to a port-typed variable — the annotation is the test:

  ```python
  runs: RunRepo = InMemoryRunRepo()   # mypy fails if the adapter drifts
  ```

- Write behavioural promises ("a terminal run is immutable — overwriting is a
  `Conflict`") as docstrings on the port method; the contract suite
  (see Enforcement) turns each into a test.

## 2. One composition root

**`main.py` is the ONLY module that imports concrete adapter classes and wires
them together.** No business logic there — construction only.

- FastAPI services: wiring happens in the `lifespan` context manager; expose
  dependencies as getter functions on `app.state`; routers reach them via
  `req.app.state.get_<svc>()` and never construct anything.
- CLI services (Typer): `main.py` builds the app and wires commands.
- Everything below `main.py` receives dependencies through `__init__`
  parameters typed as ports.

If a second module needs to import a concrete adapter, that is a design smell:
either the adapter belongs behind a port, or the wiring belongs in `main.py`.

## 3. In-memory adapters are production code

For each port with a durable adapter, write an in-memory adapter — and keep it
**in the production tree** (`memory.py` next to the port), not in `tests/`.

- It is a real alternate implementation: the default backend the application
  can run on, and simultaneously the seam higher-layer tests use. No mocks, no
  separate fake repo.
- The rule for what goes where: *a real alternate implementation → production
  code; a purely-scripted stand-in (a stepping `FakeClock`, a scripted
  `FakeEngine`) → `tests/fakes.py`.*
- This is only safe because the contract suite proves in-memory and durable
  adapters observably identical — see Enforcement below. Never ship an
  in-memory adapter without binding it to the contract suite.

## 4. Errors as values at port boundaries

Port and service methods that can fail in an *expected* way return
`Result[T, E] = Ok[T] | Err[E]` — hand-rolled (the ~10-line core below; ~30
lines with docstrings in the reference implementation), no library, no
combinators:

```python
@dataclass(frozen=True, slots=True)
class Ok[T]:
    value: T

@dataclass(frozen=True, slots=True)
class Err[E]:
    error: E

type Result[T, E] = Ok[T] | Err[E]
```

- **Closed unions per method**: errors are small frozen dataclasses with a
  `Literal` discriminant (`kind`, `op`, `reason`); each method names its union
  as a `type` alias — `type GetErr = NotFound | StorageError`. The union is the
  checkable contract of how that method can fail.
- **Consume by `isinstance` narrowing + early return**, and **re-wrap** on
  propagation (`return Err(got.error)`, never `return got`) — reconstructing
  `Err(...)` widens `E` to the caller's union.
- **The Err-vs-raise rule**: `Err` for expected outcomes a caller can act on
  (missing id, conflict, invalid user input); `raise` for programmer errors and
  internal invariant violations (illegal transitions, malformed internal
  state). Adapters catch infrastructure exceptions at the boundary and convert
  them (`except OSError as exc: return Err(StorageError("save", str(exc)))`) —
  exceptions never escape an adapter as control flow.
- **Translate `Err` variants to user-facing form (HTTP status, banner, exit
  code) only at the outermost layer**; inner layers only propagate.
- mypy `strict = true` is the enforcement mechanism: `Ok` and `Err` share no
  attributes, so reading `.value`/`.error` off an un-narrowed `Result` is a
  type error. Additionally set `warn_unreachable = true` in `[tool.mypy]` (the
  pack's qa-toolchain prescribes it) to keep over-broad error handlers honest.

Provenance note: errors-as-values and the contract suite are mined from one
reference repo; the other uses classic exceptions. We prescribe the Result
convention pack-wide because it is what makes contract tests able to assert on
failures as data, and mypy enforces it mechanically.

## 5. Dependency direction

```
api / presentation ──▶ services / application      (never the reverse)
services / application ──▶ ports (Protocols)       (never a concrete adapter)
adapters ──▶ ports + domain models                 (implement, don't extend)
main.py ──▶ everything                             (the one wiring exception)
domain ──▷ presentation / adapters / config        (FORBIDDEN)
```

- Ports modules stay dependency-light: error value objects use plain `str`
  fields rather than importing domain models when that would create a cycle.
- Config reads (`os.getenv`) live in `config.py` only; no other module touches
  the environment.

## 6. Enforcement

The architecture is enforced by three mechanisms, in order of authority:

1. **Contract-test suites** — one behavioural spec per port, run against every
   adapter. The full recipe (base class, `make_repo()` hooks, `Test<Adapter>`
   bindings, naming table) is in
   [references/contract-tests.md](references/contract-tests.md). Read it before
   adding a port or a second adapter.
2. **mypy strict** — structural port conformance (`test_ports.py` annotations)
   and exhaustive `Err` handling.
3. **Discipline in review** — the composition-root and dependency-direction
   rules are checked by eyeball; flag any non-`main.py` import of a concrete
   adapter as review-blocking.
