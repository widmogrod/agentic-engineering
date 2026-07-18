---
name: plan
description: Crystallize an agreed design into docs/plan/YYYY-MM-DD-<feature>-plan.md — the contract and ledger that /dev:implement executes. Use after a design brainstorm converges, or when the user asks to write down a plan for a feature.
argument-hint: "[feature-name]"
---

# /dev:plan — crystallize the design into an executable plan

Feature name (may be empty): `$ARGUMENTS`

Precondition: an agreed design — normally the design summary from
`/dev:brainstorm` earlier in this conversation. If there is no agreed design,
say so and run an abbreviated brainstorm first (ground → propose → converge);
do not invent a plan from nothing.

Consult the `knowledge` skill for the docs/ format rules.

## Procedure

### 1. Create the plan file

- Derive `<feature>` from the argument or the brainstorm topic (kebab-case).
- Get today's date with `date +%F`.
- Copy `${CLAUDE_SKILL_DIR}/assets/plan-template.md` to
  `docs/plan/<date>-<feature>-plan.md` and fill every placeholder. If the file
  exists already, stop and ask.

### 2. Transfer the design — don't re-design

The Design section holds the agreed signatures, data flow, and invariants from
the brainstorm, at signature altitude. Changes of substance at this stage go
back to the user first.

### 3. Decompose into vertical slices

Rules for a good slice:

- **Vertical**: each slice cuts through all layers and ends in something
  observable (a passing test against real behavior, a working endpoint) — never
  "build the models" then "build the service".
- **Ordered by risk**: the slice that could invalidate the design goes first.
- 2-6 slices; if more, the feature wants splitting into two plans.
- Each slice gets: goal (one sentence), signatures/files touched, acceptance
  criteria (checkable, not aspirational), dependencies on earlier slices.

### 4. Configure the gates

The `gates` frontmatter names what every slice must pass (the pack's QA chain,
adversarial review). `pause_after` lists slice IDs where implementation must
STOP for human review — default to pausing after the riskiest slice; ask the
user if unsure.

### 5. Stub the knowledge

For each new concept or entity the design introduces, create a stub in
`docs/concepts/` / `docs/entities/` (frontmatter + a paragraph + `[[links]]`
to this plan). Add the reverse links to the plan's frontmatter.

### 6. Hand off

Show the user the plan path and slice list. The plan stays `status: draft`
until the user approves it — then set `status: approved` and point them at
`/dev:implement <path>`. Never start implementing under this skill.
