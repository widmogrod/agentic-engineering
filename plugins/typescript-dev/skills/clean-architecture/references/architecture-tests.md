# Architecture tests — enforcing the layers with tsarch

Express the layer rules from the clean-architecture skill as executable,
versioned tests using **tsarch** (a TypeScript port of ArchUnit) inside a
dedicated vitest project. The import graph is asserted, not diagrammed:
a wrong-layer import, a reverse dependency, or a cycle fails like any other
test — things a linter cannot catch.

## 1. Install and dedicated tsconfig

```
pnpm add -D tsarch
```

Rules must resolve against production code only, so give tsarch its own
tsconfig:

```jsonc
// tsconfig.tsarch.json
{
  "extends": "./tsconfig.json",
  "compilerOptions": { "noEmit": true },
  "exclude": ["**/__test__/**", ".next", "dist"]
}
```

## 2. The vitest `arch` project

Per the `testing` skill's project conventions, arch tests are a separate,
opt-in project — slow graph analysis stays out of the fast unit suite:

```ts
// vitest.config.ts — add to test.projects
{
  test: {
    name: "arch",
    include: ["src/**/architecture.test.ts"],
    environment: "node",
    testTimeout: 120_000,
    retry: 0,             // deterministic — a failure is real, never retry
    isolate: false,       // share tsarch's expensive import-graph cache
    fileParallelism: false,
    setupFiles: ["./src/services/__test__/vitest.tsarch.setup.ts"],
  },
}
```

- Exclude `src/**/architecture.test.ts` from the default projects' globs so it
  never double-runs.
- `environment: "node"` and the `setupFiles` entry are completions beyond the
  source repo's config snippet, consistent with the `testing` skill's
  conventions.
- Script: `"test:arch": "vitest run --project arch"`. The source repo runs
  this by hand only; we prescribe wiring it as its own CI job (or scheduled
  run) because a check nobody runs silently rots — see the `testing` skill.

## 3. The `toPassAsync` matcher

A tsarch rule object exposes `check()`; wrap it in a custom matcher so rules
read as assertions:

```ts
// src/services/__test__/vitest.tsarch.setup.ts
import { expect } from "vitest";

expect.extend({
  async toPassAsync(rule: unknown) {
    try {
      await (rule as { check: () => Promise<void> }).check();
      return { pass: true, message: () => "Architecture rule passed" };
    } catch (error) {
      return { pass: false, message: () => (error as Error).message };
    }
  },
});
```

Add a `declare module "vitest"` augmentation for `toPassAsync(): Promise<void>`
so tests type-check at full strictness, and allow-list `toPassAsync` in the
ESLint `vitest/expect-expect` rule if you use it.

## 4. The reusable contract factory

Do not hand-write rules per service. One factory generates the identical suite
for every service; adopting it costs three lines per service.

```ts
// src/services/__test__/architecture.contract.ts
import { describe, expect, it } from "vitest"; // explicit — no globals:true
import { filesOfProject } from "tsarch";

export interface ServiceArchitectureOptions {
  serviceName: string; // "Conversation" — used in describe() titles
  servicePath: string; // "src/services/conversation"
  /** filename fragments whose files must live in infrastructure/ */
  infrastructurePatterns?: string[];
}

export function createServiceArchitectureTests(
  options: ServiceArchitectureOptions,
): void {
  const { serviceName, servicePath, infrastructurePatterns = [] } = options;
  const files = () => filesOfProject("tsconfig.tsarch.json");

  describe(`${serviceName} architecture`, () => {
    // ── Dependency direction ─────────────────────────────────────────
    it("domain does not depend on infrastructure", async () => {
      await expect(
        files()
          .inFolder(`${servicePath}/domain`)
          .shouldNot()
          .dependOnFiles()
          .inFolder(`${servicePath}/infrastructure`),
      ).toPassAsync();
    });

    // Same shape — bodies elided:
    it("domain does not depend on application", /* … shouldNot().dependOnFiles() */);
    it("domain does not depend on src/di", /* … */);
    it("domain does not depend on src/db/schemas", /* … */);
    it("application does not depend on src/di", /* … */);

    it("application depends on domain", async () => {
      await expect(
        files()
          .inFolder(`${servicePath}/application`)
          .should()
          .dependOnFiles()
          .inFolder(`${servicePath}/domain`),
      ).toPassAsync();
    });

    it("infrastructure depends on domain", /* … should().dependOnFiles() */);
    // No rule bars infrastructure from src/db/schemas — the schema ban is
    // domain-only; adapters are exactly where schema imports belong.

    // ── The composition-root exemption, carved into the rule ─────────
    // PRESCRIBED, not observed: in the source repo this rule carries no
    // matchingPattern exclusion — the rule and the factory exception
    // coexist without a recorded carve-out, honored in spirit by keeping
    // all infrastructure imports in the one factory file. We prescribe
    // encoding the exemption explicitly so the rule passes on conforming
    // services while still firing for every other application file.
    it("application does not depend on infrastructure (factory.ts exempt)", async () => {
      await expect(
        files()
          .inFolder(`${servicePath}/application`)
          // factory.ts IS the composition root — the one sanctioned
          // infrastructure importer. See "Exemptions" below.
          .matchingPattern("^(?!.*factory\\.ts$).*$")
          .shouldNot()
          .dependOnFiles()
          .inFolder(`${servicePath}/infrastructure`),
      ).toPassAsync();
    });

    // ── Cycles ───────────────────────────────────────────────────────
    it("service tree is free of cycles", async () => {
      await expect(
        files().inFolder(servicePath).should().beFreeOfCycles(),
      ).toPassAsync();
    });

    // ── Domain platform-purity ───────────────────────────────────────
    // Domain must run on Node, browser, and edge alike: assert domain files
    // do not depend on files providing lib.dom (browser File API) or
    // node:stream. Bodies elided — same shouldNot().dependOnFiles() shape.
    it("domain is platform-agnostic (no lib.dom)", /* … */);
    it("domain is platform-agnostic (no node:stream)", /* … */);

    // ── File placement ───────────────────────────────────────────────
    it("container files live under di/", async () => {
      await expect(
        files().matchingPattern("container\\.ts$").should().beInFolder("di"),
      ).toPassAsync();
    });
    it("service.ts and listeners live under application/", /* … beInFolder() */);
    for (const pattern of infrastructurePatterns) {
      it(`${pattern} files live under infrastructure/`, /* … beInFolder() */);
    }

    // ── Anti-patterns ────────────────────────────────────────────────
    // Must build on the DEFAULT graph — bare filesOfProject(), as the
    // source contract uses — because tsconfig.tsarch.json excludes
    // __test__/, which would leave no test files in the graph and make
    // this rule vacuously green.
    it("test files do not depend on other test files", /* … filesOfProject() … */);
  });
}
```

DSL vocabulary: `filesOfProject(tsconfig?)`, `.inFolder(p)`,
`.matchingPattern(regex)`, `.should()` / `.shouldNot()`, `.dependOnFiles()`,
`.beInFolder(p)`, `.beFreeOfCycles()`. Note: `.beInFolder()` comes from the
observed usage in our reference repo, not tsarch's public README — verify your
installed tsarch version exposes it (and pin the version) before relying on
the file-placement rules.

## 5. Per-service adoption — three lines

```ts
// src/services/conversation/__test__/architecture.test.ts
createServiceArchitectureTests({
  serviceName: "Conversation",
  servicePath: "src/services/conversation",
  infrastructurePatterns: ["postgres", "policy-adapter"],
});
```

Every new service MUST add this file. A service without it is not exempt from
the layering — it is unenforced, which is a defect.

## 6. Project-wide rules

Cross-cutting policy that is not per-service gets its own
`src/__test__/architecture.test.ts`. Example from the source repo: centralized
UUID generation — only `src/lib/utils/uuid.ts` may import the `uuid` package
or `node:crypto`; no file may call `crypto.randomUUID()` directly. Graph rules
here complement (and are stricter than) the ESLint `no-restricted-syntax`
rule that catches the call site.

## 7. Exemptions — when a rule must be legitimately broken

Never delete or globally loosen a rule to get green. The protocol:

1. **Carve the exemption into the rule, explicitly and narrowly.** Exclude the
   one file via `.matchingPattern()` (as the factory exemption above does),
   with an inline comment naming the file and the reason. The rule keeps
   firing for everything else.
2. **Document the exception at the exempted file's top.** The source repo's
   subscription factory carries it literally: *"The ONLY file that imports
   from infrastructure."* A reader of the file must learn it is special
   without opening the contract.
3. **Make the carve-out reviewable.** The factory.ts exemption lives in the
   shared contract because it applies uniformly to every service (and, per
   section 4, encoding it there at all is our prescription — the source repo
   records no carve-out). If a service needs an additional legitimate
   carve-out, we prescribe extending `ServiceArchitectureOptions` with an
   explicit `exemptions` field so the exception is declared in that service's
   own `architecture.test.ts` — visible in the diff, owned by the service,
   and enumerable. The source repo lacks both mechanisms; we prescribe them
   so exemptions never accrete invisibly.

A red arch test therefore has exactly two resolutions: fix the import, or add
an explicit, documented, reviewed exemption. There is no third option.
