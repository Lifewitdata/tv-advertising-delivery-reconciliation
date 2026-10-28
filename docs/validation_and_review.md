# Validation evidence and review

## Automated coverage

Tests verify deterministic generation, schema/key contracts, integer money,
invoice arithmetic, station-local flight/daypart rules, replacement references,
timestamp availability, replay/conflict handling, exact airing-window boundaries,
late-log recovery, cancellation exclusions and fanout prevention.

All final commitment delivery/billing outcomes and exception identities are
compared with independent generator oracles. This is a deterministic synthetic
acceptance test, not a claim of perfect detection on unseen operational data.

Ten source controls reconcile counts and money, including orphan records. Eight
analytical SQL statements execute in SQLite and PostgreSQL WASM. PostgreSQL
compares all 18,000 root rows with SQLite for delivery, original delivery,
expected billable value, net billed value and signed differences. Two reporting
roles are positively and negatively tested. An index benchmark records real
EXPLAIN ANALYZE/BUFFERS output with equivalent results.

Operational tests cover overlapping refreshes, failure recovery, input snapshot
hashes, empty operational feeds and requests beyond the observation horizon.
Export tests check data grain, absence of oracle fields in analytical facts and
the requested absence of BI dashboard/workbook files.

Four pure-Python notebooks execute with saved tables and plots. All ten static
analysis charts were visually reviewed. The Excel investigation workbook was
recalculated, error-scanned, tested with a status change and visually reviewed on
all three sheets. Native Microsoft Excel and PivotTables were not tested.

## Review boundaries

No Tableau/Power BI dashboard, calculated fields, filters, actions or rendering
are implemented or claimed. They belong to the separately requested next phase.
PGlite uses PostgreSQL compiled to WASM; this verifies SQL behavior but does not
establish production server throughput, network behavior or deployment security.

Before applying the approach to real data, an analytics reviewer should approve
grain/definitions, Delivery should approve airing and replacement rules, Billing
should approve invoice eligibility/credits, and Engineering should approve source
identity/availability contracts. Record actual review feedback in the PR rather
than treating this checklist as evidence of collaboration already performed.
