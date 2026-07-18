---
type: plan
status: draft            # draft -> approved -> in-progress -> done
created: {{date}}
feature: {{feature}}
gates:
  qa: full               # the ecosystem pack's full QA chain (lint, types, tests, coverage, CRAP)
  review: adversarial    # critic subagent must find no blocking issues
pause_after: []          # slice ids requiring human review before the next slice starts
links: []
---

# {{title}}

## Context

Why this exists, for whom, and which existing [[concepts]] / [[entities]] it
builds on. Two paragraphs maximum.

## Design (signature altitude)

Agreed signatures, data flow, state machines, and invariants — transferred
from the brainstorm. No implementation bodies.

## Out of scope

What was deliberately excluded, so implementation doesn't drift into it.

## Slices

### S1 — {{slice-name}}

- **Goal**:
- **Touches**: (signatures / files)
- **Acceptance**: (checkable criteria)
- **Depends on**: —

## Ledger

Appended by /dev:implement after each slice — never rewritten. Newest row last.

| date | slice | status | divergence from plan | tech debt created | human review? |
|------|-------|--------|----------------------|-------------------|---------------|

## Decisions & divergences

Substantive choices made during implementation, with the why. Each entry dated.

## Summary

Written when the plan reaches `done`; then distilled into
`docs/summaries/{{feature}}.md` (what EXISTS now, not what was intended).
