---
name: knowledge
description: Defines the project knowledge-base format under docs/ — plan, concepts, entities, summaries. Consult before reading or writing any file under docs/plan/, docs/concepts/, docs/entities/, or docs/summaries/ in a project that uses the agentic-engineering conventions.
user-invocable: false
---

# The docs/ knowledge format

Four directories with different natures. Plans decay; concepts and entities
compound — they are the durable context every future session inherits.

| Directory | Nature | Content |
|---|---|---|
| `docs/plan/` | temporal, append-only | intent + ledger of what actually happened |
| `docs/concepts/` | timeless, updated in place | "how we do X here" — conventions, patterns, deviations from pack defaults |
| `docs/entities/` | timeless, updated in place | domain nouns: invariants, states, key operation signatures |
| `docs/summaries/` | generated | post-implementation distillation of what exists now |

## File conventions

- **Names**: plans are `YYYY-MM-DD-<feature>-plan.md` (date = creation day);
  concepts/entities/summaries are `<kebab-case-name>.md`.
- **Frontmatter** (all files):

  ```yaml
  ---
  type: plan | concept | entity | summary
  status: draft | approved | in-progress | done   # plans only
  created: YYYY-MM-DD
  links: ["[[other-file-name]]"]
  ---
  ```

- **Wiki-links**: reference other knowledge files as `[[name]]` (the filename
  without `.md`). A link to a not-yet-existing file is fine — it marks
  something worth writing, not an error.

## Rules

1. Plans are never rewritten after approval — implementation APPENDS to the
   ledger section; divergences are recorded, not papered over.
2. Concepts and entities are updated in place; when a decision supersedes an
   old one, say so in the file ("previously X, changed because Y").
3. When work discovers a new concept or entity, create a stub immediately —
   frontmatter + one paragraph + links — rather than deferring.
4. Summaries are written at the end of implementation, distilled from the
   plan's ledger; they describe what EXISTS, not what was intended.
