---
type: reference
status: draft
source:
  - /Users/gabriel/Work/gh/legal-ai/frontend/nogai/.prettierrc (observed)
  - /Users/gabriel/Work/gh/legal-ai/frontend/nogai/.prettierignore (observed)
  - /Users/gabriel/Work/gh/legal-ai/frontend/*/.prettierrc (observed, 8 members)
  - /Users/gabriel/Work/gh/legal-ai/frontend/*/package.json (observed, `fmt` scripts + prettier dep)
  - /Users/gabriel/Work/gh/legal-ai/.github/workflows/ci.yml (observed — no format gate)
links: ["[[linting-eslint]]", "[[pnpm-workspace]]", "[[qa-chain-typescript]]"]
---

# Formatting — prettier (as found)

Prettier is the formatter across the `legal-ai/frontend` pnpm workspace. Config
is **per-member and near-empty**: every member relies on prettier defaults plus
one plugin. Paths repo-relative to `frontend/`.

## 1. The config is one plugin, nothing else (observed)

**Every** member's `.prettierrc` is byte-identical (observed in all 8 that have
one: `nogai`, `landing-page`, `outbox_processor`, and the five `packages/*`):

```json
{
  "plugins": ["prettier-plugin-organize-imports"]
}
```

- **No** `printWidth`, `semi`, `singleQuote`, `trailingComma`, `tabWidth` etc. —
  so formatting is prettier's **defaults** (80-col, semicolons, double quotes,
  `trailingComma: "all"`, 2-space). (inferred from absence of overrides)
- The lone plugin, **`prettier-plugin-organize-imports`** (`^4.3.0`, dev dep in
  every member), sorts and prunes imports as part of `prettier --write`. It uses
  the TypeScript language service, so it also **drops unused imports** — a
  formatting pass doubles as import hygiene. (observed dep; inferred behaviour)
- No root `.prettierrc` exists at `frontend/`; there is no shared base to extend.
  Config is duplicated, not inherited (same pattern as tsconfig — see
  [[pnpm-workspace]] §6).

## 2. Prettier version drifts across members (observed — inconsistency)

Pinned exact vs caret, and two different versions coexist:

| Member | `prettier` devDep |
|---|---|
| `nogai`, `event-sourcing-core`, `logger` | `3.6.2` (exact) |
| `outbox_processor`, `agent-react`, `knowledge-graph`, `knowledge-graph-cli-v2` | `^3.7.4` (caret) |

No single hoisted prettier is enforced (contrast the `zod` hoist in `.npmrc`).
Formatting output could in principle differ by member; in practice 3.6→3.7 is
non-breaking. (observed / inferred)

## 3. What's ignored (observed, `.prettierignore`)

Two shapes exist. The **app** shape (`nogai`, `landing-page`; `outbox_processor`
+ `logger` are a subset) ignores build/artifact trees **and content-addressed
inputs**:

```
dist  build  coverage  .next  .claude  .cache/  node_modules
pnpm-lock.yaml  src/sdk/**            # generated OpenAPI SDK — never format
**/__test__/**/assets/**             # test fixtures kept byte-exact
snapshots/  migrations/  public/  .stryker-tmp  reports/
```

The **package** shape (`event-sourcing-core`, `agent-react`,
`knowledge-graph`, `knowledge-graph-cli-v2`) is terser: `dist/ node_modules/
coverage/` plus per-package extras (`snapshots/`, `__test__/snapshots/`,
`oclif.manifest.json`). Note `snapshots/` (not `__snapshots__/`) is ignored —
an eslint custom rule *enforces* that snapshot dir name precisely so prettier's
ignore glob catches it (see [[testing-vitest]] and [[linting-eslint]]).

## 4. How it's run — write-only, no gate (observed)

- Sole script, in every member: `"fmt": "prettier --write ."` — **formats in
  place**. There is **no** `fmt:check` / `prettier --check` script anywhere
  (grep-verified across all `package.json`s).
- **CI does not check formatting.** The four frontend jobs
  (`.github/workflows/ci.yml`) are `frontend-tests`, `frontend-typecheck`,
  `frontend-lint`, `frontend-i18n` — none runs prettier. (observed)
- **No git hook** — no husky/lefthook/pre-commit in the frontend (consistent
  with [[qa-chain-typescript]], [[crap-typescript]]). So formatting is
  **developer-/editor-driven only, enforced nowhere**. (observed)
- Editor formatting is inferred (no `.vscode/` committed at `frontend/`); the
  realistic loop is a manual/on-save `pnpm fmt`.

## 5. Interplay with ESLint — none configured (observed)

- **`eslint-config-prettier` and `eslint-plugin-prettier` are absent** — not a
  dependency of any member, not imported in any `eslint.config.*`
  (grep-verified). There is **no** layer disabling stylistic ESLint rules for
  prettier's sake, and prettier is **not** run through ESLint.
- They coexist by staying in separate lanes: prettier owns whitespace/layout;
  ESLint configs here carry code-quality rules, not formatting rules (see
  [[linting-eslint]]). `nogai` does pull `next/core-web-vitals` +
  `next/typescript`, which are quality/type rules, not a formatter. (observed)
- **Risk (inferred):** without `eslint-config-prettier`, a future stylistic
  ESLint rule could fight prettier; nothing guards against it today.

## Recommended distillation

- One `.prettierrc` per formatted member: `{"plugins":
  ["prettier-plugin-organize-imports"]}` — defaults + import organwell.
- `"fmt": "prettier --write ."`; **add** a `"fmt:check": "prettier --check ."`
  and wire it into CI if you want formatting actually gated (this repo does not).
- Pin one prettier version and hoist it, to kill the 3.6/3.7 drift.
- Ignore generated trees (`src/sdk/**`), snapshots, fixtures, lockfiles.
- Skip `eslint-config-prettier` only if ESLint carries no stylistic rules (as
  here); otherwise add it as the last ESLint layer.
