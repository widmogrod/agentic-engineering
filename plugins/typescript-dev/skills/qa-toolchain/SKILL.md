---
name: qa-toolchain
description: Set up or run the opinionated TypeScript QA chain in a pnpm project — prettier (format), eslint (type-aware lint), tsc over src AND tests via a dev tsconfig, vitest with coverage. Use when asked to add quality gates, formatting, linting, or type-checked testing to a TypeScript project, or to run/fix the QA chain in one that has it.
argument-hint: "[setup|run]"
---

# TypeScript QA toolchain (pnpm)

The chain, in order (cheap and syntactic first):

```
pnpm fmt:check      # prettier --check .
pnpm lint           # eslint .
pnpm type-check     # tsc -p tsconfig.dev.json --noEmit   (checks tests too!)
pnpm test           # vitest run --coverage
```

In a workspace, each member owns these scripts and the root runs `pnpm -r <script>`.

## The load-bearing pattern: type-checked tests via a dev tsconfig

Two tsconfigs, one strictness level:

- `tsconfig.json` — the EMIT config: `"strict": true`, `"exclude": ["__test__"]`
  (or your test glob). What ships.
- `tsconfig.dev.json` — the CHECK config: `"extends": "./tsconfig.json"`,
  `"compilerOptions": {"noEmit": true}`, `"include": ["src/**/*", "**/__test__/**/*"]`.
  What must compile.

`tsc -p tsconfig.dev.json --noEmit` compiles source and tests TOGETHER at the
same strict level. The dev config may only widen `include` — it must NEVER
loosen a strictness flag. A member whose type-check script points at a config
that excludes tests has silently un-type-checked tests; treat that as a defect.

## Setup — retrofit an existing pnpm project

Merge into existing config, never clobber; prefer the project's values and
report differences.

1. **Dev dependencies** (skip present ones):
   `pnpm add -D typescript vitest @vitest/coverage-v8 eslint typescript-eslint prettier prettier-plugin-organize-imports`

2. **Prettier** — `.prettierrc`:

   ```json
   { "plugins": ["prettier-plugin-organize-imports"] }
   ```

   Defaults + import organizing (sorts and drops unused imports). Resist
   adding options; the value is having NO formatting discussions.

3. **ESLint** — `eslint.config.js` (flat, ESLint 9):

   ```js
   import tseslint from "typescript-eslint";

   export default tseslint.config(
     ...tseslint.configs.recommended,
     {
       languageOptions: { parserOptions: { projectService: true } },
       rules: {
         "@typescript-eslint/no-unsafe-argument": "error",
         "@typescript-eslint/no-unsafe-assignment": "error",
         "@typescript-eslint/no-unsafe-call": "error",
         "@typescript-eslint/no-unsafe-member-access": "error",
         "@typescript-eslint/no-unsafe-return": "error",
       },
     },
   );
   ```

   Lint source AND tests — do not scope eslint to `src` only.

4. **The tsconfig pair** (above). If the project has one tsconfig including
   tests, split it; if its build config excludes tests with no dev config,
   that's the defect to fix first.

5. **Vitest** — `vitest.config.ts` with `coverage.provider: "v8"`. See the
   `testing` skill for project splits and conventions.

6. **Scripts** (per member):

   ```json
   {
     "fmt": "prettier --write .",
     "fmt:check": "prettier --check .",
     "lint": "eslint .",
     "type-check": "tsc -p tsconfig.dev.json --noEmit",
     "test": "vitest run --coverage",
     "qa": "pnpm fmt:check && pnpm lint && pnpm type-check && pnpm test"
   }
   ```

7. **Calibrate, don't punish.** Run the chain once BEFORE wiring gates. Report
   existing failures and ask: fix now, or gate at current reality and ratchet.
   Never silently disable a rule to get green.

8. **Wire gates** (ask which): CI job running the chain in order, minimum.
   Every workspace member must have the scripts — a member without `lint` or
   `type-check` is invisible to the chain, not passing it.

9. **Tell the agent**: record the canonical commands in `CLAUDE.md`, including
   that `type-check` covers tests and that eslint covers tests.

## Run

Run the chain in order. On failure: `pnpm fmt` fixes formatting; lint/type
errors get fixed in code (never `any`, `@ts-ignore`, or rule-disabling to pass
— see the `testing` skill for test-specific guidance). Report what was fixed.
