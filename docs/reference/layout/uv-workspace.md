---
type: reference
status: draft
source:
  - /Users/gabriel/Work/gh/legal-ai/backend/  (no root pyproject.toml — observed absent)
  - /Users/gabriel/Work/gh/legal-ai/backend/mini_knowledge/pyproject.toml
  - /Users/gabriel/Work/gh/legal-ai/backend/mini_workflow/pyproject.toml
  - /Users/gabriel/Work/gh/legal-ai/backend/mini_{courtlistener,document_search,preview,late_chunking}/pyproject.toml
  - /Users/gabriel/Work/gh/legal-ai/backend/packages/{brazil_legislation_apis,eu_cellar,polish_case_law_apis}/pyproject.toml
  - /Users/gabriel/Work/gh/legal-ai/backend/*.Dockerfile
---

# uv workspace conventions (recipe)

Derived from `legal-ai/backend/`, uv-managed Python 3.12 services. Cited paths
are repo-relative to `backend/`.

## 0. Headline: there is NO root workspace

**The backend root is not a uv workspace.** (observed)

- No `backend/pyproject.toml`, no `backend/uv.lock`.
- The `[tool.uv.workspace]` stanza lives **inside individual services**, not at
  the repo root — the opposite of the "one workspace root" model the task
  assumed. Each deployable service is its own project root.

## 1. Two member roles

- **Services** — one dir per deployable: `mini_courtlistener`,
  `mini_document_search`, `mini_knowledge`, `mini_late_chunking`,
  `mini_preview`, `mini_workflow`. Each has its own `pyproject.toml` **and its
  own `uv.lock`** (observed: 6 service locks).
- **Shared packages** — `packages/brazil_legislation_apis`, `packages/eu_cellar`,
  `packages/polish_case_law_apis`. Libraries, each with its own `pyproject.toml`
  and `uv.lock` too.

## 2. A service becomes a workspace *only if* it consumes a shared package

Only `mini_knowledge` and `mini_workflow` declare a workspace (observed —
`grep tool.uv.workspace` matches exactly these two). Pattern
(`mini_knowledge/pyproject.toml`):

```toml
[project]
dependencies = [
    "eu_cellar",
    "brazil_legislation_apis",
    # ...normal PyPI deps...
]

[tool.uv.sources]
eu_cellar = { workspace = true }
brazil_legislation_apis = { workspace = true }

[tool.uv.workspace]
members = ["../packages/*"]
```

- The workspace **root is the service dir**; `members = ["../packages/*"]`
  reaches **up and sideways** into the sibling `packages/` tree.
- The dep is named plainly in `[project].dependencies`, then re-pointed to the
  in-repo source via `[tool.uv.sources] <name> = { workspace = true }`.
- A service pulls in only the packages it actually imports as `[project]`
  deps; the `members` glob makes all packages *available*, `sources` selects
  which are *used*.

Services with no shared-package need (`mini_courtlistener`,
`mini_document_search`, `mini_late_chunking`, `mini_preview`) have **no**
`[tool.uv.workspace]` / `[tool.uv.sources]` at all — plain standalone projects.
(observed)

## 3. Shared packages: build-backend, apps: none

- Packages set a real build backend (observed, all three):

  ```toml
  [build-system]
  requires = ["uv_build>=0.8.5,<0.9.0"]
  build-backend = "uv_build"
  ```

- `mini_knowledge` and `mini_workflow` (workspace apps) declare **no**
  `[build-system]` — they are run, not built into wheels. (observed)
- **Inconsistency:** `mini_courtlistener`, `mini_document_search`,
  `mini_late_chunking` *do* declare `[build-system]` with `hatchling` and
  `[tool.hatch.build.targets.wheel] packages = [...]`, even though they are
  services. So the "apps have no build-system" rule is not uniform — some
  services are packaged as wheels, some are not. `uv_build` (packages) vs
  `hatchling` (some services) is also mixed.

## 4. Per-member pyproject conventions

- `requires-python = ">=3.12"` everywhere except `mini_workflow` (`>=3.11`).
- Dev deps go in `[dependency-groups] dev = [...]` (PEP 735), not
  `optional-dependencies` — consistent across members (observed). Common set:
  `pytest`, `pytest-asyncio`, `pytest-cov`, `mypy`, `ruff`, `pre-commit`.
- `mini_document_search` additionally uses `[project.optional-dependencies]`
  for `demo` and `evaluation` extras — extras for optional runtime feature sets,
  dependency-groups for dev tooling.
- Tool config (`[tool.ruff]`, `[tool.mypy]`, `[tool.pytest.ini_options]`) is
  **duplicated per member**, not centralized (no root to inherit from).
  Values drift: ruff `line-length` is 100 in most, 88 in `mini_preview`.

## 5. Naming: not standardized

- Directory names all use underscores: `mini_knowledge`, `mini_courtlistener`.
- `[project].name` is **inconsistent**: underscores in `mini_knowledge`,
  `mini_workflow`, `mini_preview`, `mini_late_chunking`; **hyphens** in
  `mini-courtlistener`, `mini-document-search`. (observed — worth flagging)
- Shared package names match their dir with underscores: `eu_cellar`,
  `brazil_legislation_apis`, `polish_case_law_apis`.

## 6. Lockfile strategy: one lock per project, packages locked twice

- Every service AND every package has its **own** committed `uv.lock` (observed:
  9 lockfiles, none at root).
- A shared package is therefore resolved independently for its own dev/test,
  **and re-resolved** inside each consuming service's workspace lock. There is no
  single unified lock across the backend. (observed / inferred consequence)

## 7. One `.Dockerfile` per deployable, at the backend root

`<service>.Dockerfile` + `<service>.Dockerfile.dockerignore` sit at `backend/`
root. **Build context = backend root.** (observed)

Note: `mini_courtlistener` has **no Dockerfile** — it is a CLI/dev tool, not
deployed. (observed)

**Workspace service** (`mini_knowledge.Dockerfile`, observed):

```dockerfile
WORKDIR /app/mini_knowledge
COPY ./packages/ /app/packages
COPY ./mini_knowledge/uv.lock ./mini_knowledge/pyproject.toml /app/mini_knowledge/
RUN uv sync --locked
COPY ./mini_knowledge/. /app/mini_knowledge/
# ...runtime stage...
CMD ["uv", "run", "--no-sync", "main.py"]
```

Key trick: the image lays the service at `/app/mini_knowledge` and packages at
`/app/packages`, so the `members = ["../packages/*"]` path resolves identically
inside the container as on disk. `--locked` enforces the committed lock;
`uv run --no-sync` at runtime skips re-resolution.

**Standalone service** (`mini_document_search.Dockerfile`, observed): same shape
but **no** `COPY ./packages/` — just copy the service, `uv sync --locked`, run.

**`.dockerignore` whitelisting** (observed,
`mini_knowledge.Dockerfile.dockerignore`): starts by un-ignoring only what this
image needs and excluding sibling services —

```
!mini_knowledge
!packages
mini_document_search
mini_late_chunking
mini_preview
mini_workflow
```

so the root build context stays small even though it is the whole backend.

## 8. Pattern summary

```
backend/                      # NOT a workspace
├── <service>.Dockerfile      # one per deployable, context = backend/
├── mini_knowledge/           # workspace root: members=[../packages/*]
│   ├── pyproject.toml        #   + [tool.uv.sources] pkg = {workspace=true}
│   └── uv.lock
├── mini_document_search/     # standalone project (no workspace stanza)
│   ├── pyproject.toml
│   └── uv.lock
└── packages/
    └── eu_cellar/            # shared lib, build-backend=uv_build, own uv.lock
```
