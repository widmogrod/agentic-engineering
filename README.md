# agentic-engineering

A collection of opinionated engineering practices, conventions, and patterns
designed to increase confidence in AI agent outputs — distributed as a
Claude Code plugin marketplace.

## Install

```
/plugin marketplace add widmogrod/agentic-engineering
/plugin install python-dev@agentic-engineering
```

Installing a knowledge pack (like `python-dev`) pulls in the `dev` workflow
plugin as a dependency.

## Use

```
/dev:init python fastapi        # scaffold an opinionated FastAPI service
/dev:brainstorm                 # design at signature altitude        (planned)
/dev:plan                       # crystallize into docs/plan/          (planned)
/dev:implement <plan.md>        # gated, subagent-driven execution     (planned)
```

## What's inside

| Plugin | Role |
|---|---|
| `dev` | Language-agnostic workflow engine: `/dev:*` commands, subagents, knowledge-doc format |
| `python-dev` | Python knowledge pack (uv): FastAPI service conventions, testing, QA toolchain, templates |

Design: [docs/plan/2026-07-10-conceptual-outline.md](docs/plan/2026-07-10-conceptual-outline.md).
Mined conventions backing the packs: [docs/reference/](docs/reference/README.md).

## Development

Validate the marketplace and all plugins:

```
claude plugin validate .
```

Plugins intentionally carry no `version` yet — while under active development they
are versioned by commit SHA, so installs update on every push. Semver comes with
the first stable release (`--strict` validation will pass from then on).
