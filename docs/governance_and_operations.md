# Governance and operations

All records are synthetic. No client identifiers, real station performance,
commercial contracts or personal data are present. Raw source rows and full
analytical exports are generated per run rather than committed as loose data.

## Demonstrated access controls

`sql/40_reporting_security.sql` creates a separate reporting table with row-level
security and two NOLOGIN roles. Each role can SELECT its advertiser's commitment
summary. Tests deny raw invoice access and reporting writes. Owners/superusers
remain trusted administrators; NOLOGIN demonstration roles do not provision
real accounts. Production deployment needs least-privilege login mapping, TLS,
secret management, platform permissions and tested distribution controls.

An offline CSV or Excel workbook is not protected by database RLS. Full
cross-advertiser exception feeds are internal analytical data. Scope real client
exports before distribution, especially payer-mismatch records that may mention
another advertiser. Do not publish sensitive extracts to Tableau Public.

## Data quality and failure handling

Missing/extra source columns, malformed timestamps, noninteger money, broken
contract keys, invalid local dayparts and invalid replacements fail the run.
Expected event-feed defects become explicit exceptions. Replayed identical
events are counted once. Conflicting factual versions are not accepted as valid
evidence. Unknown invoice or credit references remain in quarantine controls.

Snapshots use both event and ingestion timestamps. A final cutoff is declared
in configuration, and future cutoffs beyond that horizon are rejected. No
network source fallback, background email or external message is performed.

Failed refreshes remove staging outputs and retain the last completed run.
The latest pointer is a regular JSON file, atomically replaced after successful
analysis. Old run folders remain available for comparison until explicitly
cleaned up. The OS releases the advisory writer lock if a process terminates.

## Excel investigation workbook

The optional workbook is a snapshot of all commitment-level billing differences.
It uses source cents, exact advertiser lookup, formulas converting to USD,
SUMIFS/COUNTIFS and a filterable review table. Owner/status/notes are editable.
Changing a review status changes the open investigation totals, not financial
source amounts. Rebuilding resets review inputs; preserve human notes in a
separate keyed register before refreshing.

`scripts/build_excel.mjs` requires `@oai/artifact-tool`, which is optional and
not a dependency of the open Python/Node pipeline. The shipped workbook is
recalculated, formula-scanned and visually reviewed with that tool. Native Excel
and native PivotTables are not claimed as tested. No BI dashboard is included.

## SQL performance evidence

The PostgreSQL WASM verifier executes all analytical queries and compares every
commitment's delivery and billing fields with SQLite. An isolated fixture
benchmarks the same selective query before/after a composite index, checks
identical results, warms both conditions and records seven EXPLAIN ANALYZE /
BUFFERS JSON plans each. These are local synthetic WASM measurements, not
production database SLAs or guaranteed speedups.
