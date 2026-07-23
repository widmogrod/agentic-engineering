# agentic-engineering

A collection of opinionated engineering practices, conventions, and patterns
designed to increase confidence in AI agent outputs — distributed as a
Claude Code plugin marketplace.

The idea: agents produce trustworthy code when explicit best practices, gates,
and workflows are installed alongside them — instead of improvised per session.
Conventions are mined from production codebases ([docs/reference/](docs/reference/README.md)),
distilled into installable skills, and enforced through mechanical quality gates.

## Install

```
/plugin marketplace add widmogrod/agentic-engineering
/plugin install python-dev@agentic-engineering
/reload-plugins
```

Installing a knowledge pack (like `python-dev`) pulls in the `dev` workflow
plugin as a dependency.

## Plugins

| Plugin | Role | Status |
|---|---|---|
| [`dev`](plugins/dev/) | Language-agnostic workflow engine: `/dev:*` commands, knowledge-doc format, (planned) gated subagent execution | usable |
| [`python-dev`](plugins/python-dev/) | Python knowledge pack (uv): service conventions, QA toolchain with CRAP gate, project templates | usable |
| [`typescript-dev`](plugins/typescript-dev/) | TypeScript knowledge pack (pnpm): type-checked tests with vitest, prettier formatting, QA chain | usable |

## Commands

### `/dev:init <ecosystem> <archetype> [member=archetype ...]`

Scaffold an opinionated project in the current directory. Resolves the
ecosystem's knowledge pack (`<ecosystem>-dev`), instantiates the archetype's
template tree (never overwrites existing files), creates the
`docs/{plan,concepts,entities,summaries}/` knowledge base, and binds the
project to its governing skills via `CLAUDE.md`.

```
/dev:init python fastapi                # standalone FastAPI service
/dev:init python workspace api=fastapi  # workspace topology (planned)
```

For **existing** projects, don't scaffold — use a knowledge pack's setup skill
directly (see `/python-dev:qa-toolchain` below).

### `/dev:brainstorm [topic]`

Structured design conversation at **signature altitude**: method signatures,
data flow, state machines, invariants — never implementation bodies. Grounds
itself in `docs/concepts/` and `docs/entities/` (prior decisions bind),
proposes 2-3 approaches with trade-offs, iterates, and converges on a design
summary. The notation discipline (arrow data-flow, state tables, error
channels as part of the contract) ships as a bundled reference. Ends by
offering `/dev:plan` — never by implementing.

### `/dev:plan [feature-name]`

Crystallizes the agreed design into `docs/plan/YYYY-MM-DD-<feature>-plan.md` —
the **contract and ledger** `/dev:implement` will execute. Decomposes the work
into 2-6 vertical slices (each cuts through all layers and ends in something
observable; riskiest first), configures the gates and human pause points in
frontmatter, and stubs new concepts/entities into the knowledge base with
`[[wiki-links]]`.

Before hand-off, the **plan-critic** agent (read-only) adversarially reviews
the plan on five fronts: acceptance-criteria *checkability* (verified against
the real code — a criterion that can't work against the actual types is
blocking), simplicity/YAGNI, conflicting requirements, **facts-not-opinions**
(every factual claim verified in the repo; opinions allowed only as recorded
decisions with rationale), and slice quality. The plan stays `draft` until
the user approves it; approval commits the plan file.

The knowledge format itself (`docs/{plan,concepts,entities,summaries}/`,
frontmatter, wiki-links, append-only ledger rules) is defined in a shared
Claude-only skill (`dev:knowledge`) that all commands consult.

### `/dev:implement <path/to/plan.md>`

Executes an approved plan slice by slice through three gated subagents, with
the plan file as the single source of truth — **in an isolated git worktree**
branched from the branch the session started on (`plan/<feature>` under
`.claude/worktrees/`), so parallel Claude Code instances implementing
different plans in one repo never touch each other's trees:

```
for each slice:
  slice-implementer   # domain/ports -> tests -> implementation -> wiring
  critic-reviewer     # adversarial, READ-ONLY: tries to refute spec/design/
                      #   convention compliance + test honesty (max 2 revision rounds)
  qa-gate             # runs the pack's mechanical chain verbatim; PASS/FAIL,
                      #   no fixing, no interpreting, no relaxing (max 2 retries)
  ledger              # append row: divergence, tech debt, human-review flag
  commit              # one commit per slice, plan update included
  pause?              # stops at plan-declared pause_after checkpoints
```

Gates exhausted → the loop STOPS with a `blocked` ledger row and verbatim
failures — it never lowers the bar to keep moving. Resume is built in: the
deterministic branch/worktree names double as discovery and same-plan mutual
exclusion, so rerunning continues from the first unfinished slice. On
completion it fills the plan Summary, distills `docs/summaries/<feature>.md`,
reports open tech debt as the backlog — then **asks before merging back**:
rebase onto the base tip, re-run the full QA chain on the rebased tree,
`merge --ff-only` (the base receives byte-identically the tree that was
tested), clean up the worktree. Every non-success path keeps the worktree.

### `/python-dev:qa-toolchain [setup|run]`

Set up or run the opinionated Python QA chain in a uv project:

```
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest                      # writes coverage.json
uv run python scripts/crap.py      # CRAP gate: cc² × (1−cov)³ + cc
```

- **setup** retrofits an existing project: adds dev deps (`ruff mypy pytest
  pytest-cov radon`), copies the bundled `crap.py` gate script, merges config
  into `pyproject.toml` without clobbering yours, and calibrates thresholds
  against the project's current state (coverage floor = current coverage,
  ratcheted up over time) instead of imposing punishing defaults.
- **run** executes the chain in order (order matters: CRAP reads the coverage
  pytest writes) and guides fixing offenders — add tests or reduce complexity,
  never silently raise thresholds.

The CRAP gate flags a function only when **both** `cc > min-complexity` (5) and
`crap > threshold` (30) hold; configured via `[tool.crap]` in `pyproject.toml`.

### `/typescript-dev:qa-toolchain [setup|run]`

Set up or run the opinionated TypeScript QA chain in a pnpm project:

```
pnpm fmt:check      # prettier --check .   (defaults + organize-imports plugin)
pnpm lint           # eslint .             (flat config, type-aware, tests included)
pnpm type-check     # tsc -p tsconfig.dev.json --noEmit
pnpm test           # vitest run --coverage
```

The load-bearing pattern is the **dual tsconfig**: `tsconfig.json` (emit,
excludes tests) + `tsconfig.dev.json` (extends it, `noEmit`, re-includes
`__test__/**` at the **same strict level**) — so tests are type-checked as
real code. The dev config may only widen `include`, never loosen strictness.
Same retrofit philosophy as the Python pack: merge-don't-clobber, calibrate
gates against current reality, every workspace member must carry the scripts
(a member without `type-check` isn't passing the chain — it's invisible to it).

### Planned commands

| Command | Purpose |
|---|---|
| `/dev:add <ecosystem> <archetype> <name>` | Grow an existing workspace with a new member |

## Knowledge skills (auto-triggered)

These load automatically when the agent works on matching code; you can also
invoke them explicitly to read the conventions.

| Skill | Governs |
|---|---|
| `python-dev:fastapi-service` | FastAPI service layout: flat package, `main.py` as sole composition root, per-endpoint `api/<ep>/{router,model,service}.py` packages, ports as `typing.Protocol`, all env access in `config.py` fail-fast |
| `python-dev:clean-architecture` | Ports as `typing.Protocol`, sole composition root (`main.py`), in-memory adapters as production code proven by contract-test suites, errors-as-values (`Result`/`Ok`/`Err`) at port boundaries |
| `typescript-dev:clean-architecture` | Hexagonal service modules (`domain/application/infrastructure`), dependency-direction rules with the `factory.ts` composition-root exception, three-tier DI, typed cross-service events — enforced by contract specs + `tsc` + tsarch architecture tests |
| `python-dev:templates` | Internal registry used by `/dev:init` to locate the pack's templates (not user-facing) |
| `typescript-dev:testing` | Vitest conventions: colocated `__test__/` dirs, filename-suffix routing to vitest projects, tests at full type strictness (no `any`/`@ts-expect-error` to make a test compile), typed mock factories that `satisfies` the real interface |

## Templates

| Archetype | Ecosystem | Description |
|---|---|---|
| `fastapi` | python | FastAPI service following the service-layout conventions; ships green — the instantiated tree passes `ruff check`, `ruff format`, `mypy --strict`, and its test suite |

Each template carries an `archetype.json` manifest (kind, standalone,
defaultDir, governing skills, variables) — the composition contract that lets
`/dev:init` stay generic and archetypes compose into workspaces.

## Design & research

- [Conceptual outline](docs/plan/2026-07-10-conceptual-outline.md) — the
  three-layer architecture (workflow engine / knowledge packs / project
  instance), archetype composition model, command designs.
- [Reference catalog](docs/reference/README.md) — 34 convention docs mined from
  production codebases: quality gates, Python conventions, clean architecture,
  workspace layouts, Docker, cross-language contracts. The raw material skills
  are distilled from.

## Development

```
claude plugin validate .
```

Test the full pipeline locally without pushing:

```
claude plugin marketplace add /path/to/agentic-engineering
claude plugin install python-dev@agentic-engineering --scope local
# after committing changes:
claude plugin update python-dev@agentic-engineering --scope local
```

Repository layout:

```
.claude-plugin/marketplace.json    # the marketplace manifest
plugins/<plugin>/
├── .claude-plugin/plugin.json     # plugin manifest (only file in .claude-plugin/)
├── skills/<name>/SKILL.md         # skills (+ scripts/, references/ per skill)
└── templates/<archetype>/         # archetype.json + tree/ (knowledge packs only)
docs/plan/                         # design docs (temporal)
docs/reference/                    # mined conventions (timeless, evidence-cited)
```

Plugins intentionally carry no `version` yet — while under active development
they are versioned by commit SHA, so installs update on every push. Semver
comes with the first stable release (`--strict` validation will pass from then
on). CI runs `claude plugin validate .` on every push and PR.
