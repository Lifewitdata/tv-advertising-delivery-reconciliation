# Local TV Advertising Delivery and Billing Reconciliation

An end-to-end synthetic analytics project that checks whether booked television
commercials have qualifying delivery evidence and whether invoices match
contract-defined billable value after credits.

The project includes a reproducible data pipeline, SQL models, analysis notebooks,
validation, reporting and published Tableau dashboards.

## Live Tableau dashboards

| Dashboard | Open in Tableau Public |
|---|---|
| Delivery Overview | [View dashboard](https://public.tableau.com/app/profile/isfaque.ansari5273/viz/TV_Delivery_Dashboard/DeliveryOverview) |
| Billing Reconciliation | [View dashboard](https://public.tableau.com/app/profile/isfaque.ansari5273/viz/TV_Billing_Dashboard/BillingReconciliation) |

Built and published by Isfaque Ansari using the project's synthetic TV advertising
data. The dashboards complement the SQL/Python analysis and reconciliation reports.

## Business questions

- Which due campaigns/commitments lack qualifying evidence at the reporting cutoff?
- Which original delivery failures were recovered through authorized replacement airings?
- Which station/daypart segments merit investigation, with sample sizes and uncertainty?
- Which charges, credits, rates, quantities or advertiser references do not reconcile?
- Can source counts and money be traced through preparation to reporting without fanout?

The scenario is inspired by the local television advertising platform in
All data and commercial rules are invented for the case study. No company/client
systems, records, real performance or confidential contracts are represented.

## Verified synthetic snapshot

| Measure | Default run |
|---|---|
| Contracted commitments | 18,000 |
| Advertisers / campaigns / stations | 30 / 120 / 24 |
| Source scheduling period | January–June 2026, station local time |
| Knowledge cutoff | 2026-07-15T00:00:00Z |
| Due, noncancelled commitments | 17,438 |
| Qualifying delivered commitments | 16,817 (96.44%) |
| Recovered through replacements | 737 |
| Contract-defined billable value | $2,928,742.64 |
| Overbilling differences / shortfalls | $252,402.59 / $171,974.54 |
| Exception flags / affected commitments | 8,988 / 5,174 |
| Source reconciliation controls | 10 matching count/money controls |

These are constructed outcomes, not realized revenue, recovered savings or
real advertiser results. Known injected defect identities and expected outcomes
match exactly at the final cutoff. That score does not estimate accuracy on
unseen operational data. See [sample results](sample_outputs/summary.json) and
[recommendations](sample_outputs/recommendations.md).

## Reproduce the complete project

Use Python 3.12 and Node 22+ on Linux/macOS or WSL. Dependencies are pinned.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm ci
bash scripts/run_project.sh
```

The script generates nine source tables, validates contracts, builds a SQLite
warehouse, prepares delivery/finance facts, reconciles source totals, estimates
exploratory statistics, verifies PostgreSQL behavior/access/index plans, executes
all four notebooks, runs tests and packages full datasets for Tableau analysis.

`outputs/latest.json` points to the completed snapshot. Each run keeps its exact
raw inputs, independent oracle files, database, reports, Tableau-ready CSVs and
source SHA-256 controls together. A failed run preserves the previous snapshot.
Refreshes are full rebuilds, not incremental production ingestion.

For a different historical knowledge cutoff, run:

```bash
python -m tvads.pipeline --as-of 2026-05-31T23:59:59Z
```

This filters event and ingestion availability. The final-snapshot oracle is not
applied to earlier snapshots. Statistical estimation skips unsupported small or
single-outcome populations. The four shipped notebooks target the rich final
snapshot; return to the default run before executing them.

## Analysis notebooks

| Notebook | Coverage |
|---|---|
| [01 Source quality](notebooks/01_data_understanding_and_quality.ipynb) | Grains, source schemas, replays/conflicts, latency, local time and reconciliation |
| [02 Delivery EDA](notebooks/02_delivery_performance_eda.ipynb) | Original/replacement delivery, station/daypart segments, due-date trends, campaign pacing/cohorts |
| [03 Billing reconciliation](notebooks/03_billing_reconciliation.ipynb) | Money bridge, invoice/credit audit, root-level prioritization and overlapping exceptions |
| [04 Statistics and recommendations](notebooks/04_statistics_and_recommendations.ipynb) | Campaign-cluster intervals, planned contrast, adjusted logistic associations, bias and actions |

The notebooks use the tested shared modules. They contain saved executed tables
and ten static analysis plots. Due-date trends show outcomes known at the selected cutoff, not historical
real-time snapshots. This distinction is explicit in the trend interpretation.

## Modeling and correctness choices

- One commitment is one contracted unit. Replacements and duplicate valid airings
  cannot increase its billable quantity.
- Canonical source events are deduplicated before delivery checks. Conflicting
  payloads are quarantined instead of arbitrarily accepted.
- Credits aggregate to invoice line, invoices aggregate to commitment, and only
  then are billing and delivery joined. Money remains integer USD cents.
- Reporting uses both event time and ingestion time. Missing evidence can remain
  provisional during a 48-hour log grace period and can resolve in later snapshots.
- Original schedules and replacements respect station timezones/dayparts and
  daylight-saving changes. The approved window and replacement policy are
  explicit synthetic assumptions.
- Statistical intervals resample campaigns. Original-failure regression adjusts
  station/daypart/duration with campaign-cluster robust errors. Relationships are
  configured by the generator; no causal or real-market conclusion is supported.

## SQL and engineering evidence

Eight analytical SQL statements cover joins, CTEs, conditional aggregation,
window functions, market ranks, cumulative due-date cohorts and money/exception
analysis. PostgreSQL WASM verifies all 18,000 commitments against SQLite.
Two NOLOGIN reporting roles enforce advertiser isolation and deny raw invoice
reads and writes. An isolated before/after composite-index benchmark records
EXPLAIN ANALYZE/BUFFERS JSON and seven warmed executions per condition.
These measurements are local demonstrations, not production SLAs.

## Reports and Tableau preparation

- [Reconciliation controls](sample_outputs/reconciliation_controls.csv)
- [Billing investigation workbook](sample_outputs/billing_investigation.xlsx)
- [Statistical methods/results](sample_outputs/statistics_metadata.json)
- [PostgreSQL verification](sample_outputs/postgres_verification.json)
- [Source schema samples](data/samples/README.md)
- [Tableau data contract](docs/tableau_data_contract.md)

Full raw sources, oracles, reports and Tableau-ready facts/dimensions are in the
`tv_advertising_verified_data.zip` produced by the script and attached to a
successful [GitHub Actions run](https://github.com/Lifewitdata/tv-advertising-delivery-reconciliation/actions). Regenerate them at any time using
the seed/configuration. The small committed source fragments are schema samples,
not the complete analysis dataset.

The Excel snapshot includes source cents, exact advertiser lookup, formulas,
SUMIFS/COUNTIFS, a filterable investigation table and editable owner/status/notes.
It was recalculated, error-scanned and visually reviewed with artifact-tool.
The optional authoring script requires `@oai/artifact-tool`; the open Python/Node
pipeline does not. Native Excel/PivotTables were not tested. This workbook is
an analyst investigation aid, not a BI dashboard.

## Documentation

[Business requirements](docs/business_requirements.md),
[contract rules and KPIs](docs/contract_and_kpis.md),
[data model and lineage](docs/data_model_and_lineage.md),
[governance/operations](docs/governance_and_operations.md),
[validation/review](docs/validation_and_review.md).

Actual review, mentoring and cross-functional collaboration cannot be proven
by code alone. Proposed reviewer responsibilities are documented without
claiming those activities occurred. No production pipeline deployment, client data access,
real financial impact, ratings, clicks, ROAS or retention analysis is claimed.
