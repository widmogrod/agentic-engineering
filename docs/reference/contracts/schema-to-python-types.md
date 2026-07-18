---
type: reference
status: draft
source:
  - legal-ai/frontend/package.json
  - legal-ai/frontend/packages/knowledge-graph/package.json
  - legal-ai/frontend/packages/knowledge-graph/scripts/emit-json-schema.ts
  - legal-ai/frontend/packages/knowledge-graph/src/schemas.ts
  - legal-ai/frontend/packages/knowledge-graph/generated/schemas.schema.json
  - legal-ai/experiments/kg-for-702-rule/src/kg_for_702_rule/schemas/{__init__,_generated,_augment}.py
  - legal-ai/experiments/kg-for-702-rule/scripts/check-types-in-sync.sh
  - legal-ai/experiments/kg-for-702-rule/docs/2026-04-23-iteration-4-learnings.md
---

# TypeScript schema → Python types generation

How the `@legal-ai/knowledge-graph` TypeScript package projects its data model
into Pydantic v2 models used by the Python experiment `kg-for-702-rule`.
Contract direction: **TypeScript (Zod) owns the contract**; Python is
generated.

Pipeline:

```
schemas.ts (Zod v4)                          ← single source of truth
  ↓ z.toJSONSchema(registry)  [emit-json-schema.ts]
generated/schemas.schema.json (Draft 2020-12, $defs, deterministic)  ← committed
  ↓ datamodel-code-generator (Pydantic v2 target)
_generated.py                                ← committed, never hand-edited
  ↓ subclass in _augment.py (restores cross-field .refine() predicates)
schemas/__init__.py                          ← stable public surface
```

## Step 1 — Source of truth: Zod (observed)

`frontend/packages/knowledge-graph/src/schemas.ts` defines the model as Zod v4
schemas (`zod ^4.2.1`), e.g. `SourceAnchorSchema`, `GraphNodeSchema`,
`GraphSchema`, `ExtractResultSchema`. Cross-field invariants use `.refine()`:

```ts
export const SourceAnchorSchema = z.object({ /* ...offsets... */ })
  .refine((a) => a.endOffset >= a.startOffset, {
    message: "endOffset must be >= startOffset",
  });
```

## Step 2 — Emit JSON Schema (observed)

Script: `scripts/emit-json-schema.ts`, run via
`pnpm --filter @legal-ai/knowledge-graph generate:json-schema`
(= `tsx scripts/emit-json-schema.ts`).

- A **curated table** (`SCHEMAS`) lists ~20 named schemas with stable string
  ids. Only these are exported — the emit surface is explicit, not "everything".
- Registers each in a `z.registry<{ id: string }>()`, then calls
  `z.toJSONSchema(registry, { target: "draft-2020-12", ... })` so each id
  becomes a `$defs/<Id>` entry with `#/$defs/<Id>` refs.
- Notable options chosen to keep the downstream Pydantic ergonomic:
  - `reused: "inline"` — prevents Zod hoisting shared primitive fields into
    `$defs/schemaN`, which `datamodel-code-generator` would otherwise wrap in
    `RootModel[str]` (giving `node.id.root` instead of `node.id`).
  - `unrepresentable: "any"` plus an `override` hook that rewrites `z.date()` to
    `{ type: "string", format: "date-time" }` so Pydantic emits a real
    `datetime`.
  - a `uri` hook that keeps refs resolvable inside the bundled doc and re-homes
    Zod's synthetic `__shared` bucket into the root `$defs`.
- **Deterministic output**: recursive `sortKeysDeep` + trailing `\n`, so the
  drift check can diff reproducibly.

Output: `frontend/packages/knowledge-graph/generated/schemas.schema.json`
(committed; header says "Auto-generated — do not edit by hand"). Root is an
anonymous `oneOf` over the registered ids.

## Step 3 — datamodel-code-generator → Pydantic (observed)

Chained in `frontend/package.json` (workspace root) as `generate:python-types`.
The full command:

```
pnpm --filter @legal-ai/knowledge-graph generate:json-schema \
 && uv run --project ../experiments/kg-for-702-rule datamodel-codegen \
      --input packages/knowledge-graph/generated/schemas.schema.json \
      --input-file-type jsonschema \
      --output ../experiments/kg-for-702-rule/src/kg_for_702_rule/schemas/_generated.py \
      --output-model-type pydantic_v2.BaseModel \
      --target-python-version 3.12 \
      --use-standard-collections --use-union-operator \
      --use-schema-description --snake-case-field \
      --field-constraints --allow-population-by-field-name \
      --disable-timestamp
```

Notes:
- `datamodel-code-generator` (`>=0.26.0`) is a Python dep of the experiment
  (`experiments/kg-for-702-rule/pyproject.toml`), invoked via `uv run --project`.
- `--snake-case-field --allow-population-by-field-name`: JSON uses camelCase
  (`startOffset`); Python fields become snake_case (`start_offset`) while still
  accepting the camelCase alias.
- `--disable-timestamp` keeps output byte-stable (no generation timestamp) so
  the drift check works.
- Output lands at
  `experiments/kg-for-702-rule/src/kg_for_702_rule/schemas/_generated.py`
  (committed).

## Step 4 — Augment (observed)

`_generated.py` is never hand-edited (regen wipes it). Semantics JSON Schema
can't express are restored in `_augment.py`:

- Cross-field `.refine()` predicates → subclasses with
  `@model_validator(mode="after")`. `SourceAnchor` and `SourceSpan` subclass
  the generated versions and re-check `end_offset >= start_offset`.
- `ExtractStats` — the `Omit<ExtractResult, "delta">` shape (not expressible in
  JSON Schema) is hand-defined here.

`schemas/__init__.py` is the canonical public surface: it re-exports the
augmented `SourceAnchor` / `SourceSpan` / `ExtractStats` and the straight
codegen for everything else, so downstream code gets validation automatically
regardless of provenance.

## Known codegen gaps (observed, from iteration-4 learnings doc)

- `z.tuple([string, string])` → `list[Any]` (imperfect `prefixItems`).
  Non-blocking.
- Anonymous enums get positional names (`Status`, `Status1`) — cosmetic.
- Both handled by "fix in Zod source if it matters", never by editing generated
  files.

## Drift prevention (observed)

`experiments/kg-for-702-rule/scripts/check-types-in-sync.sh` — a
**snapshot-hash regenerate-and-diff** gate:

1. `shasum -a 256` the two tracked outputs
   (`generated/schemas.schema.json`, `_generated.py`).
2. Run `pnpm generate:python-types` from `frontend/`.
3. Re-hash; if any output changed, fail with an actionable message
   ("Run 'pnpm generate:python-types' from frontend/ and commit the diff").

The script hashes *content on disk* rather than using `git status`, so it
catches drift whether files are tracked, staged, or untouched — testing
generation determinism against what's committed.

**Caveat (observed):** the iteration-4 doc describes this as "CI drift-check",
but `.github/workflows/ci.yml` contains **no** reference to
`check-types-in-sync` or `generate:python-types`. The script exists and is the
intended gate, but as of this snapshot it is not wired into the CI workflow —
run it manually / via pre-commit. *(Inferred from absence of CI wiring.)*
