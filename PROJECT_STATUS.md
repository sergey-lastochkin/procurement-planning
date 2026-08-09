# Project status

## IMPLEMENTED

Inventory projections; shortage calculation; MOQ, pack and minimum-order-value quantity rules; freshness, stock, lead and currency constraints; preferred/locked supplier semantics; explainable scoring/evidence; approval and idempotent draft creation; 500-SKU/5-supplier generator.

## TESTED

Python 3.12 unit suite with more than 20 business scenarios, including invalid inputs, all hard constraints, deterministic tie breaks, approval and replay.

## NOT TESTED

BSL is not runtime-tested on a 1C platform. Live supplier, exchange-rate, n8n and 1C endpoints were not used.

## EXTERNAL DEPENDENCIES

Python 3.12+ and `pytest` for tests; standard library for runtime core.

## KNOWN LIMITATIONS

One offer is selected per SKU; multi-supplier split optimization and portfolio-wide freight tiers are not modeled. Foreign currency is blocked without a rate provider.

## NEXT PRODUCTION STEPS

Add authenticated 1C input/output contracts, supplier freshness SLAs, rate service, multi-order optimization, persistence, role-based approval and acceptance tests in a mapped 1C test configuration.
