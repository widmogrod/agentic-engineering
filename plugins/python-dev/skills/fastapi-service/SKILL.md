---
name: fastapi-service
description: Opinionated conventions for building FastAPI services in Python — project layout, composition root, per-endpoint packages, ports as Protocols, fail-fast configuration. Consult before implementing or reviewing any code in a FastAPI service scaffolded by /dev:init python fastapi.
---

# FastAPI service conventions

Conventions distilled from production services. Follow them unless the project's
own `docs/concepts/` explicitly records a deviation.

## Layout

Deployable services use a **flat top-level package** — no `src/` (that layout is
reserved for installable libraries):

```
<service>/
├── pyproject.toml
├── main.py              # THE composition root (see below)
├── config.py            # single source of truth for env (see below)
├── api/
│   └── <endpoint>/      # one package per endpoint
│       ├── router.py    # FastAPI router: HTTP concerns only
│       ├── model.py     # request/response pydantic models
│       └── service.py   # the endpoint's use-case logic
├── services/            # domain/infrastructure modules, named by concrete role
│   └── <role>.py        # e.g. opensearch_store.py, embedding.py — never <x>_service.py
└── tests/
    └── api/
        └── test_<endpoint>.py
```

## Rules

1. **`main.py` is the sole composition root.** It is the only module that imports
   concrete adapter classes. Wiring happens in the FastAPI `lifespan` context
   manager; dependencies are exposed via `app.state` getter functions (per-worker).
2. **Ports are `typing.Protocol`.** Boundaries (storage, external APIs, clocks)
   are defined as Protocols; adapters implement them. Business code depends on the
   Protocol, never the adapter.
3. **HTTP files are role-named by location, not filename.** Inside
   `api/<endpoint>/` the files are always `router.py` / `model.py` / `service.py` —
   never `search_router.py`.
4. **All `os.getenv()` calls live in `config.py` only**, validated fail-fast at
   startup. No other module reads the environment.
5. **Routers stay thin.** `router.py` translates HTTP ↔ domain (status codes,
   response models); logic belongs in `service.py`.

## Verifying

Run the QA chain after every change: `uv run ruff check . && uv run ruff format
--check . && uv run mypy . && uv run pytest`.
