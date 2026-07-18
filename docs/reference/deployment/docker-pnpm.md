---
type: reference
status: draft
source:
  - /Users/gabriel/Work/gh/legal-ai/frontend/nogai.Dockerfile
  - /Users/gabriel/Work/gh/legal-ai/frontend/nogai.Dockerfile.dockerignore
  - /Users/gabriel/Work/gh/legal-ai/frontend/outbox_processor.Dockerfile
  - /Users/gabriel/Work/gh/legal-ai/frontend/outbox_processor.Dockerfile.dockerignore
  - /Users/gabriel/Work/gh/legal-ai/frontend/outbox_processor/esbuild.config.js
  - /Users/gabriel/Work/gh/legal-ai/frontend/nogai_db_migrations.Dockerfile
  - /Users/gabriel/Work/gh/legal-ai/frontend/nogai_db_migrations.Dockerfile.dockerignore
  - /Users/gabriel/Work/gh/legal-ai/frontend/nogai/next.config.ts
---

# Docker image recipes: TS / pnpm workspace

Three deployables under `legal-ai/frontend/` each ship a distinct Dockerfile
strategy. The layout (one `<member>.Dockerfile` + `.dockerignore` at the
workspace root, **build context = workspace root**) is covered in
[[pnpm-workspace]] — this doc is only the image recipes. Cited paths are
repo-relative to `frontend/`. Marked (observed) vs (inferred).

## Shared conventions (all three)

- **Base image:** `public.ecr.aws/docker/library/node:24.7.0-alpine3.22`
  (AWS ECR mirror of Docker Hub, not `docker.io` directly). (observed)
- **pnpm via corepack, pinned & cached:**
  ```dockerfile
  RUN --mount=type=cache,target=/root/.cache/corepack \
      corepack enable && corepack prepare pnpm@10.14.0 --activate
  ```
  Version `10.14.0` matches the `packageManager` field and CI. (observed)
- **`libc6-compat`** (`apk add`) for glibc-linked native deps. (observed)
- **pnpm store cache mount** on every install/fetch:
  `--mount=type=cache,target=/root/.local/share/pnpm/store` (nogai) or
  `target=/pnpm/store` with `ENV PNPM_HOME=/pnpm` (outbox, migrations).
  Two different store locations are used across files — an inconsistency, not
  a bug. (observed)
- **RDS TLS bundle** baked in at runtime via remote `ADD`:
  ```dockerfile
  ADD --chmod=644 https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem \
      /etc/ssl/certs/rds-ca-bundle.pem
  ```
  (observed — nogai & outbox & migrations)
- **Runtime secrets declared as empty `ENV`** (Auth0, AWS, DB) — documents the
  contract; real values injected via compose/task env. (observed)
- **Non-root `USER node`** — except `nogai_db_migrations`, which runs as root
  (inconsistency, flagged below). (observed)

---

## Strategy A — `nogai.Dockerfile`: Next.js standalone (2 stages)

Use when: the deployable is a **Next.js app** with `output: "standalone"`
(`next.config.ts` sets `output: "standalone"` +
`outputFileTracingRoot: "../../"`). (observed)

**Stage `builder`** — lockfile-first, then build each workspace package in
dependency order, then the app:

```dockerfile
# Only lockfiles for dependency graph
COPY pnpm-workspace.yaml pnpm-lock.yaml ./
COPY nogai/package.json ./nogai/
COPY packages/ ./packages/
```

Then, per package, in explicit topological order
(logger → event-sourcing-core → agent-react → knowledge-graph), each:

```dockerfile
WORKDIR /app/packages/logger
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile
RUN pnpm run build
```

Packages are built **before** the app because their `exports` `default`
condition points at `dist/` (see [[pnpm-workspace]] §5) — the app's
`next build` consumes compiled output, not source. (inferred)

Then prime the app's store and install offline:

```dockerfile
WORKDIR /app/nogai
RUN ... pnpm fetch                 # pre-fetch for better cache hits
COPY nogai ./
RUN ... pnpm install --frozen-lockfile --offline
```

Build-time env is load-bearing:

- `ENV NOGAI_DATABASE_URL=postgresql://build@localhost:5432/build` — a **dummy**
  URL so `drizzle.config.ts` can be imported during build; cleared to `""`
  after. (observed)
- `ARG NEXT_PUBLIC_FEATURE_CLOSED_ACCESS` → `ENV` — `NEXT_PUBLIC_*` is inlined
  into the **client bundle** at build time, so it MUST be a `--build-arg`, not
  runtime env. No default; caller (CodeBuild) passes it. (observed, per comment)
- `RUN --mount=type=cache,target=.next/cache pnpm build` — caches the Next
  build cache across builds. (observed)

**Stage `runner`** — minimal, copies only standalone output with ownership:

```dockerfile
COPY --from=builder --chown=node:node /app/nogai/.next/standalone/app ./
COPY --from=builder --chown=node:node /app/nogai/.next/static ./nogai/.next/static
COPY --from=builder --chown=node:node /app/nogai/public ./nogai/public
COPY --from=builder --chown=node:node /app/nogai/messages ./nogai/messages
```

The `.next/standalone/app` subpath is a consequence of
`outputFileTracingRoot` pointing above the app dir, so the traced tree nests the
app under a workspace-root folder. (inferred from `next.config.ts` + copy paths)

Runner extras:
- `apk add font-noto` — Noto fonts for unicode PDF generation. (observed)
- `@napi-rs/canvas` is **npm-installed fresh in the runner** (not copied from
  builder) — the comment states the pnpm cache mount makes hardlinks
  unavailable, so it's installed to a temp dir and `cp`'d into the pnpm-root
  `node_modules`. Needed by `pdfjs-dist` (transitive via `markitdown-ts`).
  (observed)
- `ENV PORT=3001`, `EXPOSE 3001`, `CMD ["node", "nogai/server.js"]`. (observed)

**`.dockerignore`** whitelists app source and blacklists all `dist`/`node_modules`/
`.next` (keeps the workspace-root context lean):
```
!nogai/src/*/**
!nogai/drizzle.config.ts
!nogai/tsconfig.json
!nogai/conf
!nogai/migrations
!nogai/public
packages/*/node_modules
packages/*/dist
...
```

---

## Strategy B — `outbox_processor.Dockerfile`: esbuild self-contained bundle (4 stages)

Use when: a **Node worker** that can be bundled into a single file, so the
runtime image needs no workspace `node_modules` graph. (observed)

Stages: `base` → `build` → `deps` → final.

- **`build`:** `COPY . /app` (whole context), `pnpm install --frozen-lockfile`,
  build the four workspace packages, then `pnpm run build:docker` (=
  `node esbuild.config.js`) in `outbox_processor/`.
- **esbuild config** (`outbox_processor/esbuild.config.js`) **bundles** the four
  `@legal-ai/*` workspace packages and marks all other `dependencies` +
  Node builtins as `external`. A custom plugin resolves `@/*` imports to
  `../nogai/src/*` — so the bundle also pulls in **nogai app source**, not just
  the packages. Output: `outbox_processor/dist/index.cjs` (with source maps).
  (observed) This is why the outbox `.dockerignore` whitelists
  `!nogai/src/*/**`.
- **`deps`:** installs **prod-only** deps from just the root manifests + the
  outbox `package.json` — workspace package.jsons are not needed because their
  code is already bundled:
  ```dockerfile
  COPY --from=build /app/package.json /app/pnpm-lock.yaml /app/pnpm-workspace.yaml /app/
  COPY --from=build /app/outbox_processor/package.json /app/outbox_processor/
  RUN --mount=type=cache,target=/pnpm/store pnpm install --prod --frozen-lockfile
  ```
- **final:** copies only `deps` node_modules + the `build` `dist/` and
  `package.json`. Comment notes this saves ~853 MB by *not* copying
  `nogai/node_modules` or package dist folders. (observed)
- `ENV PORT=9615`, `EXPOSE 9615`, `USER node`,
  `CMD ["node", "--enable-source-maps", "outbox_processor/dist/index.cjs"]`.

---

## Strategy C — `nogai_db_migrations.Dockerfile`: thin deployable, source borrowed from a sibling (4 stages)

Use when: a deployable **owns no source of its own** — here it runs drizzle
migrations that physically live inside the `nogai` app. (observed)

Stages: `base` → `build` → `deps` → final.

- **`build`:** installs the migration package's deps (its own
  `nogai_db_migrations/package.json` + root lockfiles), then **copies migration
  assets out of the sibling `nogai` app**, flattening the paths:
  ```dockerfile
  COPY nogai/drizzle.config.ts ./
  COPY nogai/migrations ./migrations
  COPY nogai/src/db ./src/db
  ```
- **`deps`:** re-installs with `pnpm install --frozen-lockfile` (all deps, incl.
  `drizzle-kit` from devDependencies — needed for proper bin linking). (observed)
- **final:** reconstructs the pnpm layout by copying the content-addressable
  store plus the package's symlink tree, then re-homes the borrowed migration
  files under the package dir:
  ```dockerfile
  COPY --from=deps /app/node_modules/.pnpm ./node_modules/.pnpm
  COPY --from=deps /app/nogai_db_migrations/node_modules ./nogai_db_migrations/node_modules
  COPY --from=build /app/drizzle.config.ts ./nogai_db_migrations/
  COPY --from=build /app/migrations ./nogai_db_migrations/migrations
  COPY --from=build /app/src/db ./nogai_db_migrations/src/db
  ```
  Copying `.pnpm` (real packages) + the package's `node_modules` (symlinks into
  `.pnpm`) preserves pnpm's resolution without a re-install. (observed)
- `ENTRYPOINT ["/bin/sh", "-c"]`, `CMD ["pnpm run db:migrate"]` — busybox sh,
  no bash. (observed)
- **Inconsistency:** no `USER node` — this image runs as **root**, unlike A and
  B. (observed) Its `.dockerignore` is the most surgical, whitelisting only
  `nogai/drizzle.config.ts`, `nogai/migrations`, `nogai/src/db`, and the
  package's own `package.json`.

---

## Choosing a strategy

| Deployable shape | Strategy | Runtime artifact |
|---|---|---|
| Next.js app (`output: standalone`) | A | `.next/standalone` + static/public |
| Node worker, bundleable | B | single `dist/index.cjs` (esbuild) |
| Task that borrows another member's files | C | copied assets + pnpm store |

All three: alpine node 24.7, corepack-pinned pnpm 10.14, `--frozen-lockfile`,
store cache mounts, RDS CA bundle, empty-`ENV` secret contract.
