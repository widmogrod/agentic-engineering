---
name: init
description: Scaffold an opinionated project layout for a given ecosystem and archetype, wire up the docs/ knowledge base, and bind the project to its knowledge-pack skills. Use when the user wants to bootstrap a new project or add opinionated structure to an empty repository.
argument-hint: "[ecosystem] [archetype] [member=archetype ...]"
---

# /dev:init — scaffold an opinionated project

Arguments given: `$ARGUMENTS`

Scaffold a project for `$0` (ecosystem, e.g. `python`, `typescript`) with archetype `$1`
(e.g. `fastapi`, `package`, `workspace`). Remaining arguments of the form
`member=archetype` are workspace members (only valid when archetype is `workspace`).

## Procedure

### 1. Resolve the knowledge pack

The knowledge pack for ecosystem `<eco>` is the plugin named `<eco>-dev`
(e.g. `python-dev`). Invoke its template registry skill with the Skill tool:
`<eco>-dev:templates`.

- If that skill is unavailable, the pack is not installed. Tell the user to run
  `/plugin install <eco>-dev@agentic-engineering` and STOP.
- The registry skill reports the absolute path of the pack's `templates/` directory
  and the available archetypes.

### 2. Read the archetype manifest

Read `<templates>/<archetype>/archetype.json`:

- `kind`: `member` (a standalone-capable project) or `workspace-root`
- `standalone`: whether it can be initialized outside a workspace
- `defaultDir`: where it lands when instantiated inside a workspace
- `skills`: knowledge skills that govern code written in this project
- `vars`: template variables to substitute

If the requested archetype does not exist, list the available ones and STOP.

### 3. Determine variables

- `name` defaults to the current directory name (kebab-case it); ask the user only
  if the manifest declares a variable you cannot infer a sensible value for.
- Substitute `{{var}}` placeholders in file contents AND file/directory names.

### 4. Instantiate

- For a `member` archetype run standalone: copy `<templates>/<archetype>/tree/` into
  the current directory root, substituting variables. Never overwrite an existing
  file — if a target exists, report it and skip it.
- For `workspace`: instantiate the workspace-root tree first, then each
  `member=archetype` into that member's `defaultDir`, and register every member in
  the workspace config file named by the manifest's `register` field.

### 5. Create the knowledge base

Create `docs/plan/`, `docs/concepts/`, `docs/entities/`, `docs/summaries/`
(with a `.gitkeep` in each empty directory).

### 6. Bind knowledge

Create or extend `CLAUDE.md` at the project root with a short section:

```markdown
## Engineering conventions

This project follows the agentic-engineering conventions.
When implementing code here, consult these skills first:
- <one line per skill listed in the archetype manifest's `skills` field>

Plans live in docs/plan/, durable decisions in docs/concepts/ and docs/entities/.
```

### 7. Report

Summarize: what was created, which skills now govern the project, and suggest
`/dev:brainstorm` as the next step.
