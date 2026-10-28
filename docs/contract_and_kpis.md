# Contract assumptions and metric dictionary

## Explicit case-study rules

- A booking line fixes station, daypart, creative, duration and USD unit price.
  A commitment is one promised spot and can earn at most one unit price.
- One original schedule exists per commitment. Authorized replacements refer
  directly to that original, remain in its station/daypart/creative/duration,
  and occur within seven days. They may extend beyond the original flight.
- A qualifying airing falls between five minutes before and fifteen minutes
  after its scheduled timestamp, inclusive. All required attributes must match.
- Original campaign flight dates and dayparts use station local time. Source
  timestamps use UTC. Generated replacement times preserve local wall-clock
  scheduling across the spring daylight-saving transition.
- Cancelled commitments are excluded from delivery denominators and cannot
  become billable, even if an unexpected airing is observed.
- Log grace is 48 hours after the original window closes. Before that, missing
  evidence is `awaiting_log`. Afterward, `undelivered` means no qualifying
  evidence is visible at the cutoff, not proof that a broadcaster never aired it.
- Invoice quantity should be one. Billing becomes eligible when a due,
  noncancelled commitment has qualifying delivery. There is no modeled invoice
  payment term; an unbilled item is not automatically overdue or an error.
- Credits reduce the matching visible invoice line. Orphan credits remain
  separate. Immutable rate errors can retain audit flags after a corrective
  credit makes the root amount reconcile.
- All money is stored and reconciled in integer USD cents. Display conversion
  to dollars occurs only in presentation outputs. No currency conversion occurs.
- Contract/schedule plans are assumed known in advance. Event, invoice and
  credit availability is explicitly time-filtered. Versioned contract changes
  are not simulated.

## Metrics

| Metric | Definition and denominator | Interpretation |
|---|---|---|
| Due commitments | Noncancelled commitments whose original window end is at/before cutoff | One row per root commitment |
| Delivery rate | Due commitments with qualifying original or authorized replacement evidence / due commitments | Undefined when none are due |
| Original delivery rate | Due commitments delivered in the original approved window / due commitments | Closest operational measure of original on-time delivery |
| Makegood recoveries | Due commitments with replacement evidence and no qualifying original evidence | Add to original deliveries to get total delivered roots |
| Campaign pacing | Delivered due commitments / planned commitments due by the same cutoff | Uses the contracted schedule, not a uniform daily target |
| Expected billable value | Sum of one contracted unit price per delivered due commitment | Contract-defined eligibility, not platform/recognized revenue |
| Gross matched billing | Sum of visible invoice amounts referencing known commitments | Multiple lines are aggregated before joining delivery |
| Net matched billing | Gross matched billing minus credits on those invoice lines | All at commitment grain |
| Billing reconciliation rate | Zero-difference commitments / commitments with positive eligibility or at least one visible invoice | Excludes all-zero inactive/cancelled roots |
| Overbilled value | Sum of positive (net invoiced minus expected billable) per commitment | Do not offset against shortfalls for prioritization |
| Underbilled value | Sum of positive (expected billable minus net invoiced) per commitment | Includes eligible delivery without any invoice |
| Unbilled eligible value | Expected value for billable commitments with zero visible invoice lines | May be operational timing rather than a confirmed billing error |
| Exception flags | Number of unique type/entity-type/entity-ID combinations | Several flags can refer to one commitment; amounts are not additive |
| Data freshness | Latest source event timestamp available at cutoff, with ingestion timestamp retained | This static simulation has no real-time SLA |

An amount-reconciled commitment can still have a payer mismatch or an immutable
audit flag. This rate is not an all-controls compliance measure.

The money bridge is:

`Expected billable + Overbilled - Underbilled = Matched net invoiced`.

The complete ledger control additionally includes orphan invoices and unapplied
orphan credits. These amounts are not silently assigned to an advertiser.

## Statistical scope

Delivery intervals resample campaigns, preserving repeated commitments within
each sampled campaign. The planned Prime-minus-Overnight contrast is an
exploratory association. Logistic regression models failure of original delivery,
adjusting for station and 60-second duration, with campaign-cluster robust errors.
Intervals and p-values are nominal and not adjusted for multiple comparisons.
The generator deliberately encodes risk differences: recovering those
relationships validates method, not an empirical claim about the TV industry.
