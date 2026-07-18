---
type: reference
status: draft
source:
  - /Users/gabriel/Work/gh/legal-ai/frontend/pnpm-workspace.yaml
  - /Users/gabriel/Work/gh/legal-ai/frontend/package.json
  - /Users/gabriel/Work/gh/legal-ai/frontend/.npmrc
  - /Users/gabriel/Work/gh/legal-ai/frontend/knip.json
  - /Users/gabriel/Work/gh/legal-ai/frontend/packages/*/package.json
  - /Users/gabriel/Work/gh/legal-ai/frontend/{nogai,landing-page,outbox_processor,nogai_db_migrations}/package.json
  - /Users/gabriel/Work/gh/legal-ai/frontend/*.Dockerfile
---

# pnpm workspace conventions (recipe)

Derived from `legal-ai/frontend/`, a pnpm 10 workspace. Marked (observed) vs
(inferred). Cited paths are repo-relative to `frontend/`.

## 1. Register members explicitly, mixing globs and names

`pnpm-workspace.yaml` (observed):

```yaml
packages:
  - packages/*
  - nogai
  - nogai_db_migrations
  - outbox_processor
  - landing-page
```

- Shared libraries live under `packages/*` (glob).
- Each deployable app is listed **by name**, not globbed. Rationale (inferred):
  keeps the app set explicit and prevents stray dirs becoming members.
- **Inconsistency to note:** `collab-poc/` exists on disk but is *not* a member
  and has no `package.json` (it holds `agent/ client/ server/` source only). A
  directory is only a member if listed here AND carrying a `package.json`.

## 2. Naming: scoped packages vs bare apps

- **Packages** are scoped: `@legal-ai/logger`, `@legal-ai/event-sourcing-core`,
  `@legal-ai/agent-react`, `@legal-ai/knowledge-graph`,
  `@legal-ai/knowledge-graph-cli-v2` (observed in each `packages/*/package.json`).
- **Apps** are bare, matching their directory: `nogai`, `landing-page`,
  `outbox_processor`, `nogai_db_migrations` (observed).
- The root package is `@legal-ai`, `"private": true`, `"version": "0.0.0"`.

## 3. What is an "app" vs a "package"

| Trait | package (`packages/*`) | app (named member) |
|---|---|---|
| name | `@legal-ai/*` scoped | bare |
| `exports` map | yes, multi-entry | no |
| `main`/`types` → `dist` | yes | no |
| built with | `tsc` → `dist/` | `next build` / `esbuild` / none |
| has its own `.Dockerfile` at root | no | yes (deployables) |
| purpose | imported by others | deployed / run |

Note: `knowledge-graph-cli-v2` is a *package* (under `packages/*`, scoped) yet
ships a `bin` (`kg-cli`). "Package" = reusable/publishable unit, not "has no
entrypoint". (observed)

## 4. Cross-member deps use the `workspace:*` protocol

Apps and packages declare internal deps with `workspace:*` (observed):

- `nogai/package.json`: `"@legal-ai/logger": "workspace:*"`,
  `"@legal-ai/event-sourcing-core": "workspace:*"`, etc.
- `packages/event-sourcing-core/package.json`:
  `"@legal-ai/logger": "workspace:*"` (package → package).
- `packages/knowledge-graph/package.json` lists `@legal-ai/agent-react` as a
  **peerDependency** `workspace:*` *and* a devDependency `workspace:*` — the
  peer/dev pairing so it resolves in-repo but stays a peer for consumers.

**Direction (observed):** apps depend on packages; packages depend on other
packages; nothing depends on an app. See `workspace-principles.md`.

## 5. The `development` conditional export (dev source, prod dist)

Every package `exports` entry carries three conditions (observed,
`packages/*/package.json`):

```json
"." : {
  "types": "./dist/index.d.ts",
  "development": "./src/index.ts",
  "default": "./dist/index.js"
}
```

`development` points at raw `src/*.ts`, `default` at built `dist`. Consuming apps
running under a dev/test resolver pick up TypeScript source directly (no
prebuild); production reads `dist`. (inferred: this is why `pnpm build` of each
package is required in Dockerfiles before the app build.)

## 6. tsconfig is duplicated per member, not centrally extended

- **No root `tsconfig.json`** (observed: none at `frontend/`).
- Each member owns a standalone `tsconfig.json` — they do **not** `extends` a
  shared base; the compilerOptions block is copy-pasted across packages
  (identical `target/module/moduleResolution: bundler/strict`...). (observed)
- Split per member: `tsconfig.json` is the **build/emit** config
  (`outDir: dist`, `rootDir: src`, `noEmit: false`); a sibling
  `tsconfig.dev.json` `extends: "./tsconfig.json"` with `rootDir: null`,
  `noEmit: true`, and widened `include` to cover tests. `type-check` scripts
  target the dev variant: `tsc -p tsconfig.dev.json --noEmit`. (observed:
  `packages/logger/tsconfig.dev.json`, `nogai/tsconfig.dev.json`)
- **Inconsistency:** `landing-page` uses `tsconfig.build.json`, not
  `tsconfig.dev.json`, for its `type-check` script. Naming is not enforced.

## 7. Scripts compose top-down but thinly

Root `package.json` (observed) delegates recursively:

```json
"scripts": {
  "lint": "pnpm -r run lint",
  "lint:knip": "knip"
}
```

- `pnpm -r run <x>` fans a script across all members that define it.
- Filter a single member: `pnpm --filter @legal-ai/knowledge-graph <script>`
  (observed in root `generate:python-types`).
- Most orchestration (build/test/lint/fmt) lives **inside each member's**
  `package.json`; the root stays minimal. Common per-member scripts:
  `build`, `type-check`, `lint`, `lint:knip`, `fmt`, `test` (mostly
  `dotenv -- vitest run ...`).

## 8. Root-level tooling

- `.npmrc` (observed): `public-hoist-pattern[]=*zod*` — force a single hoisted
  `zod` so all members share one instance (avoids dual-package hazard).
- `knip.json` (observed): a `workspaces` map keyed by member path
  (`nogai`, `packages/event-sourcing-core`, `packages/logger`,
  `outbox_processor`) declaring `entry`/`project`/`ignore` globs. Not every
  member is covered — only ones wired into `lint:knip`.
- `pnpm-lock.yaml`: **one** lockfile at the workspace root (observed, ~756 KB).
- `packageManager: "pnpm@10.14.0"` pinned in app `package.json`s (observed).

## 9. One `.Dockerfile` per deployable, at the workspace root

Deployables carry `<member>.Dockerfile` + `<member>.Dockerfile.dockerignore`
at `frontend/` root (observed: `nogai`, `outbox_processor`,
`nogai_db_migrations`). **Build context = workspace root** so the Dockerfile can
see `pnpm-workspace.yaml`, `pnpm-lock.yaml`, and sibling `packages/`.

Three distinct strategies observed (see `docker` research pass for depth):

- **`nogai.Dockerfile`** — copies lockfiles + `packages/` + `nogai/package.json`,
  then `pnpm install --frozen-lockfile` and `pnpm run build` **each dependency
  package in order** (logger → event-sourcing-core → agent-react →
  knowledge-graph), `pnpm fetch`, then `next build` (standalone output).
- **`outbox_processor.Dockerfile`** — `esbuild` bundles the app *and* its
  workspace packages into one self-contained `dist/index.cjs`; a separate
  `deps` stage does `pnpm install --prod` so workspace package.jsons aren't
  needed at runtime.
- **`nogai_db_migrations.Dockerfile`** — a "thin" deployable that copies
  migration files **out of a sibling app** (`nogai/drizzle.config.ts`,
  `nogai/migrations`, `nogai/src/db`); it owns no source of its own.

All three: alpine node base, corepack-pinned pnpm, `--mount=type=cache` for the
pnpm store, non-root `USER node`.
