---
type: reference
status: draft
source:
  - /Users/gabriel/Work/gh/legal-ai/compose.yaml
  - /Users/gabriel/Work/gh/legal-ai/compose.experiments.yaml
  - /Users/gabriel/Work/gh/legal-ai/backend/mini_document_search/compose.yaml
  - /Users/gabriel/Work/gh/legal-ai/.github/workflows/ci.yml
---

# Compose & CI: how images are composed and built

How the pnpm ([[docker-pnpm]]) and uv ([[docker-uv]]) images are wired together
locally (compose) and validated in CI. Cited paths are repo-relative to the
`legal-ai/` root. Marked (observed) vs (inferred).

## Local composition — root `compose.yaml`

One root `compose.yaml` builds and runs the whole app stack. Each service points
`build.context` at a **subdir** (`frontend/` or `backend/`) and names the
Dockerfile by file — matching the "context = workspace root" convention.
(observed)

```yaml
services:
  mini_workflow:
    build:
      context: backend/
      dockerfile: mini_workflow.Dockerfile
  nogai:
    build:
      context: frontend/
      dockerfile: nogai.Dockerfile
  mini_preview:
    build:
      context: backend/
      dockerfile: mini_preview.Dockerfile
      target: compose          # multi-target image → pick the compose stage
```

Observations:

- **`include:`** pulls in `backend/mini_document_search/compose.yaml` — a nested
  compose file that owns `mini_document_search` **plus its OpenSearch cluster**.
  Note that nested file uses `context: ../` (i.e. `backend/`) — same effective
  context, expressed relative to its own location. (observed)
- **`target: compose`** selects the non-root local stage of the multi-target
  `mini_preview` image (its Lambda target is not used by compose). (observed)
- **Env contract:** services load `env_file: <subdir>/<svc>/.env` and set
  service-discovery URLs via `environment:` (e.g.
  `NOGAI_BACKEND_MINI_WORKFLOW_BASE_URL: http://mini_workflow:8008`). The empty
  `ENV` secrets declared in the Dockerfiles are filled here. (observed)
- **Healthchecks** target each image's `/health` (backends via `curl`, added to
  the runtime layer for exactly this purpose) or `/api/health` (nogai via
  `wget`). (observed)
- **Orchestration via `depends_on` + conditions:** `nogai` waits on all
  backends `service_healthy`, `nogai_db_migrations` `service_completed_successfully`,
  and `outbox_processor` `service_healthy` — the migrations image is a run-once
  task (`restart: "no"`), gating app start. (observed)
- **DB:** `postgres:17` started with `wal_level=logical` + replication slots —
  required for the Debezium/outbox CDC path. (observed / inferred)

### `compose.experiments.yaml`

A **separate, standalone** compose file for experiment infra: Neo4j, a 2-node
OpenSearch cluster + dashboards, Kafka (KRaft) + kafka-ui, and a Debezium
connect worker. (observed)

- It references `frontend/nogai/graphql.Dockerfile` for a `graphql` service, but
  **that Dockerfile does not exist** on disk (a fourth frontend build strategy
  is *referenced but absent*) — likely stale. (observed — flag before relying
  on it.)
- It also references a `nogai_db` service that is defined in the root
  `compose.yaml`, so this file is meant to be layered, not run alone. (inferred)

## CI — `.github/workflows/ci.yml`

**CI does not build or push any Docker image.** It validates source via
per-member matrix jobs on `pull_request` to `main`. (observed) The Docker images
are built elsewhere — comments in `nogai.Dockerfile` name **AWS CodeBuild** as
the `--build-arg` caller, so image builds live in CodeBuild / CDK, not GitHub
Actions. (inferred)

What CI does run (all `pnpm install --frozen-lockfile` / `uv sync` based, mirroring
the Dockerfile install commands):

- **Frontend** (pnpm 10.14.0, node 24.7.0, `cache: pnpm`): matrix tests across
  `packages/{logger,event-sourcing-core,agent-react,knowledge-graph}` + `nogai`;
  plus typecheck, lint (+ `knip`), and i18n jobs. Every job runs
  `pnpm --filter './packages/*' -r build` first — the same
  "build workspace packages before the app" ordering the `nogai` image encodes.
  (observed)
- **Backend** (uv via `astral-sh/setup-uv@v5`, python 3.12, `actions/cache` on
  `~/.cache/uv` keyed by `hashFiles('<path>/uv.lock')`): per-service matrix for
  unit tests, integration tests, mypy `--strict`, and pre-commit. Each job
  `cd`s into the member and runs `uv sync --all-groups`. (observed)
- **ML model pre-download in CI** mirrors the Dockerfiles: dedicated steps
  `from_pretrained(...)` the Nomic model (`mini_late_chunking`) and Jina
  tokenizer (`mini_document_search`), with a `~/.cache/huggingface`
  `actions/cache`. (observed)
- **Infrastructure** jobs (`infrastructure/*`) build/test the CDK apps with
  `npm ci`. (observed)

### Cache parity: image vs CI

| Concern | Docker image | CI |
|---|---|---|
| pnpm store | `--mount=type=cache` store mount | `actions/setup-node cache: pnpm` |
| uv cache | none (layer cache only) | `actions/cache` on `~/.cache/uv` |
| HF models | baked into build layer, offline at runtime | `actions/cache` on `~/.cache/huggingface` |

Same install commands (`--frozen-lockfile`, `uv sync`), different cache
mechanisms — parity is by convention, not shared config. (inferred)

## Key takeaways

- Root `compose.yaml` is the single local composition; it builds each image with
  `context: <subdir>/` and composes them with healthcheck-gated `depends_on`.
- `compose.experiments.yaml` is opt-in experiment infra and contains at least
  one stale build reference (`graphql.Dockerfile`).
- GitHub Actions CI validates source only; **image builds are not in CI**
  (CodeBuild/CDK, per Dockerfile comments — not verified in this pass).
