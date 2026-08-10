# 1C Procurement Control Tower

## What

Python procurement-planning service designed to consume 1C operational data: synthetic stock, reservations, demand, incoming supply, safety stock and supplier offers in this reference bundle. It produces an explainable recommendation and creates only an approved draft order reference.

## Why

Choosing the lowest unit price ignores available balance, MOQ, pack rounding, minimum order value, stock, lead time, reliability, currency and data freshness. A locked supplier also has different semantics from a preference. This engine evaluates every hard constraint before scoring.

## Architecture

- Immutable inventory and offer inputs with validation.
- Pure shortage, pack and minimum-value quantity calculations.
- Policy-driven feasibility and explainable score components.
- Recommendation evidence containing every candidate and rejected constraint.
- Approval service with deterministic IDs and idempotent draft creation.
- Generator for a 500 SKU × 5 supplier synthetic functional scenario, not a load benchmark.

## Key engineering decisions

- `available = physical - reserved`; projected balance includes demand and incoming.
- Stale, over-lead, under-stock or unknown-currency offers cannot silently win.
- An infeasible locked supplier forbids automatic fallback.
- Preferences affect score but never bypass a hard constraint.
- Approval and draft creation preserve a recommendation fingerprint.

## Run

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .
```

## Test

```bash
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
```

The suite contains more than 20 deterministic business scenarios.

CI also runs `ruff` and `compileall` over the code and synthetic fixtures. It does not contact 1C, n8n or supplier systems.

## Limitations

- No live 1C/n8n/supplier connection or automatic order posting.
- Currency conversion requires an explicit future rate provider; foreign offers currently require review.
- `bsl/PurchaseOrderDraft.bsl` is an illustrative configuration-mapped adapter, not runtime-tested on a 1C platform.
