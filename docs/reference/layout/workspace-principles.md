---
type: reference
status: draft
source:
  - /Users/gabriel/Work/gh/legal-ai/frontend/  (pnpm workspace)
  - /Users/gabriel/Work/gh/legal-ai/backend/   (uv, per-service workspaces)
  - See sibling: pnpm-workspace.md, uv-workspace.md
---

# Workspace principles (language-agnostic)

The essence common to `legal-ai/frontend` (pnpm) and `legal-ai/backend` (uv),
stated prescriptively. Where the two stacks diverge, that is called out — the
divergences are as instructive as the agreements.

## 1. Two kinds of member: deployables vs shared libraries

Every member is one of:

- **Deployable** ("app"/"service") — the thing you run or ship. Has an
  entrypoint, gets a Dockerfile, is not imported by anything.
- **Shared library** ("package") — reusable code imported by deployables and by
  other libraries. Built/packaged; never deployed on its own.

Signals of a library (both stacks): a declared public surface
(`exports` map / build-backend producing a wheel), a scoped or namespaced name,
lives under a `packages/` directory. Signals of a deployable: bare name, an
entrypoint (`main.py`, `next build`, `server.js`), and a root-level Dockerfile.

Caveat observed: the split is about *role*, not rigid folder rules — a CLI can
live under `packages/` (`knowledge-graph-cli-v2`), and some services still
declare wheel packaging. Treat "app vs package" as intent, not a lint rule.

## 2. Members are registered explicitly, and the manifest is the source of truth

- pnpm: `pnpm-workspace.yaml` lists `packages/*` + each app by name.
- uv: `[tool.uv.workspace] members = ["../packages/*"]` inside each service.

A directory with source is **not** a member until it is both listed AND carries
a package manifest. Corollary (observed in both repos): proof-of-concept dirs
(`frontend/collab-poc`, `backend/mini_courtlistener` w.r.t. Docker) exist on
disk but are deliberately left unregistered / undeployed. Presence ≠ membership.

## 3. Dependency direction is a DAG pointing at libraries

The one hard rule both repos honor:

```
deployable ──▶ library ──▶ library
     (never ◀── ; no library depends on a deployable)
```

Libraries may depend on other libraries (`event-sourcing-core → logger`;
`knowledge-graph → agent-react`; `mini_knowledge → eu_cellar`). No cycles, and
nothing imports an app. This is what lets each deployable be built in isolation.

## 4. Internal deps use a first-class "local source" mechanism

Neither repo hand-rolls relative-path imports or publishes to a registry for
internal code. Each package manager has a protocol that says "this named
dependency is the copy in this repo":

- pnpm: `"@legal-ai/logger": "workspace:*"`
- uv: name it in `[project.dependencies]`, then
  `[tool.uv.sources] logger = { workspace = true }`

Prefer the manager's workspace protocol over path deps: you keep normal
dependency semantics (version constraints, peer deps) while resolving locally.

## 5. Dev consumes source, prod consumes built artifacts

Both stacks let a downstream member use a library's **source** during
development but its **built output** in production:

- pnpm: the `development` vs `default` conditional `exports` (src/*.ts vs dist).
- uv: `uv run` against the workspace resolves sibling source; the Docker build
  runs `uv sync --locked` to install pinned, built deps.

This removes a "build every lib before you can run the app" step in the inner
loop, while shipping stable artifacts in the image.

## 6. Config is duplicated per member, not inherited from a root

Both repos **lack a shared base config** for the compiler/type-checker/linter:

- No root `tsconfig.json`; each member copies the same compilerOptions.
- No root `pyproject.toml`; each member repeats `[tool.ruff]`/`[tool.mypy]`.

Observed consequence: settings **drift** (ruff line-length 88 vs 100; tsconfig
`build` vs `dev` naming). This is a real cost of the decentralized model — a
shared base (`tsconfig` `extends`, or a shared config package) would trade a
little coupling for consistency. Documented here as an honest tension, not an
endorsement.

Where inheritance *is* used, it is **local**: each member's `tsconfig.dev.json`
extends its own `tsconfig.json` (build config = emit, dev config = typecheck
everything incl. tests).

## 7. One Dockerfile per deployable, living at the workspace root

The strongest shared convention:

- File named `<member>.Dockerfile` (+ `.dockerignore`) at the **workspace root**,
  not inside the member dir.
- **Build context = workspace root**, so the build can see the lockfile, the
  workspace manifest, and sibling `packages/`.
- The `.dockerignore` **whitelists** only the target member + shared packages and
  excludes sibling deployables, keeping the context small despite the wide root.
- Inside the image, members are laid out at the **same relative paths** as on
  disk (`/app/<service>` + `/app/packages`) so workspace member paths
  (`../packages/*`) resolve unchanged.
- Multi-stage: a build stage installs (with a cache-mounted package store) and
  compiles dependency libraries first, then the app; a slim runtime stage copies
  only what runs and drops to a non-root user.

Why root-level, not per-member: a deployable's build needs its shared-library
siblings and the single lockfile, which only exist at the workspace root. A
Dockerfile buried in the member dir cannot reach them without a wider context
anyway — so put it where its context is.

## 8. Lockfile strategy differs — decide deliberately

This is where the two stacks diverge, and the choice matters:

- **pnpm**: **one** lockfile (`pnpm-lock.yaml`) at the workspace root; the whole
  graph resolves together (single hoisted store, one `zod` via
  `public-hoist-pattern`).
- **uv**: **one lockfile per project** (each service and each package), no
  unified root lock. A shared package is resolved once for itself and again
  inside every consumer's workspace.

Single-lock = guaranteed one version of everything, coupled resolution.
Per-project locks = independent, reproducible service builds and simpler
per-service Docker caching, at the cost of possible version skew between
services. `legal-ai` chose single-lock for the tightly-coupled frontend and
per-service locks for independently-deployed Python services — a defensible
split by blast radius.

## 9. Orchestration is thin at the root, fat in the members

Cross-cutting commands fan out (`pnpm -r run lint`, or `--filter`/`--project`
one member); the actual `build`/`test`/`lint`/`fmt` logic lives in each member's
manifest. The root holds only wiring (recursive runners, `knip`) — keep it that
way so members stay independently buildable.
