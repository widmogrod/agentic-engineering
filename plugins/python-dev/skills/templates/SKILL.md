---
name: templates
description: Template registry for the python-dev knowledge pack. Reports the absolute path of the pack's project templates and the available archetypes. Invoked by /dev:init to locate and instantiate Python project scaffolds.
user-invocable: false
---

# python-dev template registry

Templates root (absolute path): `${CLAUDE_PLUGIN_ROOT}/templates`

## Available archetypes

| Archetype | Kind | Description |
|---|---|---|
| `fastapi` | member | FastAPI service following the opinionated service layout (flat package, `main.py` composition root, per-endpoint `api/<ep>/` packages) |

Each archetype directory contains:
- `archetype.json` — the manifest (kind, standalone, defaultDir, skills, vars)
- `tree/` — the file tree to instantiate, with `{{var}}` placeholders

Read the manifest of the requested archetype and follow the /dev:init procedure.
