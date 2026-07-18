---
type: reference
status: draft
source:
  - /Users/gabriel/Work/gh/legal-ai/.github/workflows/ci.yml (observed)
  - /Users/gabriel/Work/gh/legal-ai/frontend/nogai/package.json (observed)
  - /Users/gabriel/Work/gh/legal-ai/frontend/nogai/knip.json (observed)
  - /Users/gabriel/Work/gh/legal-ai/frontend/nogai/vitest.config.ts (observed)
  - /Users/gabriel/Work/gh/legal-ai/frontend/nogai/scripts/validate-translations.ts (observed)
links: ["[[qa-chain-python]]", "[[architecture-tests]]", "[[crap-typescript]]", "[[mutation-testing-typescript]]", "[[linting-formatting]]"]
---

# QA gate chain — TypeScript recipe

The full quality chain for the `nogai` Next.js/pnpm workspace. Beyond typecheck
(`tsc`) and eslint, the distinctive links are **knip** (dead code / unused
deps), **i18n validation**, **tsarch architecture tests** (see
[[architecture-tests]]), and **fast-check** property-based tests.

Unlike the Python repo, there is **no husky / lefthook pre-commit** in the
frontend — the gates run in **CI only** (`legal-ai/.github/workflows/ci.yml`, on
PRs to `main`) plus manual `pnpm` scripts. Each frontend gate is its own
parallel CI job, so all are blocking-for-merge but fail independently.

## Gate order (CI jobs)

| Gate | CI job / command | Checks | Blocking |
|------|------------------|--------|----------|
| Tests | `frontend-tests` → `pnpm test` | vitest `node` + `jsdom` projects (incl. fast-check property tests) | yes |
| Type check | `frontend-typecheck` → `pnpm -r type-check` (`tsc --noEmit`) | types — see [[type-checking]] | yes |
| ESLint | `frontend-lint` → `pnpm -r lint` | lint, incl. `no-restricted-syntax` for `crypto.randomUUID` | yes |
| **knip** | `frontend-lint` → `pnpm --filter . lint:knip` | unused files, exports, dependencies | yes |
| **i18n** | `frontend-i18n` → `pnpm --filter nogai lint:i18n` | translation key parity + usage | yes |

Gates that exist as scripts/vitest projects but are **not** in the default CI
`pnpm test` run (must be invoked explicitly): `test:arch` (see
[[architecture-tests]]), `test:e2e`, `test:eval`, `test:crap`
([[crap-typescript]]), `test:mutate` ([[mutation-testing-typescript]]). *Marked
inferred:* these appear observational-only in CI — the `frontend-tests` job runs
`pnpm test` = `vitest run --project node --project jsdom`, which excludes the
`arch`/`e2e`/`eval` projects.

## knip specifics

Detects dead code (unused files, unused exports) and unused/undeclared
dependencies across a pnpm monorepo. Config: `nogai/knip.json`.

```json
{
  "$schema": "https://unpkg.com/knip@5/schema.json",
  "ignoreExportsUsedInFile": true,
  "workspaces": { "nogai": { "entry": [...], "project": [...], "ignore": [...],
    "ignoreDependencies": [...], "vitest": {...}, "next": {...} }, ... }
}
```

Key conventions:
- **Per-workspace** config: `nogai`, `packages/event-sourcing-core`,
  `packages/logger`, `outbox_processor` each declare their own entry/project.
- **`entry`** teaches knip the framework's implicit entrypoints so they aren't
  reported as dead: Next.js `page/layout/route.ts`, `middleware.ts`,
  `instrumentation*.ts`, plus all config files. Plugin blocks (`vitest`, `next`)
  add more.
- **`ignoreExportsUsedInFile: true`** — an export only consumed in its own file
  isn't flagged (avoids churn on internal helpers).
- **`ignore`** excludes generated/vendored trees (`src/sdk/**`, `src/types/**`,
  `.next`, `.stryker-tmp`, `coverage`).
- **`ignoreDependencies`** whitelists deps knip can't statically see they're used
  (`tailwindcss`, `eslint-config-next`, `pdfjs-dist`, type-only `@types/*`, …).

Run: `pnpm run lint:knip` (root: `knip`). CI runs it inside `frontend-lint`.

## i18n validation specifics

A bespoke script — `nogai/scripts/validate-translations.ts` (invoked as
`lint:i18n` via `tsx`) — not an eslint plugin. It `process.exit(1)` on any
failure (blocking). Locales: `["en", "pt-BR", "pl"]`, `en` as reference.

Four checks (all observed in the script):
1. **Structural key parity** — every locale must have exactly the reference
   key set; reports `missing` and `extra` keys per locale.
2. **Placeholder consistency** — `{name}`-style placeholders in each translation
   must match the `en` value's placeholders (no missing/extra interpolations).
3. **Keys used in code exist** — statically extracts `useTranslations("ns")` /
   `getTranslations("ns")` var bindings and their `t("key")` calls, then flags
   any `ns.key` used in code but absent from message files.
4. **Namespace existence** — namespaces referenced in code must exist in
   translations.

CI runs it for both `nogai` and `landing-page` (`frontend-i18n` job).

## fast-check (property-based testing)

Property tests generate thousands of random inputs to assert invariants, rather
than fixed examples. Uses `@fast-check/vitest` (`^0.2.4`) + `fast-check`
(`^4.3.0`).

Idiom — `test.prop([arbitrary], { numRuns })`:

```ts
import { test } from "@fast-check/vitest";
// src/lib/markdown/__test__/normalize-tables.property.test.ts
test.prop([validTable], { numRuns: 1000 })("...", (input) => { ... });
test.prop([malformedSingleLineTable], { numRuns: 1000 })("...", ...);
```

Observed usage:
- **`nogai`**: markdown table normalizer — `normalize-tables.property.test.ts`
  with custom **arbitraries** (`__test__/arbitraries/table.arbitrary.ts`)
  modelling valid/malformed/streaming table inputs; `numRuns` 300–1000 per
  property. This file matches the `node` project's `src/lib/**/*.test.ts`
  include, so it runs inside the default `pnpm test` gate (**blocking**).
- **`packages/agent-react`**: `agent.property.test.ts`,
  `schema.property.test.ts`, `schema-utils.property.test.ts`,
  `providers/generateStructured.property.test.ts` — run by that package's own
  `frontend-tests` matrix leg.

Convention: property tests live beside example tests, named `*.property.test.ts`,
with reusable arbitraries factored into an `arbitraries/` folder.

## Adjacent

[[architecture-tests]] — the tsarch `arch` vitest project (dependency-direction
rules). [[crap-typescript]] · [[mutation-testing-typescript]] — deeper
test-strength gates, run out-of-band. [[qa-chain-python]] — sibling chain.
