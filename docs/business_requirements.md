# Business brief

## Purpose and audience

Help an advertising-platform delivery lead and billing analyst identify
unconfirmed TV delivery and explain contract-to-invoice discrepancies. This
synthetic case study is inspired by the local television advertising platform
described in GIGA IT's Data Analyst SQL Senior vacancy:
https://jobs.jobvite.com/jobs-gigait/job/oTE0AfwR

No GIGA IT system, client, commercial term or production result is represented.
All names and records are synthetic. The rules below are case-study choices.

## Decisions

| Reader | Decision | Evidence |
|---|---|---|
| Delivery lead | Which due commitments require station investigation or an authorized replacement? | Original and replacement evidence, source availability, grace status |
| Billing analyst | Which root commitments differ from contract-defined billable value after credits? | Invoice lines, credits, rates, quantities and commitment-level bridge |
| Engineering | Which feeds contain replays, conflicting facts or unknown references? | Stable source event IDs and a separate quarantine/investigation queue |
| Product/analytics reviewer | Are denominators, cutoffs and exception priorities appropriate? | KPI dictionary, explicit assumptions and reproducible tests |

These are proposed review responsibilities. No real stakeholder collaboration
or mentoring is claimed by the repository.

## Acceptance criteria

1. One commitment remains one contracted unit even if it has replacement spots,
   duplicate airings or multiple invoice lines.
2. Qualifying evidence uses the correct station, creative, duration and approved
   airing window. Station timezones and daylight-saving changes are respected.
3. An event or invoice is unavailable until both its event time and ingestion
   time are at or before the reporting cutoff.
4. Replayed source events are deduplicated. Conflicting payloads are quarantined
   as ambiguous evidence rather than accepted by choosing an arbitrary version.
5. All source counts and money amounts reconcile, including unknown references.
6. The final snapshot matches independent generator oracles for delivery,
   billable amounts, net invoices and known injected exception identities.
7. Both SQLite and PostgreSQL produce identical commitment-level results.
8. Reporting roles see only their advertiser's summary and cannot read raw
   invoices or change reporting data.
9. Failed refreshes preserve the last successful snapshot and its inputs.
10. No Tableau, Power BI or other BI dashboard is created in this phase.

## Out of scope

Audience ratings, clicks, conversions, ROAS, realized savings, recognized
revenue, payments, foreign-exchange conversion, customer retention and causal
campaign uplift are not supported by these sources. No live ingestion service
or incremental change-data-capture system is claimed. Tableau-ready datasets
are prepared for a later dashboard phase.
