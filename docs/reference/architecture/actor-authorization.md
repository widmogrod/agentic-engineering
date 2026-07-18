---
type: reference
status: draft
source:
  - legal-ai/frontend/nogai/src/services/core/domain/actors.ts
  - legal-ai/frontend/nogai/src/lib/policy-engine/evaluator.ts
  - legal-ai/frontend/nogai/src/lib/policy-engine/types.ts
  - legal-ai/frontend/nogai/src/config/policy.ts
  - legal-ai/frontend/nogai/src/server/trpc/context.ts
  - legal-ai/frontend/nogai/src/server/trpc/init.ts
  - legal-ai/frontend/nogai/src/services/waitlist/domain/query.ts
  - legal-ai/frontend/nogai/src/services/research-artefact/domain/query.ts
  - legal-ai/frontend/nogai/src/services/waitlist/domain/transition.ts
  - legal-ai/frontend/nogai/src/services/message/infrastructure/policy-adapter.ts
  - legal-ai/frontend/nogai/src/services/waitlist/__test__/infrastructure/projection-contract.ts
---

# Actor-First Authorization

A prescriptive recipe. Every operation carries an explicit **Actor** — the
"who". Reads inject the actor's scope as a **query filter** (authorization by
construction, not per-row checks); writes run the actor through a declarative
**policy engine**. Observed in `nogai`; the essence generalizes to any service.

## 1. Model the Actor (the one identity type)

A closed, discriminated union — never a bag of optional flags. Observed in
`src/services/core/domain/actors.ts` (Zod, discriminated on `role`):

```ts
UserActor   = { role: "user";   userId: string }
AdminActor  = { role: "admin";  userId: string }
SystemActor = { role: "system"; serviceId: string }   // named job/service, not a user
export type Actor = UserActor | AdminActor | SystemActor;
```

- Roles are **flat** (`user`/`admin`/`system`); no role list, no groups.
- **Tenancy = `userId`.** There is no org/tenant field — the "tenant boundary"
  is the individual user. (Observed; a multi-tenant service would add `tenantId`
  and filter on it the same way.)
- Helpers are the only sanctioned way to interrogate an actor: `actorsEqual`,
  `getActorUserId` (undefined for system), `isUserActor`, `formatActor`,
  `createSystemActor(serviceId)`. Each service re-exports these from core
  (`src/services/<svc>/domain/actor.ts`) so the union stays single-source.
- **Deviation (observed):** `MessageActor` extends the union with `agent`/`tool`
  roles handled outside the policy document — see §5.

## 2. Establish the Actor at the edge (once)

The actor is minted at the trust boundary from the verified session and then
flows inward unchanged. Observed in `src/server/trpc/context.ts`:

```ts
const session = await auth0.getSession();
const userId = session?.user?.sub ?? null;
// ...
return { userId, actor: { role: "user", userId }, services, ... } as AuthContext;
```

- `authedProcedure` (`src/server/trpc/init.ts`) is the gate: it throws
  `UNAUTHORIZED` when `ctx.actor` is null, so every procedure downstream sees a
  guaranteed `UserActor`. Middleware (`src/middleware.ts`) only enforces
  session existence / public-route bypass — it does **not** build the actor.
- Admin/system actors are **not** minted at the HTTP edge. `SystemActor` is
  constructed in-process via `createSystemActor("<job-name>")` for background
  jobs, event handlers, and agent tools — giving every autonomous action a
  traceable identity. (Observed: `serviceId` values like `"orchestrator"`,
  `"summarization.ocr-completion"` appear in the policy allowlists.)

## 3. Reads: `.for(actor)` injects the filter (query-level auth)

The load-bearing convention. **Every query starts at `Query.for(actor)`** —
there is no public constructor. `for` seeds the filter set from the actor
before any caller-supplied filter is added. Observed in
`src/services/waitlist/domain/query.ts` and 12 other Query classes:

```ts
private constructor(actor: Actor) {
  if (actor.role === "user") {
    this.filters = { userIds: [actor.userId] };   // auto-injected scope
  } else {
    this.filters = {};                             // admin/system: full access
  }
}
static for(actor: Actor): WaitlistQuery { return new WaitlistQuery(actor); }
```

- `.build()` produces a **serializable** `QueryData` (plain filters +
  pagination + sort) — safe to pass across a workflow/RPC boundary.
- The repository translates filters straight into the WHERE clause. Observed
  (`postgres-projection.ts`): `inArray(table.userId, query.filters.userIds)`
  combined with `and(...conditions)`. The user scope is one `AND` term the
  caller cannot remove — builder methods only add filters, never widen.

**Why query-level beats per-row checks:**
- **No leak surface.** Rows a user may not see never leave the database, so
  pagination counts, aggregates, and "not found" are all correct for free. A
  per-row `if (row.userId !== actor.userId)` after fetching leaks existence and
  breaks counts.
- **Fail-closed by construction.** Forgetting the check is impossible when there
  is no constructor to bypass `for(actor)`; the scope is the *default*, not an
  add-on.
- **One place to reason about tenancy** — the `for` seed — instead of every
  read site.

## 4. Writes: same actor into the aggregate, recorded on events

Commands carry the actor as a first-class field (`actor: ActorSchema` in
`domain/commands.ts`). The aggregate's pure `Transition(deps, cmd, state)`
authorizes before emitting events. Observed in
`src/services/waitlist/domain/transition.ts`:

```ts
const decision = await deps.policy.canApprove({ actor: cmd.actor, entryId: cmd.id });
if (!decision.allow) throw new UnauthorizedWaitlistOperationError("approve", decision.reason, cmd);
// then emit event with data.actor = cmd.actor
```

- The **same actor** established at the edge flows into the command — no
  re-derivation, no ambient identity.
- The actor is **stamped onto the emitted event** (`data.actor: Actor` in
  `domain/events.ts` for conversation, research-artefact, waitlist) — an
  immutable audit trail of who caused each state change.
- Authorization lives in the domain layer via an injected `policy` port
  (`TransitionDeps.policy`), keeping the aggregate testable and the rule engine
  swappable.

## 5. The policy engine (declarative rules for writes)

A central document, evaluated by a generic engine. Observed in
`src/lib/policy-engine/` and `src/config/policy.ts`.

**Structure** — `POLICY_DOCUMENT: PolicyDocument<ServiceActionMap>` is
`{ [service]: { [action]: { rules: Rule[], defaultDenyReason? } } }`, type-keyed
by a compile-time `ServiceActionMap` so every `service.action` must be listed.
Four ordered `Rule` kinds (discriminated union, `types.ts`):

| kind | grants when | else |
| --- | --- | --- |
| `system-allowlist` | actor is `system` AND `serviceId ∈ serviceIds` | deny (system) / skip |
| `ownership` | non-system AND `actorsEqual(actor, resource.owner)` | deny |
| `role-allow` | `actor.role ∈ roles` | **skip** (fall through) |
| `self-service` | `getActorUserId(actor) === resource.targetUserId` | deny |

**Semantics** (`evaluator.ts`, `evaluate(service, action, actor, resource?)`):
- Rules run **in order**; first rule returning a decision wins.
- A rule returns `undefined` to **abstain** (missing context, or wrong actor
  class), and evaluation falls through to the next rule.
- If no rule decides → **`{ allow: false, defaultDenyReason }`**. Fail-closed.
- No wildcards; `"*"` is a literal `serviceId`.

**How policies compose with the §3 query filters** — they are two layers of the
same principle, applied to different verbs:
- **Reads** are authorized *structurally* by the `for(actor)` filter (§3); the
  policy document mostly does not gate list queries.
- **Writes / point-reads** are authorized *declaratively* by the evaluator,
  which needs a `resource.owner`. That owner is fetched using the **same
  actor-first query** — defense in depth. Observed in the message adapter
  (`src/services/message/infrastructure/policy-adapter.ts`): user ownership is
  resolved by `ConversationQuery.for(actor).ids([id])` returning non-empty,
  *not* by the evaluator's ownership rule (owner isn't known upfront / needs an
  async lookup). System actors go through the evaluator's allowlist.

**Adapter pattern:** each service wraps the shared evaluator in a
`<Service>PolicyAdapter` implementing a domain `Policy` port
(`canApprove`, `canViewEntry`, …), wired in `application/factory.ts` with
`new PolicyEvaluator<ServiceActionMap>(POLICY_DOCUMENT)`. The domain depends on
the port, not the engine.

## 6. Testing

- **Policy document as a unit** — `src/config/__test__/policy.test.ts`
  instantiates the real evaluator against `POLICY_DOCUMENT` with fixture actors
  (`owner`, `nonOwner`, `admin`, `systemAllowed`, `systemDenied`) and asserts a
  **coverage-completeness** test: every `service.action` in the map has a policy.
- **Cross-actor isolation as a repository contract** —
  `projection-contract.ts` seeds rows for `user1`/`user2` then asserts
  `Query.for(user1Actor)` returns only user1's rows and *"user1 cannot see
  user2 entries"*. Run against both in-memory and Postgres projections, so the
  filter is verified where it actually executes.
- **Router tests** assert the injected filter reaches the service:
  `expect(mockQuery).toHaveBeenCalledWith({ filters: { userIds: ["...user-123"] }})`
  (`server/routers/__test__/waitlist.test.ts`).

## 7. Language-agnostic essence

The actor-first principle, portable to any service (illustrated in Python/FastAPI):

1. **One closed Actor type.** A tagged union `user | admin | system`; tenancy is
   an explicit field on it. No optional-flag identity objects.
   ```python
   Actor = UserActor | AdminActor | SystemActor   # pydantic discriminated union
   ```
2. **Mint at the edge, pass inward.** Build the actor once from the verified
   session in a dependency; never re-derive identity deeper in.
   ```python
   async def current_actor(session = Depends(auth)) -> Actor:
       if not session: raise HTTPException(401)
       return UserActor(user_id=session.sub)
   ```
3. **Reads: actor seeds the query, no bypass.** A `Query.for(actor)` factory (no
   public constructor) that injects the scope as a filter the builder can only
   narrow; the repository turns it into a `WHERE` term. Prefer this over
   post-fetch per-row checks — it fixes counts, pagination, and existence leaks.
   ```python
   class ArtefactQuery:
       @classmethod
       def for_(cls, actor: Actor) -> "ArtefactQuery":
           q = cls()
           if actor.role == "user": q.filters["user_ids"] = [actor.user_id]
           return q                       # admin/system: unscoped
   ```
4. **Writes: same actor into the command, stamped on the event.** Commands carry
   `actor`; authorize before emitting; persist `actor` in the event for audit.
5. **Declarative policy for writes.** A central `{service: {action: [rules]}}`
   document + ordered, abstaining rule evaluator that is **fail-closed** by
   default. Resolve the resource `owner` via the same actor-first query.
6. **Test two things:** policy coverage completeness, and cross-actor isolation
   as a repository contract executed against the real backend.

**Deviations to carry forward honestly:** flat roles + `userId`-as-tenant suit a
single-tenant-per-user product; a B2B service needs a `tenantId` scope term and
likely a role list. Async ownership (owner not known upfront) is resolved by a
scoped query, not the sync evaluator — expect that split in any real system.
