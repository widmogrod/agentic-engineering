---
name: brainstorm
description: Structured design conversation at signature altitude — method signatures, data flow, state machines, never implementation bodies. Use when the user wants to think through what to build (a feature, service, or system) before committing to a plan.
argument-hint: "[topic]"
---

# /dev:brainstorm — design at signature altitude

Topic (may be empty): `$ARGUMENTS`

Goal: converge with the user on a design they explicitly agree with,
communicating at HIGH level throughout. The output of a good brainstorm is a
design that fits in one screen and survives contact with implementation.

Notation rules live in `${CLAUDE_SKILL_DIR}/references/technical-communication.md`
— read it before proposing anything.

## The altitude discipline (non-negotiable)

- Code blocks may contain ONLY: type/interface definitions, method signatures
  (bodies elided), data-flow notation, state machines. Never implementation
  bodies, imports, or config.
- Behavior is expressed as: signatures + data flow + invariants + error
  channels. If you catch yourself writing an `if` statement, you are too low.
- Every proposal names its trade-offs. One recommendation, clearly marked.

## Procedure

### 1. Ground

Before proposing anything, read what already exists (consult the `knowledge`
skill for the format):

- `docs/concepts/` and `docs/entities/` — prior decisions bind; build on them
  or explicitly propose superseding them.
- Recent `docs/plan/` and `docs/summaries/` — what was recently built and why.
- Relevant code entry points — enough to anchor signatures in reality, not to
  study implementations.

### 2. Frame

State back, in two or three sentences, what problem is being solved and for
whom. If intent or constraints are genuinely unclear, ask at most 2-3 focused
questions — then proceed.

### 3. Propose

Offer 2-3 approach sketches at signature altitude, each with: core signatures,
data flow, affected entities, trade-offs. Recommend one and say why. Keep each
sketch short enough to compare side by side.

### 4. Iterate

Refine with the user. Stay at altitude — when the user drills into detail,
answer, then restate the impact at the signature level. Track open questions
explicitly rather than letting them dissolve.

### 5. Converge

When the user signals agreement, produce the **design summary**:

- Agreed signatures and data flow (final form)
- Entities and concepts affected (existing + new)
- Invariants the implementation must preserve
- Open questions deliberately deferred
- Explicitly out of scope

Then offer `/dev:plan <feature-name>` to crystallize it into an executable
plan. Do not start implementing.
