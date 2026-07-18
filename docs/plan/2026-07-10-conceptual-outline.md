---
type: plan
status: draft
created: 2026-07-10
links: ["[[plugin-marketplace-spec]]"]
---

# Agentic Engineering — Conceptual Outline

A collection of opinionated engineering practices, conventions, and patterns designed
to increase confidence in AI agent outputs — distributed as a Claude Code plugin
marketplace, consumable via the open Agent Skills standard.

## Vision

A developer bootstraps in two commands:

```
/plugin marketplace add widmogrod/agentic-engineering
/plugin install python-dev@agentic-engineering
```

then drives a full engineering loop:

```
/dev:init python fastapi        # opinionated project scaffold + knowledge base
/dev:brainstorm                 # design at signature/data-flow altitude
/dev:plan                       # crystallize into docs/plan/YYYY-MM-DD-{feature}-plan.md
/dev:implement <plan.md>        # gated, subagent-driven implementation loop
```

Every step is backed by installable, versioned knowledge (skills) so agents work
from explicit best practices instead of improvisation.

## Architecture: three layers

The core separation is **workflow** vs. **knowledge** vs. **project instance**:

| Layer | Artifact | Contains | Update path |
|---|---|---|---|
| Workflow engine | `dev` plugin | `/dev:*` commands, subagents (implementer, critic, QA gate), knowledge-doc format, archetype contract | `/plugin update` |
| Knowledge packs | `python-dev`, `typescript-dev`, … | Ecosystem toolchain + archetype skills, project templates, QA gate config | `/plugin update` |
| Project instance | user's repo after `/dev:init` | Scaffolded layout, `docs/` knowledge base, thin `.claude/` binding | versioned with the code, team-customizable |

Rationale for the split: process and how-to knowledge stay updatable and uniform in
plugins; templates and accreted project decisions live in the repo where teams can
diverge and version them. Plugin commands are namespaced `/plugin-name:skill-name`,
so a plugin literally named `dev` yields `/dev:init` for free.

## Repository layout (this repo = marketplace monorepo)

```
agentic-engineering/
├── .claude-plugin/
│   └── marketplace.json              # name: "agentic-engineering", lists all plugins
├── plugins/
│   ├── dev/                          # WORKFLOW ENGINE → /dev:* commands
│   │   ├── .claude-plugin/plugin.json
│   │   ├── skills/
│   │   │   ├── init/                 # /dev:init <ecosystem> <archetype>
│   │   │   ├── add/                  # /dev:add — grow an existing workspace
│   │   │   ├── brainstorm/           # + references/technical-communication.md
│   │   │   ├── plan/                 # + assets/plan-template.md
│   │   │   ├── implement/            # orchestration loop + references/gates.md
│   │   │   └── knowledge/            # docs/{plan,concepts,entities,summaries} format
│   │   │                             #   (user-invocable: false — background skill)
│   │   └── agents/
│   │       ├── slice-implementer.md
│   │       ├── critic-reviewer.md    # adversarial, read-only tools
│   │       └── qa-gate.md            # mechanical verdicts: lint/types/tests/CRAP
│   │
│   ├── python-dev/                   # KNOWLEDGE PACK (uv-based)
│   │   ├── .claude-plugin/plugin.json    # dependencies: ["dev"]
│   │   ├── skills/
│   │   │   ├── uv-toolchain/         # CORE — applies to every variant
│   │   │   ├── testing/              # CORE
│   │   │   ├── qa-toolchain/         # CORE — ruff/mypy/coverage + scripts/crap_metric.py
│   │   │   ├── fastapi-service/      # ARCHETYPE — vertical slice knowledge
│   │   │   │   └── references/{api-endpoint,validation,auth,async-processing,
│   │   │   │                   outbox,idempotency,migrations,testing,observability}.md
│   │   │   ├── python-package/       # ARCHETYPE — public API, semver, py.typed
│   │   │   └── uv-workspace/         # TOPOLOGY — member deps, shared config
│   │   └── templates/
│   │       ├── _shared/              # pyproject fragments, ruff.toml, mypy.ini
│   │       ├── fastapi/    { archetype.json, tree/ }
│   │       ├── package/    { archetype.json, tree/ }
│   │       └── workspace/  { archetype.json, tree/ }   # kind: workspace-root
│   │
│   └── typescript-dev/               # KNOWLEDGE PACK (pnpm-based), identical shape
│       ├── skills/  { pnpm-toolchain, testing, nextjs-app, ts-package, pnpm-workspace }
│       └── templates/ { _shared, nextjs, package, workspace }
├── docs/                             # dogfood the knowledge format on this repo itself
│   ├── plan/  ├── concepts/  ├── entities/  ├── summaries/  └── reference/
├── README.md
└── CONTRIBUTING.md
```

Spec constraints that shape this (see [[plugin-marketplace-spec]]):

- Component dirs (`skills/`, `agents/`, `templates/`…) sit at **plugin root**; only
  `plugin.json` goes inside `.claude-plugin/`.
- Installed plugins **cannot reference files outside their own directory** — sharing
  across plugins requires marketplace-level symlinks (dereferenced and copied on install).
- Skills use progressive disclosure: ~100 tokens at discovery, full SKILL.md (<500 lines)
  on activation, `references/` on demand. Bundling many variants in one plugin is cheap.
- `SKILL.md` follows the open Agent Skills standard (agentskills.io), so the same
  `skills/` directories are consumable by `npx skills add` and 40+ other agents.

## Variants and composition

The trap to avoid: treating `python-fastapi`, `python-package`, `python-workspace` as
flat siblings. They are three different dimensions:

1. **Ecosystem** → one plugin per ecosystem (`python-dev` = uv, `typescript-dev` = pnpm).
   Owns toolchain knowledge: package manager, lint, typing, testing. One plugin per
   *variant* would duplicate ~70% of this and fight the no-cross-plugin-references rule.
2. **Archetype** → a variant inside the plugin (`fastapi`, `package`, `worker` /
   `nextjs`, `package`). Owns shape-specific knowledge + template.
3. **Topology** → standalone vs. workspace. **Workspace is not a variant — it is a
   composition operator over archetypes.** A uv workspace contains a fastapi member
   and a package member; a pnpm workspace contains a nextjs app and packages.

### The archetype contract: `archetype.json`

Each template carries a manifest; `/dev:init` in the `dev` plugin stays generic and
just interprets manifests. The schema is owned by `dev` (the contract), implemented
by each ecosystem pack — adding `go-dev` later means implementing the contract, not
new machinery.

```json
{
  "name": "fastapi",
  "kind": "member",                    // "member" | "workspace-root"
  "standalone": true,                  // may also be initialized alone
  "defaultDir": "apps/{{name}}",       // placement inside a workspace
  "skills": ["python-dev:fastapi-service", "python-dev:testing"],
  "vars": ["name", "port"]
}
```

```json
{
  "name": "workspace",
  "kind": "workspace-root",
  "memberRoots": { "apps": ["fastapi", "worker"], "packages": ["package"] },
  "register": "pyproject.toml#tool.uv.workspace.members",
  "skills": ["python-dev:uv-workspace"]
}
```

### Unifying principle

**Every archetype is written as a workspace member; standalone is a workspace of one**
(a thin shell around the same tree). uv and pnpm both make this natural — a member's
manifest is nearly identical either way; only the root differs. One instantiation code
path serves both cases; the workspace root additionally registers the member in
`[tool.uv.workspace].members` / `pnpm-workspace.yaml`.

### Command grammar

```
/dev:init python fastapi
/dev:init python package
/dev:init python workspace api=fastapi core=package worker=worker
/dev:init typescript workspace web=nextjs ui=package

/dev:add python package billing       # workspaces GROW — add member to existing repo
/dev:add typescript nextjs admin
```

`/dev:add` is arguably the primitive; `init workspace` = create root shell + N adds.
`/dev:add` detects ecosystem and member roots from the existing workspace config.

### Knowledge routing in a monorepo

- **`paths:` frontmatter** on SKILL.md auto-activates skills by glob: `fastapi-service`
  activates for `apps/api/**`, `python-package` for `packages/**`.
- **Nested `.claude/skills/<subdir>`** gives directory-scoped, qualified skills
  (`/apps/api:deploy`); `/dev:add` can drop a thin member-local pointer skill per member.

### Cross-ecosystem workspaces (explicitly punted, not precluded)

`nextjs frontend + fastapi backend` in one repo fits neither plugin. Because
`archetype.json` is a `dev`-level contract, a future
`/dev:init workspace web=typescript/nextjs api=python/fastapi` can compose across
packs — each ecosystem owns its sub-root (`frontend/` pnpm, `backend/` uv). Only the
init orchestration needs to learn multi-root; the manifests already carry enough.

## The workflow commands

### /dev:init `<ecosystem> <archetype>`

Verifies the knowledge pack is installed (prompts `/plugin install` otherwise),
instantiates the template tree (via `${CLAUDE_PLUGIN_ROOT}/templates/…`), creates the
`docs/{plan,concepts,entities,summaries}/` skeleton, writes a CLAUDE.md binding the
project to the installed skills.

### /dev:brainstorm

Conversational design at **signature altitude**: method signatures, data-flow diagrams,
state machines — never implementation bodies. The discipline is encoded in
`references/technical-communication.md` (including a small meta-language for flows).
Actively pulls prior decisions from `docs/concepts/` and `docs/entities/`. Ends by
offering `/dev:plan`.

### /dev:plan

Writes `docs/plan/YYYY-MM-DD-{feature}-plan.md` from a template with frontmatter
(status, slices, gate config, pause points, links). This file is the **contract** that
`/dev:implement` consumes — and doubles as the execution **ledger**. Newly discovered
concepts/entities get stub files with `[[wiki-links]]` back to the plan.

### /dev:implement `<plan.md>`

The orchestration loop, run slice by slice with subagents:

```
for each vertical slice in plan:
  1. slice-implementer: domain model → tests → implementation
  2. critic-reviewer:   adversarial review vs. spec + pack best practices
  3. qa-gate:           lint + types + tests + coverage + CRAP → PASS/FAIL
  4. FAIL → bounded retry (max 2), then STOP and involve the human
  5. PASS → update plan ledger: what was built, divergence from plan,
            tech debt created-not-addressed, human-review-recommended flag
  6. commit the slice; next slice
```

Design decisions:

- **The plan file is the shared state**, not conversation memory. Every subagent reads
  it fresh; the orchestrator appends to it. Resumable, auditable, survives context
  compaction.
- **Separation of duties**: the critic is instructed to *refute* spec-compliance and
  holds read-only tools — it cannot fix what it reviews.
- **Mechanical gates**: the pack's `qa-toolchain` defines exact commands and thresholds.
  CRAP = comp² × (1 − cov)³ + comp, computed by a bundled script (radon + coverage.xml
  for Python). Deterministic verdicts keep the loop honest.
- **Explicit human checkpoints**: stop conditions in plan frontmatter
  (e.g. `pause_after: [slice-1, schema-changes]`), not vibes.
- Start with plain sequential subagents driven from the skill body (simple, portable);
  Workflow-based orchestration is a later optimization.

## The knowledge format (`docs/`)

A lightweight Zettelkasten-with-frontmatter convention, defined once in the `dev`
plugin's `knowledge` skill and shared by all commands:

| Directory | Nature | Content |
|---|---|---|
| `docs/plan/` | temporal, append-only | intent + ledger of what actually happened |
| `docs/concepts/` | timeless | "how we do X here" — starts as pointer to a plugin skill, accretes project deviations |
| `docs/entities/` | timeless | domain nouns: invariants, states, key operation signatures |
| `docs/summaries/` | generated | post-implementation distillation, written at end of /dev:implement |

Files cross-link with `[[wiki-links]]` and carry `type/status/links` frontmatter.
Plans decay; concepts and entities compound — they are the durable context every
future agent session inherits.

## Mechanics

- **Versioning**: omit `version` during development → users update per commit SHA;
  adopt semver once stable.
- **CI**: GitHub Action running `claude plugin validate . --strict` on every PR
  (validates marketplace schema, plugin manifests, SKILL.md frontmatter).
- **Discipline**: every SKILL.md < 500 lines, detail pushed to `references/` —
  one file per concept.
- **Dependencies**: knowledge packs declare `"dependencies": ["dev"]` so installing
  a pack pulls the workflow engine.

## Open questions

1. **Knowledge residence**: hybrid chosen (process/how-to in plugins; templates +
   accreted decisions in repo). Possible escape hatch: `/dev:init --vendor` copies
   skills into the repo for teams wanting full ownership.
2. **How opinionated is the blessed stack?** Vertical slice with outbox + queues
   implies concrete choices (FastAPI + Postgres + which task queue?). Pick one stack
   for v1 — opinionation is the product.
3. **Naming**: `dev` is short with great ergonomics but generic; `ae` (`/ae:init`) is
   the fallback if collisions bite. Keeping `dev`.

## First milestone (skeleton spike)

Prove the distribution pipeline before writing the bulk of the knowledge:

1. `marketplace.json` + `dev` plugin with a working `/dev:init`
2. `python-dev` with one skill (`fastapi-service` + 2–3 references) and one template
3. Install end-to-end from GitHub; validate in CI
4. **Load-bearing assumption to verify first**: `templates/` as plain data dirs inside
   a plugin, read via `${CLAUDE_PLUGIN_ROOT}`, survive install/caching intact.
