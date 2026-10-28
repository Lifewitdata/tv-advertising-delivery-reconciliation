# Tableau data preparation contract

**BI/dashboard creation is deferred by request.** There is no `.twb`, `.twbx`,
`.hyper`, `.pbix` or dashboard prototype in this project.

All CSVs below are generated under the completed run's `tableau_ready/` folder.
Download the verified run artifact from GitHub Actions or regenerate locally.
`schema_manifest.json` lists columns, observed dtypes and row counts.

| File | Grain/key | Safe relationship/use |
|---|---|---|
| fact_commitment_delivery_billing.csv | One commitment_id | Primary delivery and billing fact; all money in cents |
| fact_airing_review.csv | One source_event_id | Detailed evidence; one commitment may have several events |
| fact_invoice_ledger.csv | One invoice_line_id | Charge/credit audit; one commitment may have several lines |
| exception_queue.csv | exception_type + entity_type + entity_id | Investigation queue; multiple flags per commitment |
| dim_advertisers.csv | advertiser_id | Many commitments to one advertiser |
| dim_campaigns.csv | campaign_id | Many commitments to one campaign |
| dim_stations.csv | station_id | Many commitments to one station |
| dim_booking_lines.csv | booking_line_id | Many commitments to one contracted line |

Every fact includes the reporting cutoff. Do not combine runs with different
cutoffs without explicitly adding a snapshot dimension and handling repeated
commitments. Due dates are UTC export dates; station-local scheduling is already
validated in the analytical layer.

Use logical relationships or pre-aggregated data. Do not physically join the
three facts and sum their duplicated commitment amounts. Delivery rate must use
the due population and be calculated as a ratio of sums. A future financial
view should sum commitment-level overbilled/underbilled amounts, not exception
flag amounts. These files do not include actual audience impressions or clicks.

Advertiser filtering is not access control. The full synthetic extracts contain
all advertisers for portfolio review; real client exports must be scoped before
distribution. Native Tableau calculated fields, filters, drill-downs, dashboard
actions, rendering and performance will be built and tested in the next phase.
