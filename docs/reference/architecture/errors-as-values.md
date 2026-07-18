---
type: reference
status: draft
source:
  - /Users/gabriel/Work/gh/agentic-spreadsheet-workflow (src/agentic_spreadsheet_workflow/lifecycle/results.py, lifecycle/service.py, lifecycle/fsrepo.py, lifecycle/models.py, lifecycle/ops.py, desktop/server.py, tests/lifecycle/test_repo_contract.py)
  - /Users/gabriel/Work/gh/legal-ai (backend/*, frontend/nogai/src/lib/agent/tools/web-deep-plan/tools/dag-executor.ts)
---

# Errors-as-values: `Result[T, E]` as a prescriptive convention

Expected failures are **data in the signature**, not control-flow exceptions.
A port/service method that can fail in an anticipated way returns
`Result[T, E] = Ok[T] | Err[E]`; the caller must narrow before touching the payload,
so mypy makes ignoring a failure a type error. This is the companion of
[[contract-tests]] (the contract suite asserts on the *returned* `Err` types) — the
two only work together because failures are values the suite can inspect. Markers:
`[observed]` read directly, `[inferred]` deduced.

## 1. The `Result` type — hand-rolled, ~30 lines, no library

Defined in `src/agentic_spreadsheet_workflow/lifecycle/results.py` `[observed]`.
**Not** `returns`, **not** `result` (PyPI), **not** neverthrow — two frozen dataclasses
and a union alias, using PEP 695 type parameters (`class Ok[T]`) and `type` aliases:

```python
@dataclass(frozen=True, slots=True)
class Ok[T]:
    value: T

@dataclass(frozen=True, slots=True)
class Err[E]:
    error: E

type Result[T, E] = Ok[T] | Err[E]
```

API surface — deliberately **minimal** `[observed]`:
- **No combinators.** There is no `.map`, `.and_then`, `.unwrap`, `.unwrap_or`. A
  grep for these across the lifecycle package returns nothing.
- **Consumption is `isinstance` narrowing + early return**, not `match`. The house
  idiom, seen throughout `service.py` `[observed]`:
  ```python
  got = self._templates.get(template_id)
  if isinstance(got, Err):
      return Err(got.error)      # short-circuit; re-wrap (see below)
  template = got.value           # mypy now knows got: Ok[...]
  ```
- **`match`/`case` is reserved for exhaustive dispatch over closed `Literal` sets**
  (statuses, reason keys) with `typing.assert_never` as the total-ness gate — e.g.
  `desktop/views.py`, `reasons.py` `[observed]`. `Ok`/`Err` themselves are narrowed
  with `isinstance`, not `match`.
- **The re-wrap rule** (`return Err(x.error)`, never `return x`): `Err[E]` is
  invariant in `E`, so a helper's narrower `Err[GetErr]` will not type-check as the
  method's wider `Err[RenameTemplateErr]`; reconstructing `Err(...)` widens `E` at the
  boundary. Documented in the `service.py` module docstring `[observed]`.

## 2. Error taxonomy — small, closed, `Literal`-tagged dataclasses

Every error is a `@dataclass(frozen=True, slots=True)` value object carrying the
fields a caller needs to explain the failure. A `Literal` discriminant field
(`kind`, `op`, `reason`) keeps them legible and lets any `match` over them stay
exhaustive `[observed, results.py docstring]`. The vocabulary:

| Error VO | Fields (`[observed]`) | Meaning |
|---|---|---|
| `NotFound` | `kind: Literal["template","analysis","run"]`, `id: str` | no such aggregate |
| `Conflict` | `kind: Literal["run"]`, `id: str`, `detail: str=""` | write violates an invariant (terminal Run is immutable) |
| `StorageError` | `op: Literal["get","find","count","save","delete"]`, `detail: str=""` | backing store IO fault |
| `InspectError` | `reason: Literal["locked","missing","unreadable"]`, `detail: str=""` | input dataset unreadable |
| `TemplateNotReady`, `TemplateInUse`, `NoInputData`, `AlreadyInFlight`, `IllegalTransition`, `InvalidName` | policy-specific fields (ids as `str`, phase as `str`) | application-layer refusals |

Two layers of error VO `[observed]`: **storage/port errors** (`NotFound`, `Conflict`,
`StorageError`) that the repos return, and **application/policy errors**
(`TemplateNotReady`, `AlreadyInFlight`, …) — *expected refusals* the service composes
on top. The policy VOs' phase/id fields are plain `str` so `results.py` needs no
`models` import (a deliberate dependency cut).

**Per-method error unions are named aliases**, one per port/service method — the `E`
slot each method's `Result` uses. This is the taxonomy's backbone `[observed]`:
```python
type GetErr        = NotFound | StorageError
type RunSaveErr    = Conflict | StorageError    # only Run carries Conflict
type SubmitRunErr  = GetErr | ReadErr | InspectError | NoInputData | AlreadyInFlight | RunSaveErr
```
Design rule made explicit in comments: Template/Analysis saves are plain
last-write-wins (`*SaveErr = StorageError` — a concurrent edit just overwrites), so
**no `Conflict` rides their unions**; only a Run's terminal snapshot is immutable, so
only `RunSaveErr` adds `Conflict` `[observed]`. The union is the precise, checkable
contract of *how* a method can fail.

## 3. Err vs. raise — the boundary rule

Return `Err` for **expected outcomes**; `raise` for **programmer errors and truly
exceptional faults**. Concretely `[observed]`:

- **Expected → `Err`.** A missing id, a write conflict, a not-ready template, an
  already-in-flight analysis, invalid *user* input. These are anticipated states the
  caller must handle, so they live in the signature.
- **Programmer error → `raise`.** Illegal state transitions are treated as invariant
  violations: `ops.py` (pure transitions) `raise ValueError`, and its docstring
  states the rule — *"Illegal transitions are invariant violations (programmer bugs),
  so they `raise ValueError` rather than returning an error value."* The service
  **pre-checks** so `ops` never actually raises at runtime (a would-be illegal
  transition surfaces earlier as an `IllegalTransition` *value*) `[observed]`.
- **Internal invariants → `raise`; user input → `Err`.** The same value object can do
  both. `Name.__post_init__` raises `ValueError` (an id/name constructed internally
  must already be valid), while the smart constructor `Name.parse(raw)` returns
  `Result[Name, InvalidName]` because `raw` is *user* input `[observed, models.py]`.
- **Exceptions caught at the adapter boundary become `Err`.** Filesystem adapters wrap
  IO in try/except and convert to the shared vocabulary — `except OSError as exc:
  return Err(StorageError("save", str(exc)))`; a malformed record
  (`CorruptRecordError`, raised internally by the codec's field-by-field validation) is
  caught and returned as `Err(StorageError("get", f"corrupt record: {exc}"))`, never
  escaping the adapter `[observed, fsrepo.py]`. So **the in-memory adapter never raises
  `StorageError`; it exists only so durable adapters share one error vocabulary with
  the ports** `[observed, results.py]`.

Rule of thumb `[inferred from the above]`: *if a caller could reasonably act on it,
it is a `Result` variant; if it means the code itself is wrong, it raises.*

## 4. How Results flow across layers

Ports (`ports.py`) return `Result`; the service composes them, short-circuiting and
re-wrapping to widen the error union at each layer boundary (§1). The presentation
layer is where `Err` variants are **translated for the user** `[observed]`.

This app is server-rendered HTML (Starlette), so translation is
**`Err` variant → localized banner text**, not `Err` → HTTP status code. Each action
has a small total translator in `desktop/server.py` `[observed]`:
```python
def _submit_error_text(error: SubmitRunErr) -> str:
    if isinstance(error, NoInputData):
        return "Brak danych — otwórz plik, wklej listę podmiotów i zapisz."
    if isinstance(error, AlreadyInFlight):
        return "Analiza już się przetwarza — poczekaj na zakończenie."
    return f"Nie udało się uruchomić analizy ({type(error).__name__})."
```
The handler narrows the service `Result`, and on `Err` re-renders the page with the
banner rather than raising `[observed]`. Read-only GETs often degrade silently
(`items = [] if isinstance(got, Err) else got.value`) `[observed]`. Where an HTTP
status *is* emitted it is for a different concern (missing file → `404`, redirects →
`303`), decided by the handler — **not** a mechanical `Err`-variant-to-status map
`[observed]`. The essence is portable: **each `Err` variant maps to a
caller-appropriate representation (banner, status, exit code) at the outermost layer;
inner layers only propagate.** `[inferred]`

## 5. How mypy enforces handling

- **Union with no shared members forces narrowing.** `Ok` and `Err` share no
  `.value`/`.error` attribute, so reading either off a bare `Result` is a type error
  until an `isinstance` narrows it. You cannot "forget" the `Err` arm and reach the
  value `[inferred from the type shape]`.
- **`strict = true` + `warn_unreachable = true`** (`pyproject.toml [tool.mypy]`)
  `[observed]`. `warn_unreachable` flags an over-broad handler branch that can never
  match (e.g. a `Conflict` check on a union that cannot contain one), keeping the
  per-method unions honest.
- **`assert_never` for exhaustive `match`** over closed `Literal` sets: adding a
  variant makes the `case _` arm a type error until every consumer handles it
  `[observed, reasons.py]`. mypy is the authoritative pre-commit gate; pyright config
  only mirrors intent for the IDE `[observed]`.

## 6. How tests assert on Results

Raw `isinstance` narrowing — **no `assert_ok`/`unwrap` test helper exists** (grep
confirms) `[observed]`. The shape, from the contract suite `[observed,
test_repo_contract.py]`:
```python
# success: narrow to Ok, then read .value
assert isinstance(got, Ok) and got.value == saved.value

# failure: narrow to Err AND assert the variant AND its fields
out = repo.save(changed)                       # overwrite terminal Run
assert isinstance(out, Err) and isinstance(out.error, Conflict)
assert out.error.kind == "run" and out.error.id == "r"
```
Assertions check three things: it failed (`Err`), it failed *the right way* (variant
type), and the error's fields carry the right data. Because the failure is a value,
the shared contract suite ([[contract-tests]]) can assert every adapter returns the
*same* `Err` variant for the same misuse — the executable definition of what
`NotFound` vs `Conflict` means.

## The recipe, condensed

1. Model expected failure as a small frozen dataclass with a `Literal` discriminant
   and just-enough fields; name a per-method union alias (`type FooErr = A | B`).
2. Return `Result[T, FooErr]`; never raise for anything a caller could act on.
3. Consume by `isinstance(x, Err): return Err(x.error)` (re-wrap to widen), then use
   `x.value`.
4. Reserve `raise` for programmer bugs (illegal transitions, internal invariants) and
   convert caught infrastructure exceptions to `Err(StorageError(...))` at the adapter
   boundary.
5. Translate `Err` variants to user-facing form (banner / status / exit code) only at
   the outermost layer.
6. Let mypy (`strict`, `warn_unreachable`) enforce that every arm is handled; test by
   narrowing and asserting on the variant + fields.

## Cross-repo note: legal-ai

**Backend does not use this convention** `[observed]`. It is classic
exceptions-for-failure: `ConfigurationError`, `RateLimitError`, `QuotaExhaustedError`,
`ServerError`, `BulkIndexError`, `SAOSAPIError` all subclass `Exception`; no
`Result`/`Ok`/`Err`, no `returns` library. So errors-as-values is a
spreadsheet-repo convention, **not (yet) a shared house standard** — same conclusion
[[contract-tests]] reached about the contract-suite half of the pattern.

## TypeScript equivalent

**No `neverthrow`** anywhere in `legal-ai/frontend` (absent from every non-vendored
`package.json`) `[observed]`. There is one **local, ad-hoc discriminated union** — the
same shape as this convention, built by hand at a boundary that converts caught
exceptions to values `[observed,
frontend/nogai/src/lib/agent/tools/web-deep-plan/tools/dag-executor.ts]`:
```ts
type StepResult<T> =
  | { ok: true; value: T }
  | { ok: false; error: unknown };
// ...
try   { results.set(i, { ok: true, value: await runStep(step, i) }); }
catch (error) { results.set(i, { ok: false, error }); }
```
Mapping to the Python convention: the `Ok[T] | Err[E]` union → a `{ ok: true } |
{ ok: false }` discriminated union; `isinstance` narrowing → narrowing on the `ok`
discriminant; the closed `Literal`-tagged error VOs → a tagged-union error type. A
library (`neverthrow`'s `Result`/`ResultAsync` with `map`/`andThen`) would supply the
combinators this codebase deliberately omits; the hand-rolled discriminated union is
the minimal, dependency-free equivalent and matches the Python style (no combinators,
narrow-and-branch). `[inferred]`
</content>
</invoke>
