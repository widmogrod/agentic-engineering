---
type: reference
status: draft
source:
  - legal-ai/backend/mini_courtlistener
  - legal-ai/backend/mini_document_search
  - legal-ai/backend/mini_knowledge
  - legal-ai/backend/mini_late_chunking
  - legal-ai/backend/mini_preview
  - legal-ai/backend/mini_workflow
  - legal-ai/backend/packages/{eu_cellar,brazil_legislation_apis,polish_case_law_apis}
  - agentic-spreadsheet-workflow/src/agentic_spreadsheet_workflow
---

# Python Service Layout

Prescriptive recipe for laying out a Python service or library, distilled from the
`mini_*` FastAPI services, the installable `packages/`, and the desktop pipeline in
`agentic-spreadsheet-workflow`. Marked **[observed]** where seen verbatim across
services, **[standard]** where it holds across all, **[varies]** where services
diverge, **[inferred]** where extrapolated.

## Two layout shapes (pick by artifact kind) [standard]

The single strongest rule: **deployable services use a flat top-level package; installable
libraries use `src/` layout.**

- **Deployable FastAPI/CLI service** — flat, no `src/`. `main.py` and top-level packages
  (`api/`, `services/`) sit at the repo/service root. Evidence: every `mini_*` service.
- **Installable library** — `src/<dist_name>/` layout with `py.typed`. Evidence:
  `packages/eu_cellar/src/eu_cellar/`, `packages/polish_case_law_apis/src/...`,
  `agentic-spreadsheet-workflow/src/agentic_spreadsheet_workflow/py.typed`.

## Canonical FastAPI service tree [observed]

Annotated from `mini_document_search` (the fullest example) and `mini_workflow`:

```
mini_<service>/
├── main.py                 # Composition root: instrumentation → app → routers → DI wiring → uvicorn runner
├── instrumentation.py      # OpenTelemetry setup, imported FIRST in main.py [4/5 web services]
├── config.py | api/config.py | api/app_config.py   # env single-source-of-truth [varies — see location table]
├── contracts.py            # Protocol boundaries [courtlistener only; = ports.py elsewhere]
├── pyproject.toml          # [tool.hatch.build.targets.wheel] packages = ["api","services"]
├── uv.lock                 # uv-managed lockfile [standard]
├── pytest.ini | [tool.pytest.ini_options]          # [varies]
├── README.md
├── api/                    # HTTP layer — one sub-package per endpoint group
│   ├── __init__.py
│   ├── health/router.py    # health endpoint is its own group [standard]
│   └── <endpoint>/
│       ├── __init__.py
│       ├── router.py       # APIRouter + path operations only
│       ├── model.py        # Pydantic request/response models (SINGULAR filename)
│       ├── service.py      # business logic class <Name>Service [when non-trivial]
│       ├── predictor.py    # DSPy signatures/logic [mini_workflow only]
│       └── config.py       # endpoint-local constants [mini_workflow]
├── services/               # Shared domain logic + adapters (flat modules, role-named)
│   ├── __init__.py         # re-exports public classes via __all__
│   └── <role>.py           # e.g. opensearch_store.py, embedding.py, chunking.py
└── tests/
    ├── conftest.py
    ├── unit/
    ├── integration/        # [most services]
    └── comparison/ | evaluation/   # [some]
```

Ports for the same tree in `mini_courtlistener` (a Typer **CLI**, not FastAPI):
`main.py` (Typer app + wiring), `config.py`, `contracts.py` (Protocols), and packages
`client/`, `services/`, `storage/`, `models/`, `scripts/`.

## Filename conventions [observed]

- **HTTP-layer files are singular and role-suffixed by filename, not by class:**
  `router.py`, `model.py`, `service.py`, `predictor.py`, `config.py`. The suffix is the
  *filename*; the module lives inside its endpoint package (`api/search/router.py`), so
  you do NOT get `search_router.py`. Evidence: `mini_document_search/api/*/`,
  `mini_workflow/api/*/`.
- **`services/` modules are named by role, not with a `_service` suffix:**
  `opensearch_store.py`, `embedding.py`, `filter_builder.py`, `judge_syncer.py`. Classes
  inside may be `EmbeddingService`, but files are the concrete role. Evidence:
  `mini_document_search/services/`, `mini_courtlistener/services/`.
- **`model.py` is singular** in the HTTP layer even when it holds many models. [varies]
  `mini_preview/api/models.py` is the one plural outlier.
- **Installable-library modules are single-word, role-named:** `service.py`,
  `repository.py`, `config.py`, `model.py`, `validators.py`, `utils.py`, `exceptions.py`,
  `<name>_client.py` (e.g. `saos_client.py`). Evidence: `packages/eu_cellar/src/eu_cellar/`.
- **Adapters carry an implementation prefix, ports stay abstract:** in
  `agentic-spreadsheet-workflow/src/.../lifecycle/`, `ports.py` (Protocols) vs `fsrepo.py`,
  `memory.py`, `engine.py`, `fsio.py` (concrete adapters).

## Module boundaries [standard]

A hexagonal / ports-and-adapters discipline recurs, stated explicitly in-repo:

- **`main.py` is the ONLY place that imports concrete classes and wires them.**
  Verbatim from `mini_courtlistener/main.py` docstring: "No business logic here. Only
  imports concrete classes and wires them together." and `contracts.py`: "Only main.py
  imports concrete classes."
- **Boundaries are declared as `typing.Protocol`.** `mini_courtlistener/contracts.py`
  ("Services import from here … never from client/ or storage/"); mirrored by
  `agentic-spreadsheet-workflow/src/.../lifecycle/ports.py` ("Ports — the interfaces the
  pure domain needs … Protocol seams only: no implementations, no IO").
- **`api/` (HTTP) depends on `services/` (domain), never the reverse.** Routers read
  collaborators off `app.state`; services take dependencies via `__init__`.

## FastAPI app assembly + DI wiring [observed]

Both happen in `main.py`. The recurring shape:

1. `setup_early_instrumentation()` is called **before** importing/creating FastAPI
   (comment "Set up instrumentation BEFORE importing FastAPI" with `# ruff: noqa: E402`).
   [4/5 web services — absent in `mini_late_chunking`]
2. A `lifespan` async context manager builds services once per worker, calls
   `setup_telemetry(...)`, and stashes **getter functions** on `app.state`
   (e.g. `app.state.get_unified_search_service = ...`). This is the DI wiring point.
   [standard across web services]
3. `app = FastAPI(title=..., description=..., version=..., lifespan=lifespan)`.
4. `app.include_router(...)` for each router, health first.
5. `if __name__ == "__main__": uvicorn.run("main:app", host="0.0.0.0", port=<fixed>, workers=..., reload=False)`.
   Ports are fixed per service (8007 knowledge, 8008 workflow, 8009 doc-search, 8010 late-chunking, 8011 preview).

Routers reach dependencies via `req.app.state.get_<svc>()` (see
`mini_document_search/api/search/router.py`), keeping routers free of construction.

## Entrypoint conventions [standard]

- **FastAPI services:** `main.py` with a `__main__` guard running uvicorn. No `cli.py`.
- **CLI service:** `main.py` builds a `typer.Typer()` app; `@app.command()` functions.
  (`mini_courtlistener`.)
- **Installable desktop app:** `src/<pkg>/__main__.py` delegating to a `main()` in a
  wiring module (`desktop/entry.py`), so `python -m <pkg>` and the frozen app share one
  launch path. (`agentic-spreadsheet-workflow`.)
- `load_dotenv()` is called near the entrypoint or in the config module. [standard]

## Where services diverge (be honest) [varies]

| Concern | Convention | Outliers |
|---|---|---|
| `api/` sub-structure | one package per endpoint (`api/<ep>/{router,model,service}.py`) | `mini_preview` uses flat `api/*.py` (`preview.py`, `health.py`, `models.py`); `mini_knowledge` mixes `api/<graph>/router.py` with top-level `api/model.py` |
| Config file location | see service-configuration.md | root `config.py` (preview, courtlistener) vs `api/config.py` (knowledge) vs `api/config.py`+`api/app_config.py` two-layer (doc-search) |
| `service.py` present | yes when logic is non-trivial | absent for thin endpoints (health, list) |
| pytest config | `[tool.pytest.ini_options]` in pyproject | standalone `pytest.ini` (knowledge, preview, workflow) |
| instrumentation.py | present, imported first | absent in `mini_late_chunking` |
| Build backend | `hatchling` (mini services) | `uv_build` (eu_cellar), differs per package |
| Test subfolders | `unit/` + `integration/` | `comparison/` (late_chunking), `evaluation/` (packages), flat `tests/*.py` (workflow, courtlistener) |

## Adjacent, not covered here

Dockerfiles live at the backend root as `<service>.Dockerfile` with a matching
`.dockerignore` and per-service `compose.yaml` — a deployment-topology concern worth a
separate pass. Test-layout conventions (unit/integration/evaluation split, testcontainers)
also merit their own reference.
