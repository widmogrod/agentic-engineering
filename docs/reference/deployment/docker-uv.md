---
type: reference
status: draft
source:
  - /Users/gabriel/Work/gh/legal-ai/backend/mini_document_search.Dockerfile
  - /Users/gabriel/Work/gh/legal-ai/backend/mini_knowledge.Dockerfile
  - /Users/gabriel/Work/gh/legal-ai/backend/mini_workflow.Dockerfile
  - /Users/gabriel/Work/gh/legal-ai/backend/mini_late_chunking.Dockerfile
  - /Users/gabriel/Work/gh/legal-ai/backend/mini_preview.Dockerfile
  - /Users/gabriel/Work/gh/legal-ai/backend/mini_*.Dockerfile.dockerignore
---

# Docker image recipe: Python / uv services

The `mini_*` services under `legal-ai/backend/` share one uv-based image recipe
with small per-service variations. Workspace layout (no root workspace; each
service is its own project root; **build context = `backend/` root**) is covered
in [[uv-workspace]] — this doc is the image recipe. Cited paths are
repo-relative to `backend/`. Marked (observed) vs (inferred).

## The canonical recipe (2 stages)

`mini_knowledge.Dockerfile` is the clean archetype (observed):

```dockerfile
FROM public.ecr.aws/docker/library/python:3.12-slim AS base
RUN python -m pip install --no-cache-dir uv

FROM base AS build
WORKDIR /app/mini_knowledge
COPY ./packages/ /app/packages
COPY ./mini_knowledge/uv.lock ./mini_knowledge/pyproject.toml /app/mini_knowledge/
RUN uv sync --locked
COPY ./mini_knowledge/. /app/mini_knowledge/

FROM base
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 appuser
WORKDIR /app/mini_knowledge
COPY --from=build --chown=appuser:appuser /app /app
EXPOSE 8007
USER appuser
CMD ["uv", "run", "--no-sync", "main.py"]
```

### Element by element

- **Base:** `public.ecr.aws/docker/library/python:3.12-slim` (ECR mirror).
  `mini_preview` uses `...:3.12-slim-bookworm`. (observed)
- **uv install:** `pip install --no-cache-dir uv` into the base layer (uv from
  PyPI, not the `ghcr.io/astral-sh/uv` binary image). (observed)
- **Lockfile-first layering:** copy **only** `uv.lock` + `pyproject.toml`, run
  `uv sync --locked`, *then* copy the rest of the service. So the dependency
  layer is cached and only re-runs when the lock/manifest changes. (observed)
- **`uv sync --locked`:** installs into a project `.venv` from the committed
  lock; `--locked` fails if the lock is stale (no silent re-resolution).
  (observed)
- **Runtime stage:** fresh `base`, adds `curl` (compose healthchecks hit
  `/health`), creates `appuser` (uid 1000), then
  `COPY --from=build --chown=appuser:appuser /app /app` — brings over the whole
  `/app` tree in one layer (venv + service code + any packages). (observed)
- **`CMD ["uv", "run", "--no-sync", "main.py"]`:** `--no-sync` skips
  re-resolution at container start — the venv baked by the build stage is used
  as-is. (observed)
- **Non-root:** `USER appuser` in every runtime stage. (observed — contrast the
  pnpm images which use `node`, and `nogai_db_migrations` which stays root.)

## Mirroring on-disk paths so `../packages/*` resolves

The critical trick: the image reproduces the **same relative geometry** the uv
workspace has on disk. A workspace service declares
`[tool.uv.workspace] members = ["../packages/*"]` (see [[uv-workspace]] §2), so
`../packages` must exist relative to the service dir both on disk and in the
image.

```dockerfile
WORKDIR /app/mini_knowledge          # service at /app/<svc>
COPY ./packages/ /app/packages       # packages at /app/packages
```

`/app/mini_knowledge/../packages` == `/app/packages`. The `members` glob and
`[tool.uv.sources] pkg = { workspace = true }` therefore resolve identically in
the container. (observed / inferred)

**Only workspace services copy `packages/`.** `mini_knowledge` and
`mini_workflow` (the two services that consume shared packages) have
`COPY ./packages/ /app/packages`; the standalone services
(`mini_document_search`, `mini_late_chunking`, `mini_preview`) omit it entirely.
(observed — matches which services declare `[tool.uv.workspace]`.)

## Per-service variations (observed)

- **ML model pre-download** (`mini_document_search`, `mini_late_chunking`): after
  `uv sync`, run a `uv run python -c "...from_pretrained(...)"` to bake the
  HuggingFace model/tokenizer into a build layer, with
  `ENV HF_HOME=/app/models`. Runtime then sets `HF_HUB_OFFLINE=1` /
  `TRANSFORMERS_OFFLINE=1` to forbid network fetches. (observed)
- **`mini_preview` — no lock in repo, generated in-image:** copies only
  `pyproject.toml` and runs `RUN uv lock && uv sync --locked --python
  /usr/local/bin/python3`. This is the one service that does **not** ship a
  committed `uv.lock` to Docker; it locks during build. (observed — a deviation
  from the `--locked`-against-committed-lock norm.)
- **`mini_preview` — multi-target, no plain final stage:** stages are `base` →
  `build` → **`compose`** (local dev, non-root `appuser`) and **`lambda`** (AWS
  Lambda Web Adapter). There is no default final stage; callers must pick a
  `target`. (observed)
  - `compose` target: adds runtime OS deps (`poppler-utils`, `wkhtmltopdf`,
    `libreoffice-writer-nogui`, fonts), non-root, `CMD uv run --no-sync main.py`.
  - `lambda` target: copies `aws-lambda-adapter:0.9.1` into
    `/opt/extensions/`, sets `AWS_LWA_PORT`/`AWS_LWA_READINESS_CHECK_PATH`,
    runs as **root** (no `appuser`), and invokes the venv python directly
    (`/app/mini_preview/.venv/bin/python main.py`) — the comment explains this
    avoids uv recreating the venv under Lambda's interpreter path. (observed)
- **System deps in the build stage** (`mini_preview`): heavy OS packages
  (`poppler-utils`, `wkhtmltopdf`, LibreOffice) are installed in both `build`
  and each runtime target. (observed)
- **No cache mounts.** Unlike the pnpm images, none of the uv Dockerfiles use
  `--mount=type=cache` for the uv cache — they rely purely on layer caching from
  lockfile-first ordering. (observed) CI does cache `~/.cache/uv` separately
  (see [[compose-and-ci]]).

## `.dockerignore` whitelist strategy

Every `mini_*.Dockerfile.dockerignore` follows the same shape: since the context
is the whole `backend/` root, it **un-ignores this service + `packages`** and
**explicitly names every sibling service to exclude**
(`mini_document_search.Dockerfile.dockerignore`, observed):

```
!mini_document_search
!packages
mini_knowledge
mini_late_chunking
mini_preview
mini_workflow
```

...followed by generic exclusions applied to `packages/**` and the service dir
(`.venv`, `tests`, `__pycache__`, `docs`, `.env*`, `*.md`, caches, egg-info,
etc.). Even standalone services (which don't `COPY ./packages/`) still whitelist
`!packages` — harmless but slightly over-broad. (observed)

Note the leading `!service` / `!packages` lines are effectively no-ops on their
own (nothing above them ignored those paths); the real work is the sibling
blacklist keeping the root context small. (inferred)

## Recipe summary

```
backend/                          # build context (NOT a workspace)
├── mini_<svc>.Dockerfile         # 2-stage: base+uv → build (sync --locked) → runtime
├── mini_<svc>/{uv.lock,pyproject.toml,main.py,...}
└── packages/                     # copied to /app/packages ONLY for workspace svcs
```

- Standalone service → copy service only, `uv sync --locked`, run.
- Workspace service → additionally `COPY ./packages/ /app/packages` so
  `../packages/*` resolves.
- ML service → bake model in build layer + offline env at runtime.
- `mini_preview` → the outlier: in-image `uv lock`, multi-`target`
  (compose/lambda), OS deps, ruff line-length 88 vs 100 elsewhere.
