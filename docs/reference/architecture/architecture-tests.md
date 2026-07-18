---
type: reference
status: draft
source:
  - /Users/gabriel/Work/gh/legal-ai/frontend/nogai/src/services/__test__/architecture.contract.ts (observed)
  - /Users/gabriel/Work/gh/legal-ai/frontend/nogai/src/services/__test__/vitest.tsarch.setup.ts (observed)
  - /Users/gabriel/Work/gh/legal-ai/frontend/nogai/src/__test__/architecture.test.ts (observed)
  - /Users/gabriel/Work/gh/legal-ai/frontend/nogai/vitest.config.ts (observed)
  - /Users/gabriel/Work/gh/legal-ai/frontend/nogai/tsconfig.tsarch.json (observed)
links: ["[[qa-chain-typescript]]", "[[service-layout]]"]
---

# Architecture tests — executable dependency rules (tsarch)

Architecture constraints (layer boundaries, dependency direction, file
placement, absence of cycles) are expressed as **executable, versioned tests**
that live beside the code and fail the build when the import graph drifts. The
TS implementation uses **`tsarch`** (a TypeScript port of ArchUnit) inside a
dedicated vitest project.

## How the rules are expressed

`tsarch` exposes a fluent, readable DSL over the project's import graph. A rule
is built, then asserted with a custom async matcher:

```ts
// src/services/__test__/architecture.contract.ts
const rule = filesOfProject()
  .inFolder(`${servicePath}/domain`)
  .shouldNot()
  .dependOnFiles()
  .inFolder(`${servicePath}/infrastructure`);

await expect(rule).toPassAsync();
```

`toPassAsync` is a custom vitest matcher (`vitest.tsarch.setup.ts`) that calls
`rule.check()` and turns a thrown violation into a failed assertion:

```ts
expect.extend({
  async toPassAsync(rule: unknown) {
    try { await (rule as { check: () => Promise<void> }).check();
      return { pass: true, message: () => "Architecture rule passed" };
    } catch (error) {
      return { pass: false, message: () => (error as Error).message };
    }
  },
});
```

DSL vocabulary observed: `filesOfProject(tsconfig?)`, `.inFolder(p)`,
`.matchingPattern(regex)`, `.should()` / `.shouldNot()`, `.dependOnFiles()`,
`.beInFolder(p)`, `.beFreeOfCycles()`.

## The reusable contract factory

The core pattern: instead of hand-writing rules per module, a single factory
`createServiceArchitectureTests({ serviceName, servicePath, infrastructurePatterns })`
generates the **same standardized suite for every service**. Each service test
file is three lines:

```ts
// src/services/knowledge-graph/__test__/architecture.test.ts
createServiceArchitectureTests({
  serviceName: "KnowledgeGraph",
  servicePath: "src/services/knowledge-graph",
  infrastructurePatterns: ["postgres", "static-lens-registry"],
});
```

15 services adopt the contract (one `architecture.test.ts` each). This makes the
hexagonal / clean-architecture layering (see [[service-layout]]) a mechanically
enforced invariant rather than a documented aspiration.

## Rules enforced by the contract

Layers: **domain** (pure logic) → **application** (orchestration) →
**infrastructure** (adapters) → **di** (wiring). Dependencies must point inward.

| Category | Rule |
|----------|------|
| Domain boundaries | domain **shouldNot** depend on `infrastructure`, `application`, `di`, or `db/schemas` |
| Application boundaries | application **shouldNot** depend on `infrastructure` or `di`; **should** depend on `domain` |
| Infrastructure | infra **should** depend on `domain` and may import `db/schemas`; is never imported by domain |
| Dependency direction | infra/application never imported *by* domain (no reverse deps) |
| File organization | `container.ts` → `di/`; `service.ts` + `listeners.ts` → `application/`; files matching each `infrastructurePattern` → `infrastructure/` |
| Anti-patterns | service tree **beFreeOfCycles**; test files don't depend on other test files |
| Domain purity | domain **shouldNot** touch `lib.dom` (browser File API) or `node:stream` — must be platform-agnostic (Node/browser/edge) |

Project-wide rules (`src/__test__/architecture.test.ts`) enforce cross-cutting
policy, e.g. **centralized UUID generation**: only `src/lib/utils/uuid.ts` may
import the `uuid` package or `node:crypto`; no file may call
`crypto.randomUUID()` directly. This complements — and is stricter than — the
eslint `no-restricted-syntax` rule that catches the direct call site.

## How it runs

A separate vitest project isolates these slow, deterministic tests:

```ts
// vitest.config.ts — Project 5
{ name: "arch", include: ["src/**/architecture.test.ts"],
  testTimeout: 120000, retry: 0,
  isolate: false, fileParallelism: false } // share tsarch's parse cache
```

- Invoked with `pnpm test:arch` (`vitest run --project arch`); `retry: 0`
  (deterministic — a failure is real). `isolate:false` + `fileParallelism:false`
  let the files share tsarch's expensive import-graph cache.
- Rules resolve against `tsconfig.tsarch.json` (extends the base, `noEmit`,
  excludes tests / `.next` / `dist`) so the graph reflects production code only.
- *Inferred:* excluded from the default `pnpm test` CI job (see
  [[qa-chain-typescript]]) — it is a separate opt-in project.

## Language-agnostic essence

The pattern transfers to any language with an ArchUnit-style tool (Java
ArchUnit, .NET NetArchTest, Python `pytestarch` / import-linter):

1. **Encode architecture as tests, co-located and versioned** — the import graph
   is asserted, not just diagrammed; violations fail CI like any other test.
2. **A reusable contract factory** — parameterize one canonical rule set by
   module path so every module inherits identical layering guarantees; adopting
   it for a new module is a few lines.
3. **Rules operate on the dependency graph**, catching what a linter cannot: an
   import from the wrong layer, a reverse dependency, a cycle across files.
4. **Keep them out-of-band** from the fast unit suite (slow graph analysis),
   deterministic, no retries.
