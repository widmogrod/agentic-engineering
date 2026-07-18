# Technical communication at signature altitude

How to express a design without implementation detail. Use the project's
language for signatures; use the notations below for everything else.

## Signatures

Types and names carry the design; bodies are elided with `...`. Always show
the error channel — it is part of the contract, not a detail.

```python
def resolve_schedule(pool: PoolId, at: ZurichTime) -> Result[Schedule, ResolveError]: ...

class OutboxStore(Protocol):
    def append(self, events: Sequence[DomainEvent], *, tx: Tx) -> Result[None, Conflict]: ...
```

```typescript
type PlaceOrder = (cmd: PlaceOrderCmd, actor: Actor) => Promise<Result<OrderId, OrderError>>
```

Rules: real parameter and type names (no `foo`/`any`); closed error unions
spelled out; async-ness visible; ownership visible (method on which construct?).

## Data flow

Arrow notation for linear flows, one step per line. `-->` is a synchronous
call, `~~>` is asynchronous (queue/event), `+` groups same-transaction work:

```
POST /orders --> validate(dto) --> place_order(cmd)
place_order: persist(Order) + outbox.append(OrderPlaced)     # same tx
OrderPlaced ~~> reserve_inventory ~~> InventoryReserved | InventoryFailed
InventoryFailed ~~> compensate: cancel_order
```

For flows with 4+ participants or request/response pairing, use a mermaid
`sequenceDiagram` instead. For topology (who talks to whom, not when), use a
mermaid `flowchart`.

## Branching and outcomes

Express outcomes as alternatives with `|`, and map them to effects:

```
validate(input) -> Ok(order) | Err(Invalid -> 422) | Err(Duplicate -> 409)
```

## State machines

Small ones as a table — it forces totality:

| state × event | action | next state |
|---|---|---|
| `pending` × `Confirm` | reserve inventory | `confirmed` |
| `pending` × `Cancel` | — | `cancelled` |
| `confirmed` × `Cancel` | release inventory | `cancelled` |

Larger ones as mermaid `stateDiagram-v2`. Either way: unlisted transitions are
illegal — say what happens on illegal transitions (reject? no-op?).

## Invariants

Plain assertions, one per line, testable as written:

- An order's `total` equals the sum of its lines at all times.
- `OrderPlaced` is emitted in the same transaction as the order row (outbox).
- Cancelling an already-cancelled order is a no-op, not an error.

## Contracts (API shapes)

Typed models, not example JSON:

```python
class PlaceOrderRequest(BaseModel):
    lines: list[OrderLine]          # min_length=1
    idempotency_key: UUID
```

## Trade-off tables

| | A: sync call | B: outbox event |
|---|---|---|
| consistency | strong | eventual |
| coupling | temporal | none |
| failure mode | caller sees it | retry + DLQ |

## What does NOT belong at this altitude

Implementation bodies, imports, framework wiring, config values, logging,
retry/backoff numbers, variable naming inside functions, performance
micro-decisions. If it wouldn't change a reviewer's opinion of the design,
leave it out.
