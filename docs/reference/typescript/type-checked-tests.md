---
type: reference
status: draft
source:
  - /Users/gabriel/Work/gh/legal-ai/frontend/*/tsconfig.json (observed — build config, excludes tests)
  - /Users/gabriel/Work/gh/legal-ai/frontend/*/tsconfig.dev.json (observed — includes tests)
  - /Users/gabriel/Work/gh/legal-ai/frontend/*/package.json (observed — `type-check` scripts)
  - /Users/gabriel/Work/gh/legal-ai/frontend/landing-page/tsconfig.build.json (observed — excludes tests)
  - /Users/gabriel/Work/gh/legal-ai/.github/workflows/ci.yml (observed — frontend-typecheck job)
links: ["[[pnpm-workspace]]", "[[testing-vitest]]", "[[linting-eslint]]", "[[qa-chain-typescript]]"]
---

# Type-checked tests (as found)

**How test files get type-checked: a second tsconfig (`tsconfig.dev.json`) that
*re-includes* the test dirs the build config excludes, checked with
`tsc -p tsconfig.dev.json --noEmit`.** No vitest `typecheck` feature, no
`*.test-d.ts`, no `expectTypeOf` type-assertion suites are used — tests are
type-checked the same way `src` is, just with a wider `include`. Paths
repo-relative to `frontend/`.

## 1. The build config excludes tests; the dev config re-includes them (observed)

Two tsconfigs per member (the split introduced in [[pnpm-workspace]] §6). The
**build** config emits `dist/` and **excludes tests**:

```jsonc
// packages/logger/tsconfig.json  (build/emit)
"outDir": "./dist", "rootDir": "./src", "noEmit": false,
"include": ["src/**/*"], "exclude": ["node_modules", "dist", "__test__"]
```

The **dev** config `extends` it, flips to `noEmit: true`, drops `rootDir`, and
**adds the test tree** to `include`:

```jsonc
// packages/logger/tsconfig.dev.json  (type-check only)
"extends": "./tsconfig.json",
"compilerOptions": { "rootDir": null, "noEmit": true },
"include": ["src/**/*", "__test__/**/*"],   // <-- tests re-added
"exclude": ["node_modules", "dist"]         // <-- no longer excludes __test__
```

**This re-include is the whole mechanism.** Dropping `__test__` from `exclude`
and widening `include` is what puts test files under the type-checker.

## 2. The script that does it (observed)

Standard per-member script — CI's `frontend-typecheck` job runs `pnpm -r
type-check`:

```json
"type-check": "tsc -p tsconfig.dev.json --noEmit"
```

Because the dev config includes `src` **and** `__test__`, one `tsc` invocation
type-checks production code and tests together, at the same strictness. This is
a **compile-only** gate: `--noEmit`, no test execution. (observed)

## 3. Same strictness for tests as for src (observed)

`tsconfig.dev.json` `extends` the build config and **never loosens** the
compiler flags, so tests inherit `strict: true`, `isolatedModules: true`,
`moduleResolution: "bundler"` verbatim. The only dev-side changes are structural,
not strictness:

- `rootDir: null` — tests live outside `src/rootDir`, so the constraint is removed.
- `noEmit: true` — checking, not building.
- Some dev configs set `"types": []` (`event-sourcing-core`, `knowledge-graph`)
  or `"types": ["node"]` (`cli-v2`) to control ambient globals; `cli-v2` also
  sets `allowJs/checkJs:false` and re-declares `paths`.

So test-only code (fixtures, builders, arbitraries, factories) is held to the
**identical** `strict` bar as production — there is no relaxed test tsconfig.

## 4. Per-member reality — three patterns (observed)

| Member | `type-check` command | Are tests type-checked? |
|---|---|---|
| `nogai` | `tsc -p tsconfig.dev.json --noEmit` | **Yes** — dev `include` is `**/*.ts(x)` + `e2e/**`; dev `exclude` omits `__test__` (build config excludes it) |
| `logger`, `event-sourcing-core`, `knowledge-graph`, `agent-react`, `cli-v2` | `tsc -p tsconfig.dev.json --noEmit` (`agent-react`: `tsc --noemit -p tsconfig.dev.json`) | **Yes** — dev `include` adds `__test__/**/*` |
| `cli-v2` | `tsc -p tsconfig.dev.json --noEmit && tsc -p web/tsconfig.json --noEmit` | **Yes** — two passes (lib+bin+tests, then web) |
| **`landing-page`** | `tsc -p tsconfig.build.json --noEmit` | **No** — see below |
| **`outbox_processor`** | `tsc --noEmit` (default `tsconfig.json`) | **No** — build config excludes all `*.test.ts`/`__test__` |

### Inconsistency: `landing-page` type-checks *away* from tests (observed)

`landing-page` has no `tsconfig.dev.json`; its `type-check` targets
`tsconfig.build.json`, which **explicitly excludes** every test glob:

```jsonc
// landing-page/tsconfig.build.json
"exclude": ["node_modules","dist",".next",".claude","e2e",
  "**/__test__/**","**/__tests__/**","**/*.test.ts","**/*.test.tsx",
  "**/*.spec.ts","**/*.spec.tsx","**/*.end-to-end.test.ts","**/*.contract.ts"]
```

So `landing-page` (and `outbox_processor`, via its single build tsconfig) ships a
`type-check` that **never sees test files**. The `tsconfig.dev.json` convention
is the norm but not universal. (observed)

## 5. What is NOT used (observed — grep-verified)

- **No vitest `typecheck` feature** — no `test: { typecheck: … }` in any
  `vitest.config.ts`; vitest never invokes `tsc`. Type-checking is a wholly
  separate `tsc` pass from the test run (see [[testing-vitest]]).
- **No `*.test-d.ts`** type-test files, and **no `expectTypeOf`/`assertType`**
  calls in first-party source (only inside `node_modules` deps). The
  `vitest/expect-expect` allow-list *names* `expectTypeOf` ([[linting-eslint]]),
  but no first-party test uses it. Type-level assertions are done implicitly by
  `tsc` compiling the tests, not by explicit type-equality assertions.
- **No `tsd`/`dtslint`.** Type safety of fixtures/builders is enforced only by
  `strict` `tsc` over `tsconfig.dev.json`.

## 6. ESLint is the second type-aware pass over tests (observed)

Separately from `tsc`, ESLint is **type-aware** (`projectService: true`), and in
`cli-v2`/`knowledge-graph` the test-file override points the parser at
`tsconfig.dev.json` — so unsafe-`any` rules apply to tests too. That is a second,
rule-based type check layered on the `tsc` compile check. See [[linting-eslint]] §3.

## Recommended distillation

- Keep `tsconfig.json` (emit, `exclude: ["__test__"]`) + `tsconfig.dev.json`
  (`extends`, `noEmit`, `include: ["src/**/*","__test__/**/*"]`) per member.
- `"type-check": "tsc -p tsconfig.dev.json --noEmit"`; run via `pnpm -r
  type-check` in CI. This is the canonical "tests are type-checked" gate.
- Do **not** loosen strictness for tests — extend, never override the flags.
- Audit that *every* member's `type-check` targets the test-including config
  (this repo's `landing-page`/`outbox_processor` do not — a real gap).
