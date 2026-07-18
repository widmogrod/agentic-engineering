---
type: reference
status: draft
source:
  - legal-ai/backend/mini_courtlistener/config.py
  - legal-ai/backend/mini_document_search/api/app_config.py
  - legal-ai/backend/mini_document_search/api/config.py
  - legal-ai/backend/mini_knowledge/api/config.py
  - legal-ai/backend/mini_preview/config.py
  - agentic-spreadsheet-workflow/src/agentic_spreadsheet_workflow/config.py
---

# Python Service Configuration

How settings, environment variables, and config are handled across the `mini_*`
services and `agentic-spreadsheet-workflow`. Marked **[observed]** / **[standard]** /
**[varies]** / **[inferred]** as in service-layout.md.

## The core rule: one env single-source-of-truth [standard]

Every service designates exactly one module as the sole reader of the environment.
The rule is stated **verbatim** in two independent services
(`mini_courtlistener/config.py` and `mini_document_search/api/app_config.py`):

> This module is the SINGLE source of truth for all environment variable handling.
> All env vars are validated at startup with helpful error messages.
>
> Rules:
> 1. All `os.getenv()` calls MUST be in this file only
> 2. Leaf modules MUST NOT have fallback defaults — require explicit config
> 3. Invalid config MUST fail fast with clear error messages

`agentic-spreadsheet-workflow/src/.../config.py` states the same intent differently —
"the one authority for *what a run sees*" — with a `REGISTRY` of `ConfigItem` records and
a `resolve()` that returns the effective value **and its source** (`env`/`default`/`unset`).

## Fail-fast validation layer [observed]

The richer services (`mini_courtlistener`, `mini_document_search`) implement a small
validation toolkit in the config module rather than pulling a settings framework:

```python
class ConfigurationError(Exception): ...

def _fail(message: str) -> NoReturn:
    print(f"CONFIGURATION ERROR: {message}", file=sys.stderr)
    sys.exit(1)

def _validate_required(name) -> str: ...      # missing → _fail
def _validate_url(name) -> str: ...           # must start http(s):// → _fail
def _validate_int(name, *, min_val, max_val)  # bounds-checked
def _validate_enum(name, enum_class, default) # value must be a member, else lists valid
```

Notable defensive touch in `mini_courtlistener/config.py`: `_validate_required` rejects
non-ASCII values with an explicit hint that em-dashes in inline `.env` comments get parsed
into the value — a real-bug-hardened check. [observed]

Validated values are frozen into an immutable config object, then dependency-injected:
`mini_document_search/api/app_config.py` names the three layers explicitly — "Layer 1:
Raw env vars (untrusted) → Layer 2: AppConfig (validated, immutable) → Layer 3: Services
receive config via dependency injection (no `os.getenv()`)."

## Config object styles [varies]

| Service | Style | Evidence |
|---|---|---|
| `mini_document_search` | `@dataclass` `AppConfig` with `from_env()` classmethod; nested sub-configs (`opensearch`, `chunking`, `embedding`); Pydantic `BaseModel` only for enum-bearing `ProviderConfig` | `api/app_config.py`, `api/config.py` |
| `mini_courtlistener` | frozen `@dataclass` `AppConfig` + `_validate_*` helpers | `config.py` |
| `mini_knowledge` | plain `class Settings:` with class-level typed attributes; `settings = Settings()` module singleton | `api/config.py` |
| `mini_preview` | module-level constants only (`SIZE_PRESETS`, `SUPPORTED_TYPES`) — no env at all | `config.py` |
| `mini_workflow` | per-endpoint `config.py` re-exporting shared `services/dspy_helpers/config.py` constants via `__all__` | `api/summarize/config.py` |
| `agentic-spreadsheet-workflow` | declarative `REGISTRY` of `ConfigItem(kind, aliases, default, required)` + `resolve()` returning value+source | `config.py` |

Takeaway: **the *pattern* (single reader, fail-fast, inject the result) is the standard;
the *mechanism* (dataclass vs plain class vs registry vs Pydantic) is deliberately not
mandated.** Note `pydantic-settings` is a dependency of `mini_document_search` but the
env-reading is still hand-rolled in `app_config.py` — BaseSettings is not the house style.

## Enums for closed value sets [observed]

Closed choices are modeled as `str, Enum` in the config module and validated against:
`EmbeddingProvider`, `SearchMode`, `LabelMode` in
`mini_document_search/api/config.py`, consumed by `_validate_enum`.

## `.env` loading [standard]

- `python-dotenv`'s `load_dotenv()` is called once, near the composition root or at the
  top of the config module — `mini_preview/main.py`, `mini_workflow/main.py`,
  `mini_courtlistener/main.py`, `mini_knowledge/api/config.py`.
- `agentic-spreadsheet-workflow` wraps it as `load_env()` that seeds `os.environ` from a
  repo-root `.env` "if present and is a no-op otherwise", with a committed `.env.example`
  documenting expected keys. A committed `.env.example` is the [inferred] convention.

## Where env is loaded at startup [observed]

In FastAPI services, `AppConfig.from_env()` is called **inside the `lifespan`** ("This is
the ONLY place where config is loaded from env vars" — `mini_document_search/main.py`),
so an invalid environment fails the worker at boot, not lazily at request time. The
`__main__` uvicorn runner loads it a second time only to read `workers`.

Runtime knobs read directly off env at the entrypoint (not through AppConfig) are limited
to process-topology values: `WORKERS` and `OTEL_EXPORTER_OTLP_ENDPOINT`. [varies —
`mini_knowledge`/`mini_preview` read these inline rather than via a config object]

## Adjacent, not covered here

Secret persistence for the packaged desktop app (`desktop/secrets.py` layering a keychain
store over `config.resolve`) and the OpenTelemetry/`instrumentation.py` bootstrap are
related but distinct concerns worth separate passes.
