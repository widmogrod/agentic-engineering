# Claude Code Plugin & Marketplace Specification

**Official Documentation URLs:**
- Claude Code Docs Map: https://code.claude.com/docs/en/claude_code_docs_map.md
- Plugins Guide: https://code.claude.com/docs/en/plugins.md
- Plugins Reference: https://code.claude.com/docs/en/plugins-reference.md
- Marketplace Guide: https://code.claude.com/docs/en/plugin-marketplaces.md
- Skills Guide: https://code.claude.com/docs/en/skills.md
- Agent Skills Spec: https://agentskills.io/specification

---

## 1. MARKETPLACE.JSON SCHEMA

**Location:** `.claude-plugin/marketplace.json` at marketplace root

### Complete Schema

```json
{
  "name": "my-plugins",
  "owner": {
    "name": "Owner Name",
    "email": "owner@example.com"
  },
  "description": "Brief marketplace description",
  "version": "1.0.0",
  "metadata": {
    "pluginRoot": "./plugins"
  },
  "allowCrossMarketplaceDependenciesOn": ["other-marketplace"],
  "renames": {
    "old-plugin-name": "new-plugin-name",
    "removed-plugin": null
  },
  "plugins": [
    {
      "name": "plugin-name",
      "displayName": "Plugin Display Name",
      "source": "./plugins/plugin-name",
      "description": "What this plugin does",
      "version": "1.0.0",
      "author": {
        "name": "Author Name",
        "email": "author@example.com"
      },
      "homepage": "https://docs.example.com",
      "repository": "https://github.com/user/plugin",
      "license": "MIT",
      "keywords": ["tag1", "tag2"],
      "category": "productivity",
      "tags": ["tag1"],
      "strict": true,
      "defaultEnabled": false,
      "relevance": {
        "pathPatterns": ["src/**/*.ts"],
        "fileExtensions": [".ts", ".tsx"]
      }
    }
  ]
}
```

### Required Fields

| Field   | Type   | Description                                                                                     |
|---------|--------|----------------------------------------------------------------------------------------------|
| `name`  | string | Marketplace identifier (kebab-case). Reserved names cannot be used: `claude-code-plugins`, `claude-plugins-official`, `claude-plugins-community`, `claude-community`, `anthropic-marketplace`, `anthropic-plugins`, `agent-skills`, etc. |
| `owner` | object | Marketplace maintainer: `{ "name": string, "email"?: string }`                                 |
| `plugins` | array | List of plugin entries                                                                        |

### Optional Fields

| Field                                  | Type                 | Description                                                          |
|----------------------------------------|----------------------|----------------------------------------------------------------------|
| `$schema`                              | string               | JSON Schema URL for autocomplete (ignored by Claude Code)             |
| `description`                          | string               | Brief marketplace description                                        |
| `version`                              | string               | Marketplace manifest version                                         |
| `metadata.pluginRoot`                  | string               | Base directory prepended to relative plugin source paths              |
| `allowCrossMarketplaceDependenciesOn`  | array[string]        | Marketplaces this one may depend on                                  |
| `renames`                              | object               | Map old names to new names (or `null` if removed)                    |

### Plugin Entry Fields

**Required:**

| Field    | Type           | Description                                                  |
|----------|----------------|--------------------------------------------------------------|
| `name`   | string         | Kebab-case plugin identifier                                 |
| `source` | string\|object | Plugin source location                                       |

**Optional Metadata:**

| Field            | Type    | Description                                             |
|------------------|---------|-------------------------------------------------------|
| `displayName`    | string  | Human-readable name (may contain spaces, any casing)  |
| `description`    | string  | Brief description                                     |
| `version`        | string  | Plugin version (pins for updates)                     |
| `author`         | object  | `{ "name": string, "email"?: string }`               |
| `homepage`       | string  | Documentation URL                                     |
| `repository`     | string  | Source code URL                                       |
| `license`        | string  | SPDX license identifier                               |
| `keywords`       | array   | Discovery tags                                        |
| `category`       | string  | Plugin category                                       |
| `tags`           | array   | Additional tags for searchability                     |
| `strict`         | boolean | If `true`, `plugin.json` is authority (default: true) |
| `defaultEnabled` | boolean | Plugin enabled after install (default: true)          |
| `relevance`      | object  | Path/extension patterns for suggestion                |

**Component Configuration:**

| Field       | Type            | Description                              |
|-------------|-----------------|--------------------------------------|
| `skills`    | string\|array   | Custom skill directory paths              |
| `commands`  | string\|array   | Custom flat `.md` skill files             |
| `agents`    | string\|array   | Custom agent definition files             |
| `hooks`     | string\|object  | Hook config paths or inline config        |
| `mcpServers`| string\|object  | MCP server configs or paths                |
| `lspServers`| string\|object  | LSP server configs or paths                |

---

## 2. PLUGIN SOURCE TYPES

### Relative Path

```json
{
  "name": "my-plugin",
  "source": "./plugins/my-plugin"
}
```

- Resolved relative to marketplace root (directory containing `.claude-plugin/`)
- Must start with `./`
- Resolved locally or in git-based marketplaces
- **Does not work** in URL-based marketplaces

### GitHub Repository

```json
{
  "name": "github-plugin",
  "source": {
    "source": "github",
    "repo": "owner/repo",
    "ref": "v2.0.0",
    "sha": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"
  }
}
```

- `repo` (required): GitHub `owner/repo` format
- `ref` (optional): Branch or tag name
- `sha` (optional): Full 40-character commit SHA (takes precedence over `ref`)

### Git Repository (Any Host)

```json
{
  "name": "git-plugin",
  "source": {
    "source": "url",
    "url": "https://gitlab.com/team/plugin.git",
    "ref": "main",
    "sha": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"
  }
}
```

- `url` (required): Full git URL (HTTPS or SSH, with `.git` suffix recommended)
- `ref` (optional): Branch or tag
- `sha` (optional): Full commit SHA

### Git Subdirectory

```json
{
  "name": "monorepo-plugin",
  "source": {
    "source": "git-subdir",
    "url": "https://github.com/acme-corp/monorepo.git",
    "path": "tools/claude-plugin",
    "ref": "v2.0.0",
    "sha": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"
  }
}
```

- `url` (required): Git URL, GitHub shorthand, or SSH URL
- `path` (required): Subdirectory path within repo
- `ref` (optional): Branch or tag
- `sha` (optional): Commit SHA

### NPM Package

```json
{
  "name": "npm-plugin",
  "source": {
    "source": "npm",
    "package": "@org/plugin",
    "version": "2.1.0",
    "registry": "https://npm.example.com"
  }
}
```

- `package` (required): Package name or scoped package
- `version` (optional): Version or version range (e.g., `^2.0.0`)
- `registry` (optional): Custom npm registry URL

---

## 3. PLUGIN.JSON MANIFEST SCHEMA

**Location:** `.claude-plugin/plugin.json` in plugin root

### Complete Schema

```json
{
  "name": "plugin-name",
  "displayName": "Plugin Name",
  "version": "1.2.0",
  "description": "Brief plugin description",
  "author": {
    "name": "Author Name",
    "email": "author@example.com",
    "url": "https://github.com/author"
  },
  "homepage": "https://docs.example.com/plugin",
  "repository": "https://github.com/author/plugin",
  "license": "MIT",
  "keywords": ["keyword1", "keyword2"],
  "defaultEnabled": true,
  "skills": "./custom/skills/",
  "commands": ["./custom/commands/special.md"],
  "agents": ["./custom/agents/reviewer.md"],
  "hooks": "./config/hooks.json",
  "mcpServers": "./mcp-config.json",
  "lspServers": "./.lsp.json",
  "outputStyles": "./styles/",
  "settings": "./settings.json",
  "userConfig": {
    "api_endpoint": {
      "type": "string",
      "title": "API Endpoint",
      "description": "Your API endpoint",
      "required": true
    }
  },
  "channels": [
    {
      "server": "telegram",
      "userConfig": {}
    }
  ],
  "dependencies": [
    "helper-plugin",
    { "name": "vault-plugin", "version": "~2.1.0" }
  ],
  "experimental": {
    "themes": "./themes/",
    "monitors": "./monitors.json"
  }
}
```

### Required Fields

| Field  | Type   | Description                                                      |
|--------|--------|--------------------------------------------------------------|
| `name` | string | Kebab-case identifier. Used for namespacing components.         |

### Metadata Fields

| Field           | Type    | Description                                                    |
|-----------------|---------|---------------------------------------------------------------|
| `$schema`       | string  | JSON Schema URL (ignored by Claude Code)                       |
| `displayName`   | string  | Human-readable name (overrides `name` in UI)                   |
| `version`       | string  | Semantic version. If omitted, uses git commit SHA              |
| `description`   | string  | Brief explanation of plugin purpose                           |
| `author`        | object  | `{ "name": string, "email"?: string, "url"?: string }`        |
| `homepage`      | string  | Documentation URL                                              |
| `repository`    | string  | Source code repository URL                                     |
| `license`       | string  | SPDX license identifier (e.g., `MIT`, `Apache-2.0`)           |
| `keywords`      | array   | Discovery tags (string array)                                  |
| `defaultEnabled`| boolean | Whether enabled by default after install (default: `true`)    |

### Component Path Fields

| Field                     | Type            | Description                                                    |
|---------------------------|-----------------|---------------------------------------------------------------|
| `skills`                  | string\|array   | Adds to default `skills/` scan. Paths must start with `./`    |
| `commands`                | string\|array   | Replaces default `commands/`. Can be files or directories      |
| `agents`                  | string\|array   | Replaces default `agents/`                                     |
| `hooks`                   | string\|array\|object | Hook config paths or inline config (merged with `hooks/hooks.json`) |
| `mcpServers`              | string\|array\|object | MCP server config paths or inline config                       |
| `lspServers`              | string\|array\|object | LSP server configs (merged with `.lsp.json`)                   |
| `outputStyles`            | string\|array   | Replaces default `output-styles/`                              |
| `settings`                | string          | Path to default settings JSON (only `agent` and `subagentStatusLine` keys supported) |
| `experimental.themes`     | string\|array   | Color theme files (replaces default `themes/`)                |
| `experimental.monitors`   | string\|array   | Background monitor configs (replaces `monitors/monitors.json`) |

### User Configuration

```json
{
  "userConfig": {
    "config_key": {
      "type": "string|number|boolean|directory|file",
      "title": "Display Label",
      "description": "Help text",
      "required": true,
      "default": "value",
      "sensitive": false
    }
  }
}
```

- Values available as `${user_config.KEY}` in MCP/LSP/hook/monitor configs
- Non-sensitive values also available in skill/agent content
- Exported as `CLAUDE_PLUGIN_OPTION_<KEY>` environment variables

### Channels

```json
{
  "channels": [
    {
      "server": "telegram",
      "userConfig": {
        "bot_token": {
          "type": "string",
          "title": "Bot Token",
          "sensitive": true
        }
      }
    }
  ]
}
```

### Dependencies

```json
{
  "dependencies": [
    "helper-plugin",
    { "name": "secrets-vault", "version": "~2.1.0" }
  ]
}
```

---

## 4. PLUGIN DIRECTORY STRUCTURE

### Standard Layout

```
plugin-name/
├── .claude-plugin/
│   └── plugin.json          # Metadata (optional if no manifest needed)
├── skills/
│   ├── skill-one/
│   │   ├── SKILL.md
│   │   ├── reference.md
│   │   └── scripts/
│   └── skill-two/
│       └── SKILL.md
├── commands/                # Flat .md skill files (legacy)
│   ├── status.md
│   └── logs.md
├── agents/
│   ├── code-reviewer.md
│   └── security-checker.md
├── output-styles/
│   └── terse.md
├── themes/
│   └── dracula.json
├── hooks/
│   └── hooks.json
├── monitors/
│   └── monitors.json
├── bin/                     # Executables added to PATH
│   └── my-tool
├── .mcp.json                # MCP servers
├── .lsp.json                # LSP servers
├── settings.json            # Default plugin settings
├── LICENSE
└── README.md
```

### Important Notes

- **All component directories** (`skills/`, `commands/`, `agents/`, `hooks/`, etc.) must be at **plugin root**
- **Only `plugin.json`** goes inside `.claude-plugin/`
- A plugin with a single skill can use `SKILL.md` directly at plugin root
- CLAUDE.md at plugin root is NOT loaded automatically

### File Locations Reference

| Component      | Default Location        | Description                                                 |
|----------------|-------------------------|-------------------------------------------------------------|
| **Manifest**   | `.claude-plugin/plugin.json` | Plugin metadata (optional)                                 |
| **Skills**     | `skills/`               | Directories with `<name>/SKILL.md` structure                 |
| **Commands**   | `commands/`             | Flat Markdown `.md` files (legacy, use `skills/`)            |
| **Agents**     | `agents/`               | Subagent definitions in Markdown                             |
| **Output Styles** | `output-styles/`       | Output style definitions                                     |
| **Themes**     | `themes/`               | Color theme JSON definitions                                 |
| **Hooks**      | `hooks/hooks.json`      | Event handlers (can also be inline in `plugin.json`)         |
| **MCP Servers**| `.mcp.json`             | MCP server definitions                                       |
| **LSP Servers**| `.lsp.json`             | Language server configurations                               |
| **Monitors**   | `monitors/monitors.json`| Background monitor configs                                   |
| **Executables**| `bin/`                  | Scripts/binaries added to Bash tool `$PATH`                  |
| **Settings**   | `settings.json`         | Default configuration applied when enabled                   |

---

## 5. SKILL.MD FRONTMATTER SPEC

### YAML Frontmatter Format

```yaml
---
name: skill-name
description: What this skill does and when to use it
when_to_use: Additional context for activation (optional)
argument-hint: "[issue-number]"
arguments: "issue branch"
disable-model-invocation: false
user-invocable: true
allowed-tools: "Read Write Bash(git *)"
disallowed-tools: "AskUserQuestion"
model: inherit
effort: medium
context: fork
agent: Explore
paths: "src/**/*.ts, tests/**/*.ts"
shell: bash
---
```

### Field Reference

| Field                      | Type    | Required | Description                                                                          |
|----------------------------|---------|----------|--------------------------------------------------------------------------------------|
| `name`                     | string  | No       | Display name (defaults to directory name). For plugin-root `SKILL.md`, sets invocation name. |
| `description`              | string  | Yes      | What the skill does and when to use it. Claude uses this for automatic invocation.   |
| `when_to_use`              | string  | No       | Additional context for when Claude should invoke. Appended to description.           |
| `argument-hint`            | string  | No       | Hint for autocomplete (e.g., `[issue-number]`, `[filename] [format]`)               |
| `arguments`                | string\|array | No  | Positional argument names for `$name` substitution                                   |
| `disable-model-invocation` | boolean | No       | If `true`, only user can invoke (default: `false`)                                  |
| `user-invocable`           | boolean | No       | If `false`, only Claude can invoke (hidden from menu) (default: `true`)              |
| `allowed-tools`            | string  | No       | Space/comma-separated tools pre-approved for this skill                              |
| `disallowed-tools`         | string  | No       | Space/comma-separated tools removed from available pool while skill active           |
| `model`                    | string  | No       | Model to use when skill active (e.g., `opus`, `sonnet`, `inherit`)                 |
| `effort`                   | string  | No       | Effort level: `low`, `medium`, `high`, `xhigh`, `max`                              |
| `context`                  | string  | No       | Set to `fork` to run in isolated subagent context                                   |
| `agent`                    | string  | No       | Subagent type when `context: fork` (e.g., `Explore`, `Plan`, `general-purpose`)   |
| `paths`                    | string\|array | No  | Glob patterns. Skill activates automatically only when working with matching files  |
| `shell`                    | string  | No       | Shell for command execution: `bash` (default) or `powershell`                       |
| `hooks`                    | object  | No       | Hooks scoped to this skill's lifecycle                                               |

### Agent Skills Standard (agentskills.io)

The `SKILL.md` format follows the **Agent Skills** open standard. Additional fields:

| Field          | Type   | Description                                                  |
|----------------|--------|--------------------------------------------------------------|
| `license`      | string | License name or bundled file reference                       |
| `compatibility`| string | Environment requirements (1-500 chars)                       |
| `metadata`     | object | Arbitrary key-value mapping for additional metadata           |
| `allowed-tools`| string | Pre-approved tools (experimental)                             |

---

## 6. STRING SUBSTITUTIONS IN SKILLS

Available variables for use in skill content and `allowed-tools`:

| Variable                | Description                                                              |
|-------------------------|--------------------------------------------------------------------------|
| `$ARGUMENTS`            | All user-provided arguments as a single string                           |
| `$ARGUMENTS[N]`         | Specific argument by 0-based index                                       |
| `$N`                    | Shorthand for `$ARGUMENTS[N]`                                            |
| `$name`                 | Named argument from `arguments` field                                    |
| `${CLAUDE_SESSION_ID}`  | Current session ID                                                        |
| `${CLAUDE_EFFORT}`      | Current effort level                                                      |
| `${CLAUDE_SKILL_DIR}`   | Directory containing the skill's `SKILL.md`                              |
| `${CLAUDE_PROJECT_DIR}` | Project root directory                                                    |

### Examples

```yaml
---
name: fix-issue
arguments: "issue branch"
---

Fix GitHub issue $0 on branch $1:
1. Check out $branch
2. Understand the issue from #$issue
3. Implement and test the fix
```

---

## 7. COMMAND NAMESPACING

### Plugin Skills Namespace

Skills from plugins are invoked with colon notation:

```
/plugin-name:skill-name
```

Example:
```
/my-plugin:code-review
/deployment-tools:deploy-staging
```

### Skill Discovery and Naming

| Skill Location                        | Command Name            | Example                                      |
|---------------------------------------|-------------------------|----------------------------------------------|
| `skills/<name>/SKILL.md`              | Directory name          | `skills/deploy/` → `/deploy`                 |
| `.claude/commands/<name>.md`          | File name (no extension)| `commands/deploy.md` → `/deploy`             |
| Plugin `skills/<name>/SKILL.md`       | Plugin-namespaced       | `plugin/skills/deploy/` → `/plugin:deploy`   |
| Nested `.claude/skills/<subdir>/<name>/` | Qualified path       | `apps/web/.claude/skills/deploy/` → `/apps/web:deploy` |
| Plugin root `SKILL.md` with `name`    | Frontmatter `name` field | Frontmatter `name: review` → `/plugin:review` |

---

## 8. MONOREPO LAYOUT (MULTI-PLUGIN MARKETPLACE)

### Recommended Structure

```
my-marketplace/
├── .claude-plugin/
│   └── marketplace.json
├── plugins/
│   ├── formatter-plugin/
│   │   ├── .claude-plugin/
│   │   │   └── plugin.json
│   │   └── skills/
│   │       └── format-code/
│   │           └── SKILL.md
│   ├── deployment-tools/
│   │   ├── .claude-plugin/
│   │   │   └── plugin.json
│   │   ├── skills/
│   │   │   └── deploy/
│   │   │       └── SKILL.md
│   │   └── agents/
│   │       └── deploy-reviewer.md
│   └── security-scanner/
│       ├── .claude-plugin/
│       │   └── plugin.json
│       └── skills/
│           └── scan-dependencies/
│               └── SKILL.md
├── shared/              # Optional: shared scripts/libs
│   ├── validators.py
│   └── helpers.sh
├── README.md
└── CONTRIBUTING.md
```

### Marketplace Entry Pattern

**marketplace.json:**

```json
{
  "name": "my-tools",
  "owner": { "name": "Your Org" },
  "metadata": {
    "pluginRoot": "./plugins"
  },
  "plugins": [
    {
      "name": "formatter",
      "source": "./plugins/formatter-plugin",
      "description": "Code formatting automation"
    },
    {
      "name": "deployment-tools",
      "source": "./plugins/deployment-tools",
      "description": "Deployment automation and approval workflows"
    },
    {
      "name": "security-scanner",
      "source": "./plugins/security-scanner",
      "description": "Dependency and security scanning"
    }
  ]
}
```

### Sharing Files Across Plugins

Use **symlinks** for shared code:

```bash
# In deployment-tools plugin:
ln -s ../../shared/validators.py ./validators.py

# In security-scanner plugin:
ln -s ../../shared/helpers.sh ./bin/helpers.sh
```

When installed, symlinks are dereferenced and content is copied:
- Symlinks within plugin own directory: preserved
- Symlinks to sibling plugins: dereferenced (content copied)
- Symlinks outside marketplace: skipped (security)

---

## 9. AGENT SKILLS SPECIFICATION (agentskills.io)

Claude Code skills follow the **Agent Skills** open standard, enabling reuse across multiple agents.

### SKILL.md Format (Agent Skills Spec)

```yaml
---
name: skill-name
description: What this skill does and when to use it
license: Apache-2.0
compatibility: "Requires Python 3.11+ and uv"
metadata:
  author: example-org
  version: "1.0"
  custom-field: custom-value
allowed-tools: "Bash(git:*) Read"
---

# Skill Instructions

Step-by-step instructions for the agent...
```

### Directory Structure (Agent Skills Standard)

```
skill-name/
├── SKILL.md          # Required: metadata + instructions
├── scripts/          # Optional: executable code
├── references/       # Optional: detailed documentation
├── assets/           # Optional: templates, resources
└── examples/         # Optional: usage examples
```

### Frontmatter Fields (Agent Skills Spec)

| Field           | Required | Constraints                                                     |
|-----------------|----------|---------------------------------------------------------------|
| `name`          | Yes      | 1-64 chars. Lowercase alphanumeric + hyphens. No leading/trailing hyphens. |
| `description`   | Yes      | 1-1024 chars. Include both what it does and when to use it.    |
| `license`       | No       | License name or bundled license file reference                 |
| `compatibility` | No       | 1-500 chars. Environment requirements                          |
| `metadata`      | No       | Arbitrary key-value mapping (string keys, string values)       |
| `allowed-tools` | No       | Space-separated pre-approved tools (experimental)              |

### Progressive Disclosure Pattern

Agents load skills in three stages:

1. **Discovery (~100 tokens):** Name + description loaded at startup
2. **Activation (< 5000 tokens recommended):** Full `SKILL.md` body loaded when skill activates
3. **Resources (on-demand):** Referenced files loaded when needed

Keep main `SKILL.md` under 500 lines; move detailed content to `references/`.

---

## 10. PLUGIN INSTALLATION & RESOLUTION

### Installation Scopes

```json
{
  "enabledPlugins": {
    "plugin-name@marketplace": true
  }
}
```

**Scopes (in precedence order):**

1. **Managed** (`managed-settings.json`) - Read-only, admin-controlled
2. **Project** (`.claude/settings.json`) - Shared with team via git
3. **User** (`~/.claude/settings.json`) - Personal, persists across projects
4. **Local** (`.claude/settings.local.json`) - Project-specific, gitignored

### Plugin Installation Command

```bash
# Interactive install with scope selection
/plugin install plugin-name@marketplace-name

# CLI install to specific scope
claude plugin install formatter@my-marketplace --scope project

# From alternate marketplace
/plugin install plugin-name@claude-plugins-official
```

### Resolution Order for Plugin Discovery

1. Marketplace name from `enabledPlugins`
2. Look in configured marketplaces (in priority order)
3. If not found, check for cached/installed versions
4. Fall back to auto-discovered skills directory plugins (`@skills-dir`)

---

## 11. PLUGIN VS SKILLS COMPARISON

| Aspect              | Skill                          | Plugin                                    |
|-------------------|-------------------------------|------------------------------------------|
| **Invocation**     | `/skill-name`                 | `/plugin-name:skill-name`                 |
| **Distribution**   | Commit to `.claude/skills/`   | Install via marketplace                   |
| **Scoping**        | Personal, project, directory  | User, project, local, managed             |
| **Components**     | Skills only                   | Skills, agents, hooks, MCP, LSP, monitors |
| **Namespacing**    | No namespacing                | Namespaced (prevents conflicts)           |
| **Versioning**     | Git-based                     | Explicit version or git commit SHA        |
| **Sharing**        | Via repository                | Via marketplace                           |

---

## 12. RESERVED MARKETPLACE NAMES

These marketplace names are reserved for official use:

- `claude-code-marketplace`
- `claude-code-plugins`
- `claude-plugins-official`
- `claude-plugins-community`
- `claude-community`
- `anthropic-marketplace`
- `anthropic-plugins`
- `agent-skills`
- `anthropic-agent-skills`
- `knowledge-work-plugins`
- `life-sciences`
- `claude-for-legal`
- `claude-for-financial-services`
- `financial-services-plugins`
- `first-party-plugins`
- `healthcare`

Also reserved: Names impersonating official marketplaces (e.g., `official-claude-plugins`, `anthropic-plugins-v2`)

---

## 13. VERSION MANAGEMENT

### Two Approaches

**Explicit Version** (for published plugins):
```json
{
  "version": "2.1.0"
}
```
- Users get updates only when you bump this field
- Pushing new commits without bumping has no effect
- Good for stable release cycles

**Commit-SHA Version** (for development):
- Omit `version` from both `plugin.json` and marketplace entry
- Uses git commit SHA as version
- Users get updates on every new commit
- Good for team/internal plugins under active development

### Version Resolution Order

1. `version` in plugin's `plugin.json`
2. `version` in plugin's marketplace entry
3. Git commit SHA (for git-based sources)
4. `unknown` (for npm sources or non-git directories)

If set in `plugin.json`, marketplace entry's version is ignored.

---

## 14. PLUGIN CACHING & FILE RESOLUTION

### Plugin Cache Location

```
~/.claude/plugins/
├── known_marketplaces.json          # Registered marketplaces
├── marketplaces/                    # Marketplace clones
│   └── marketplace-name/
└── cache/                           # Plugin installations
    └── marketplace-name/
        └── plugin-name/
            └── v1.0.0/              # Version-specific directory
```

### Environment Variables (Plugin Runtime)

| Variable              | Description                                              |
|----------------------|----------------------------------------------------------|
| `${CLAUDE_PLUGIN_ROOT}` | Absolute path to plugin installation directory           |
| `${CLAUDE_PLUGIN_DATA}` | Persistent directory (`~/.claude/plugins/data/{id}/`)   |
| `${CLAUDE_PROJECT_DIR}` | Project root (same as hook's `CLAUDE_PROJECT_DIR`)      |

### Path Traversal Limitations

- Installed plugins **cannot reference files outside their directory**
- Paths like `../shared-utils` will not work after installation
- Solution: Use symlinks within marketplace or restructure to keep shared content inside plugin

### Persistent Data Directory

For plugin state that should survive updates:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "diff -q \"${CLAUDE_PLUGIN_ROOT}/package.json\" \"${CLAUDE_PLUGIN_DATA}/package.json\" || (cp \"${CLAUDE_PLUGIN_ROOT}/package.json\" \"${CLAUDE_PLUGIN_DATA}/\" && npm install)"
          }
        ]
      }
    ]
  }
}
```

ID format: `{id}` = plugin identifier with non-alphanumeric chars replaced by `-`
Example: `formatter@my-marketplace` → `~/.claude/plugins/data/formatter-my-marketplace/`

---

## 15. PLUGIN VALIDATION

### CLI Command

```bash
# Validate marketplace
claude plugin validate .

# Validate plugin with strict mode
claude plugin validate ./my-plugin --strict

# Validate inline
/plugin validate .
```

### Checked Items

- Marketplace JSON schema
- Plugin manifests (`plugin.json`)
- SKILL.md frontmatter YAML
- Hooks JSON syntax
- Duplicate plugin names
- Source path traversal (no `..` escapes)
- Version mismatches between manifest and marketplace

### Warnings (Non-blocking)

- Unrecognized manifest fields
- Missing marketplace description
- Non-kebab-case plugin names
- Ignored default directories

---

## QUICK REFERENCE COMMANDS

```bash
# Initialize a new marketplace
mkdir -p my-marketplace/.claude-plugin
echo '{...}' > my-marketplace/.claude-plugin/marketplace.json

# Initialize a skills-directory plugin
claude plugin init my-plugin
# Creates: ~/.claude/skills/my-plugin/.claude-plugin/plugin.json

# Add marketplace
/plugin marketplace add owner/repo
/plugin marketplace add https://git.example.com/plugins.git

# Install plugin
/plugin install plugin-name@marketplace-name
claude plugin install plugin-name@marketplace --scope project

# List plugins
/plugin list
claude plugin list --json

# Validate
claude plugin validate .
/plugin validate .

# Reload plugins mid-session
/reload-plugins

# Update plugin
/plugin update plugin-name@marketplace
claude plugin update plugin-name@marketplace

# Disable/enable
/plugin disable plugin-name@marketplace
/plugin enable plugin-name@marketplace

# Uninstall
/plugin uninstall plugin-name@marketplace
claude plugin uninstall plugin-name@marketplace --prune
```

