---
name: implement
description: Execute an approved plan slice by slice through gated subagents — implement, adversarially review, run mechanical QA, record the ledger, commit, pause for humans where the plan says so. Use when the user asks to implement a plan file created by /dev:plan.
argument-hint: "[path/to/plan.md]"
---

# /dev:implement — gated execution of an approved plan

Plan file: `$ARGUMENTS`

You are the ORCHESTRATOR. Subagents write code; you own the plan file, the
ledger, the gates, and the commits. Consult the `knowledge` skill for docs/
format rules.

## Preconditions

1. Read the plan file completely. If `status: draft` → show the slice list and
   ask the user to approve first; STOP. If `status: in-progress` → this is a
   resume: slices already `done` in the ledger are finished; continue from the
   first slice that isn't.
2. `git status` must be clean (or contain only the plan file). Uncommitted
   unrelated work → ask the user before proceeding.
3. Set `status: in-progress` (if not already) and commit the plan file alone:
   `plan(<feature>): start implementation`.

## The loop — for each remaining slice, in plan order

Run stages sequentially with the Agent tool (`run_in_background: false`).
This plugin provides the agents: `slice-implementer`, `critic-reviewer`,
`qa-gate` (they may appear namespaced, e.g. `dev:slice-implementer`).

### 1. Implement

Spawn **slice-implementer** with: the plan path, the slice id, and nothing
else — the agent reads plan + conventions itself. Keep its report.

### 2. Adversarial review

Spawn **critic-reviewer** with: plan path, slice id, and the implementer's
report. On `verdict: revise`: send the blocking findings back to the SAME
implementer (SendMessage) to fix, then re-review. Maximum 2 revision rounds;
still `revise` after that → go to **Stopping** below.

### 3. Mechanical gate

Spawn **qa-gate** (no context needed beyond "run the chain"). On FAIL: send
the verbatim failures to the implementer to fix, then re-run the gate.
Maximum 2 retry rounds; still FAIL → **Stopping**. Never proceed on a FAIL
verdict, never relax a gate to convert FAIL to PASS.

### 4. Record — append to the plan, never rewrite

Add one ledger row:
`| <date> | S<n> | done | <divergence summary or "none"> | <tech debt or "none"> | <yes/no> |`
(`human review?` = yes when the critic left substantial suggestions, the
slice diverged from design, or the implementer flagged discoveries.)

Longer entries go under **Decisions & divergences** (dated). New concepts or
entities discovered → stub files in `docs/concepts|entities/` per the
`knowledge` skill. Prior ledger rows and past decisions are immutable.

### 5. Commit

One commit per slice: implementation + tests + plan-file update together.
Message: `feat(<feature>): S<n> <slice name>` with a body noting divergences
and tech debt from the ledger row.

### 6. Pause points

If the slice id is in `pause_after` → STOP after committing. Tell the user
what was built, what the next slice is, and what to review; continue only
when they say so.

## Stopping (gate exhausted or blocked)

Do NOT loop forever and do NOT lower the bar. Record a ledger row with status
`blocked` and the reason, commit what is safely committable (never commit red
tests silently — say so if you must leave the tree red), report to the user:
what passed, the verbatim blocking findings/failures, your recommendation.
Let the human decide.

## Completion — all slices done

1. Fill the plan's **Summary** section (what exists now, from the ledger);
   set `status: done`.
2. Distill `docs/summaries/<feature>.md` per the `knowledge` skill; update
   concept/entity stubs that implementation refined.
3. Final commit: `plan(<feature>): complete — summary + knowledge`.
4. Report: slices done, total divergences, open tech debt (this is the
   backlog), rows flagged `human review? yes`.

## Rules

- The plan file is yours ALONE — subagents never edit it (their definitions
  say so too; treat a violation as a blocking review finding).
- Ledger is append-only. Divergences are recorded, not papered over.
- One slice fully through the gates before the next starts. No parallel
  slices — later slices read the ledger of earlier ones.
- If the user interrupts mid-slice, finish recording (ledger row `blocked`
  or `done`) before yielding — a resume must find the plan truthful.
