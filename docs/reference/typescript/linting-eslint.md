---
type: reference
status: draft
source:
  - /Users/gabriel/Work/gh/legal-ai/frontend/nogai/eslint.config.mjs (observed, ~500 lines)
  - /Users/gabriel/Work/gh/legal-ai/frontend/nogai/eslint-rules/*.js (observed, 16 custom rules)
  - /Users/gabriel/Work/gh/legal-ai/frontend/packages/*/eslint.config.mts (observed, 5 packages)
  - /Users/gabriel/Work/gh/legal-ai/frontend/*/package.json (observed — `lint` scripts, eslint ^9)
  - /Users/gabriel/Work/gh/legal-ai/.github/workflows/ci.yml (observed — frontend-lint job)
links: ["[[formatting-prettier]]", "[[testing-vitest]]", "[[type-checked-tests]]", "[[qa-chain-typescript]]", "[[architecture-tests]]"]
---

# Linting — ESLint (as found)

ESLint 9 **flat config** everywhere. Two dialects: `nogai`/`landing-page` are
Next.js apps (huge bespoke config), the `packages/*` share a compact
typescript-eslint config. Two members have **no ESLint at all**. Paths
repo-relative to `frontend/`.

## 1. Flat config, ESLint 9, typed parser (observed)

All configs are flat (`eslint.config.mjs`/`.mts`, array export), eslint `^9.x`.
Both dialects use `@typescript-eslint/parser` with the **project service** so
rules are **type-aware**:

```ts
// packages/*/eslint.config.mts
languageOptions: { parser: tsparser, parserOptions: { projectService: true } }
```

`nogai` adds `project: "./tsconfig.json"` + `tsconfigRootDir`. The package
configs are typed `satisfies TSESLint.FlatConfig.ConfigArray`.

## 2. Per-member coverage is uneven (observed — inconsistency)

| Member | ESLint config | `lint` script |
|---|---|---|
| `nogai` | `eslint.config.mjs` (Next + 16 custom rules) | `eslint` |
| `packages/event-sourcing-core`, `logger`, `agent-react` | `.mts`, compact | `eslint src` |
| `packages/knowledge-graph` | `.mts` + test override | `eslint src` |
| `packages/knowledge-graph-cli-v2` | `.mts` + test/web overrides | `eslint src __test__ bin web` |
| `landing-page` | **none** | **no `lint` script** |
| `outbox_processor` | **none** | **no `lint` script** |

`landing-page` and `outbox_processor` are **not linted** — `pnpm -r lint` simply
skips members with no `lint` script. Most `packages/*` lint **only `src`**, not
their tests (except `cli-v2` and `knowledge-graph`, which add typed test
overrides). (observed)

## 3. The package baseline: typescript-eslint recommended + strict `any` (observed)

Every `packages/*` config starts from `tseslint.configs.recommended.rules` and
hardens the unsafe-`any` family to **error**:

```ts
...tseslint.configs.recommended.rules,
"@typescript-eslint/no-explicit-any": "error",
"@typescript-eslint/no-unsafe-assignment": "error",
"@typescript-eslint/no-unsafe-member-access": "error",
"@typescript-eslint/no-unsafe-call": "error",
"@typescript-eslint/no-unsafe-return": "error",
"@typescript-eslint/no-unused-vars": ["error",
  { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
```

- It is `recommended`, **not** `recommended-type-checked`/`strict-type-checked`
  — the strictness comes from hand-picking the five unsafe-any rules, not from a
  preset. (observed)
- Test-file overrides (`cli-v2`, `knowledge-graph`) add
  `@typescript-eslint/consistent-type-imports: "error"` and point the parser at
  `tsconfig.dev.json` so tests are lintable with types (see [[type-checked-tests]]).
- `event-sourcing-core` relaxes one rule: `no-empty-object-type` with
  `allowObjectTypes: "always"` (empty state generics). `caughtErrorsIgnorePattern`
  is added there too.

## 4. nogai: Next preset + 16 project-specific custom rules (observed)

`nogai` composes `next/core-web-vitals` + `next/typescript` (via `FlatCompat`)
and layers a **local plugin of 16 hand-written rules** (`nogai/eslint-rules/*.js`),
scoped by file glob. Highlights:

- **Domain/DDD guards:** `no-userid-in-service-queries` (actor pattern; see
  actor-authorization), `require-typed-event-handlers`,
  `no-event-metadata-in-listeners`, `no-event-type-guards` (scoped to
  `**/listeners.ts`), `no-suspended-callback-mutations` (`**/*.workflow.ts`),
  `require-err-field-in-logger` (Pino serialization), `no-locale-fallbacks`.
- **Test-hygiene rules** (scoped to `**/*.test.ts`, `**/__test__/**`):
  `no-container-in-tests` (no `ApplicationContainer` in unit tests — e2e/integration
  exempt), `no-local-mock-factories` (push toward shared factories),
  `require-assert-all-overrides-called`, `integration-test-cleanup`.
- **Convention rules:** `no-tests-directory` (force `__test__`, not `__tests__`),
  `no-dunder-snapshots-directory` (force `snapshots/`, not `__snapshots__/` — so
  prettier's ignore catches them; see [[formatting-prettier]]),
  `no-inline-type-imports`, `no-section-separator-comments`,
  `prefer-remove-unused-vars` (replaces the built-in `no-unused-vars`, which is
  turned **off**).

nogai also uses **`eslint-plugin-vitest`** on test globs
(`vitest/expect-expect` with an allow-list incl. `expectTypeOf`, `toPassAsync`;
`no-identical-title`, `valid-expect` maxArgs 2, `no-standalone-expect`) and
**`eslint-plugin-drizzle`** (`enforce-delete-with-where`). See [[testing-vitest]].

### `no-restricted-*` — the enforcement centerpiece (observed)

- `no-restricted-imports`: bans `uuid` and `crypto.randomUUID` — forces
  `generateUUID from "@/lib/utils/uuid"` (with `src/lib/utils/uuid.ts` exempted).
- `no-restricted-syntax`: bans `crypto.randomUUID()`, `z.any()`, and **~30 Zod v4
  deprecations** (`z.string().uuid()` → `z.uuid()`, etc.) via AST selectors — a
  bespoke, self-maintained "codemod-as-lint".

## 5. How it composes with prettier — separate lanes (observed)

No `eslint-config-prettier`/`eslint-plugin-prettier` anywhere (grep-verified).
ESLint carries **zero formatting rules** (Next presets + quality/custom rules
only), so it doesn't collide with prettier, which owns layout. See
[[formatting-prettier]] §5. They run as independent scripts.

## 6. How it runs (observed)

- Per member: `pnpm lint` → `eslint [globs]`. Root fan-out: `pnpm -r run lint`.
- CI: `frontend-lint` job runs `pnpm -r lint` then `pnpm --filter . lint:knip`
  (knip is a *separate* gate — see [[qa-chain-typescript]]). Blocking for merge.
- No `--fix` in CI; no pre-commit hook. `nogai` `tsarch` architecture rules are
  a **vitest** project, not ESLint — see [[architecture-tests]].
