"""Create four focused, pure-Python analysis notebooks; no BI dashboard."""
from pathlib import Path
import nbformat as nbf

bootstrap='''from pathlib import Path
import os, sys, json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
ROOT=Path.cwd()
if not (ROOT/'tvads').exists(): ROOT=ROOT.parent
os.chdir(ROOT);sys.path.insert(0,str(ROOT))
from tvads.pipeline import current_output
OUT=current_output()
REPORTS=OUT/'reports'
summary=json.loads((REPORTS/'summary.json').read_text())
manifest=json.loads((OUT/'run_manifest.json').read_text())
fact=pd.read_parquet(OUT/'fact_commitments.parquet')
plt.rcParams.update({'figure.dpi':110,'axes.spines.top':False,'axes.spines.right':False})
print('Synthetic snapshot:',summary['as_of'])
'''


def write(name,title,cells):
    book=nbf.v4.new_notebook()
    book.metadata.kernelspec={'display_name':'Python 3','language':'python','name':'python3'}
    book.cells=[nbf.v4.new_markdown_cell(title),nbf.v4.new_code_cell(bootstrap)]
    book.cells += [nbf.v4.new_markdown_cell(text) if kind=='md' else nbf.v4.new_code_cell(text) for kind,text in cells]
    Path('notebooks').mkdir(exist_ok=True)
    nbf.write(book,Path('notebooks')/name)


write('01_data_understanding_and_quality.ipynb','# Source understanding, availability and quality\n\nAll data is synthetic. This notebook checks analytical grain, source availability, duplicates, quarantine and reconciliation before interpreting business metrics.',[
 ('code',"from tvads.warehouse import read_raw\nraw=read_raw(OUT/'raw')\npd.DataFrame([{'source':k,'rows':len(v),'columns':len(v.columns)} for k,v in raw.items()])"),
 ('md','## Grain and relationships\n\nA source event may be replayed, and a commitment may have multiple schedules, airings and invoices. Raw row counts are not interchangeable with contracted units.'),
 ('code',"assert fact.commitment_id.is_unique\nraw_keys={'advertisers':'advertiser_id','campaigns':'campaign_id','stations':'station_id','booking_lines':'booking_line_id','commitments':'commitment_id','scheduled_spots':'scheduled_spot_id','airing_logs':'ingestion_id','invoice_lines':'invoice_line_id','credits':'credit_id'}\npd.DataFrame([{'source':k,'key':v,'unique':raw[k][v].is_unique,'null_cells':int(raw[k].isna().sum().sum())} for k,v in raw_keys.items()])"),
 ('code',"pd.DataFrame(manifest['validation']['quarantine_candidates'].items(),columns=['Source issue','Raw rows'])"),
 ('md','## Source event replay and conflict handling\n\nIdentical factual payloads for one source event count once. Conflicting payloads are ambiguous and cannot establish delivery. Feed defects remain visible in an audit queue.'),
 ('code',"airings=pd.read_csv(OUT/'tableau_ready/fact_airing_review.csv')\nassert airings.source_event_id.is_unique\nquality=airings.airing_status.value_counts().rename_axis('airing_status').reset_index(name='canonical_events')\nquality"),
 ('code',"quality.set_index('airing_status').canonical_events.sort_values().plot.barh(figsize=(8,4),color='#243B55')\nplt.xlabel('Canonical source events');plt.title('Synthetic airing evidence classifications');plt.tight_layout();plt.show()"),
 ('code',"pd.DataFrame([{'measure':'Raw visible feed rows','count':int(airings.raw_record_count.sum())},{'measure':'Unique source events','count':len(airings)},{'measure':'Replay/conflict rows beyond first','count':int(airings.raw_record_count.sum()-len(airings))}])"),
 ('md','## Arrival latency\n\nA valid airing can look absent until its source record arrives. These delays are configured simulation outcomes, not measured broadcaster SLAs.'),
 ('code',"logs=raw['airing_logs'].copy()\nlogs['latency_hours']=(pd.to_datetime(logs.ingested_at,utc=True)-pd.to_datetime(logs.aired_at,utc=True)).dt.total_seconds()/3600\nlogs.latency_hours.describe(percentiles=[0.5,0.9,0.99])"),
 ('code',"logs.groupby(logs.latency_hours.round().astype(int)).size().plot.bar(figsize=(7,3.5),color='#117C83')\nplt.xlabel('Ingestion delay (rounded hours)');plt.ylabel('Feed rows');plt.title('Synthetic source availability');plt.tight_layout();plt.show()"),
 ('md','## Station local time and daylight saving\n\nThe contract uses local station flight dates/dayparts. The warehouse stores UTC timestamps. Validation checks both original and replacement schedules.'),
 ('code',"example=raw['scheduled_spots'].merge(raw['stations'][['station_id','timezone']],on='station_id',validate='many_to_one').head(8).copy()\nexample['local_scheduled_time']=[pd.Timestamp(t).tz_convert(z).isoformat() for t,z in zip(example.scheduled_at,example.timezone)]\nexample[['scheduled_spot_id','scheduled_at','timezone','local_scheduled_time']]"),
 ('md','## Independent count and money controls\n\nAll differences must be zero. Orphan invoices and unapplied orphan credits are included in complete-ledger controls instead of silently disappearing.'),
 ('code',"controls=pd.read_csv(REPORTS/'reconciliation_controls.csv')\nassert controls.status.eq('MATCH').all()\ncontrols"),
 ('md','## Synthetic oracle evaluation\n\nThe generator records injected defect identities and expected root outcomes separately. Those oracle files do not enter SQL or estimation. Perfect scores apply only to this known constructed scenario.'),
 ('code',"summary['oracle_evaluation']"),
])

write('02_delivery_performance_eda.ipynb','# TV campaign delivery and replacement recovery\n\nInvestigate commitment-level delivery, station/daypart segments, due-date trends and campaign-start cohorts at one declared knowledge cutoff.',[
 ('code',"due=fact[fact.due_commitment.eq(1)].copy()\npd.Series({k:summary[k] for k in ['total_commitments','cancelled_commitments','due_commitments','original_deliveries','makegood_recoveries','delivered_commitments','undelivered_mature_commitments','delivery_rate']})"),
 ('md','## Delivery composition\n\nOriginal deliveries plus recovered commitments equal delivered units. Extra airings never create extra contracted units.'),
 ('code',"composition=pd.Series({'Original delivered':summary['original_deliveries'],'Recovered by makegood':summary['makegood_recoveries'],'Unconfirmed at final cutoff':summary['due_commitments']-summary['delivered_commitments']})\ncomposition.plot.barh(figsize=(8,3.5),color=['#243B55','#117C83','#B7791F'])\nplt.xlabel('Due commitments');plt.title('Synthetic commitment delivery composition');plt.tight_layout();plt.show()"),
 ('code',"by_part=due.groupby('daypart').agg(due_commitments=('commitment_id','size'),delivered=('delivered','sum'),original=('original_delivered','sum'),makegood_recovered=('delivery_status',lambda x:x.eq('makegood_delivered').sum()))\nby_part['delivery_rate']=by_part.delivered/by_part.due_commitments\nby_part['original_delivery_rate']=by_part.original/by_part.due_commitments\nby_part"),
 ('code',"(by_part[['original_delivery_rate','delivery_rate']].rename(columns={'original_delivery_rate':'Original delivery','delivery_rate':'Total delivery'})*100).plot.bar(figsize=(8,4),color=['#243B55','#117C83'])\nplt.ylabel('Due commitments (%)');plt.title('Original and eventual delivery at the snapshot cutoff');plt.xticks(rotation=0);plt.tight_layout();plt.show()"),
 ('md','## Station and market comparisons\n\nAlways show sample sizes. Rankings describe this synthetic mix and do not isolate causal station performance.'),
 ('code',"station=due.groupby(['market','station_id']).agg(due_commitments=('commitment_id','size'),delivered=('delivered','sum'))\nstation['delivery_rate']=station.delivered/station.due_commitments\nstation[station.due_commitments>=50].sort_values('delivery_rate').head(12)"),
 ('code',"pd.read_csv(REPORTS/'station_daypart.csv').head(15)"),
 ('md','## Due-date cohorts at the final cutoff\n\nThis chart groups original due dates using outcomes visible at the chosen cutoff. It does not reconstruct what was known on each historical date. Replacement outcomes may have arrived later.'),
 ('code',"trend=pd.read_csv(REPORTS/'delivery_trend.csv',parse_dates=['due_date']).set_index('due_date')\ntrend=trend.reindex(pd.date_range(trend.index.min(),trend.index.max(),freq='D'),fill_value=0)\ntrend['weighted_7day_delivery_rate']=trend.delivered.rolling(7,min_periods=1).sum()/trend.due_commitments.rolling(7,min_periods=1).sum().replace(0,np.nan)\nfig,axes=plt.subplots(2,1,figsize=(10,6),sharex=True)\ntrend[['due_commitments','delivered']].plot(ax=axes[0],color=['#9AA5B1','#117C83']);axes[0].set_ylabel('Commitments')\n(trend.weighted_7day_delivery_rate*100).plot(ax=axes[1],color='#243B55');axes[1].set_ylabel('7-day weighted rate (%)')\naxes[0].set_title('Original due-date cohorts, evaluated at final knowledge cutoff');plt.tight_layout();plt.show()"),
 ('md','## Campaign pacing and cohort analysis\n\nPacing compares actual qualifying delivery against contracted units already due. It is not a forecast, audience-delivery estimate or customer-retention metric.'),
 ('code',"campaign=pd.read_csv(REPORTS/'campaign_delivery.csv')\ncampaign.sort_values(['delivery_rate','due_commitments'],ascending=[True,False]).head(15)"),
 ('code',"cohorts=pd.read_csv(REPORTS/'campaign_start_cohorts.csv')\ncohorts"),
 ('code',"durations=due.groupby('duration_seconds').agg(due_commitments=('commitment_id','size'),original_delivered=('original_delivered','sum'),delivered=('delivered','sum'))\ndurations['original_failure_rate']=1-durations.original_delivered/durations.due_commitments\ndurations"),
 ('md','## Operational recommendation\n\nPrioritize mature unconfirmed commitments using campaign deadline, station evidence and replacement status. Keep awaiting-log items provisional and review segment uncertainty before changing delivery allocation.'),
])

write('03_billing_reconciliation.ipynb','# Contract-defined billable value, invoices and credits\n\nReconcile at commitment grain before interpreting money. These are synthetic billing differences, not platform revenue, recognized revenue, realized savings or collections.',[
 ('code',"pd.Series({k:summary[k] for k in ['expected_billable_cents','matched_net_invoiced_cents','overbilled_cents','underbilled_cents','unbilled_eligible_cents','billing_reconciliation_commitments','billing_reconciliation_rate']})"),
 ('md','## The monetary bridge\n\nExpected billable + overbilling - shortfalls equals matched net invoiced. Opposing discrepancies must remain separate when prioritizing investigations.'),
 ('code',"expected=summary['expected_billable_cents']/100\nover=summary['overbilled_cents']/100\nunder=summary['underbilled_cents']/100\nnet=summary['matched_net_invoiced_cents']/100\nassert abs(expected+over-under-net)<0.00001\nfig,ax=plt.subplots(figsize=(9,4))\nax.bar(['Expected billable','Overbilled','Shortfall','Net invoiced'],[expected,over,-under,net],bottom=[0,expected,expected+over,0],color=['#243B55','#B7791F','#B42318','#117C83'])\nax.set_ylabel('USD');ax.set_title('Synthetic matched-commitment billing bridge');ax.ticklabel_format(axis='y',style='plain');plt.tight_layout();plt.show()"),
 ('md','## Largest commitment differences\n\nThis is the correct monetary investigation grain. A commitment may have multiple exception labels, so summing amounts attached to those labels would duplicate exposure.'),
 ('code',"differences=fact[fact.billing_difference_cents.ne(0)].copy()\ndifferences.sort_values('billing_difference_cents',key=abs,ascending=False)[['commitment_id','advertiser_id','campaign_id','expected_billable_cents','gross_invoiced_cents','credited_cents','net_invoiced_cents','billing_difference_cents']].head(15)"),
 ('code',"advertiser=pd.read_csv(REPORTS/'advertiser_billing.csv')\nadvertiser['absolute_investigation_cents']=advertiser.overbilled_cents+advertiser.underbilled_cents\npriority=advertiser.nlargest(10,'absolute_investigation_cents').sort_values('absolute_investigation_cents')\nfig,ax=plt.subplots(figsize=(9,5))\nax.barh(priority.advertiser_id.astype(str),priority.overbilled_cents/100,color='#B7791F',label='Overbilled')\nax.barh(priority.advertiser_id.astype(str),-priority.underbilled_cents/100,color='#243B55',label='Shortfall')\nax.axvline(0,color='#444444',linewidth=0.8);ax.set_xlabel('USD, separated by discrepancy direction');ax.set_ylabel('Synthetic advertiser ID');ax.legend();ax.set_title('Largest total absolute billing differences');plt.tight_layout();plt.show()"),
 ('md','## Corrective credits and audit history\n\nA wrong rate may already have a correcting credit. Keep the original error traceable without counting a second outstanding financial discrepancy.'),
 ('code',"ledger=pd.read_csv(OUT/'tableau_ready/fact_invoice_ledger.csv')\ncredited=ledger[ledger.credited_cents.gt(0)].merge(fact[['commitment_id','expected_billable_cents','billing_difference_cents']],on='commitment_id',validate='many_to_one')\ncredited[['invoice_line_id','commitment_id','amount_cents','credited_cents','net_invoiced_cents','expected_billable_cents','billing_difference_cents']].head(10)"),
 ('md','## Exception composition\n\nFlags count investigative conditions, not unique commitments or additive money. Unmatched invoices and credits remain visible in full-ledger reconciliation.'),
 ('code',"exceptions=pd.read_csv(OUT/'tableau_ready/exception_queue.csv')\ncounts=exceptions.exception_type.value_counts()\ncounts"),
 ('code',"counts.sort_values().plot.barh(figsize=(9,6),color='#243B55')\nplt.xlabel('Exception flags');plt.title('Synthetic investigation conditions; flags may overlap');plt.tight_layout();plt.show()"),
 ('code',"exceptions[exceptions.exception_type.str.startswith('unmatched')][['exception_type','entity_type','entity_id']].head(10)"),
 ('code',"pd.read_csv(REPORTS/'reconciliation_controls.csv').query(\"unit == 'USD cents'\")"),
 ('md','## Billing recommendation\n\nReview distinct commitment differences first, then inspect charge/credit details. Route payer mismatches internally and keep unmatched references separate. Unbilled eligibility is not automatically overdue because no invoice payment/due-date terms are modeled.'),
])

write('04_statistics_and_recommendations.ipynb','# Uncertainty, adjusted associations and operational recommendations\n\nStatistical outputs describe a configured synthetic population. They do not establish causal effects or real station performance.',[
 ('code',"metadata=json.loads((REPORTS/'statistics_metadata.json').read_text())\nmetadata"),
 ('md','## Campaign-cluster bootstrap\n\nCampaigns are resampled with all their commitments, preserving one source of within-campaign dependence. The interval is conditional on the simulated population and does not include uncertainty about the generator itself.'),
 ('code',"intervals=pd.read_csv(REPORTS/'daypart_intervals.csv')\nintervals"),
 ('code',"fig,ax=plt.subplots(figsize=(8,4))\nax.errorbar(intervals.daypart,intervals.delivery_rate*100,yerr=[(intervals.delivery_rate-intervals.ci_low)*100,(intervals.ci_high-intervals.delivery_rate)*100],fmt='o',capsize=5,color='#117C83')\nax.set_ylabel('Delivery rate (%)');ax.set_title('Synthetic delivery with 95% campaign-cluster intervals');plt.tight_layout();plt.show()"),
 ('md','## Planned Prime-minus-Overnight contrast\n\nThe null contrast is zero. Inspect the estimate and interval rather than interpreting a small p-value as proof of a business mechanism. The generator explicitly encodes daypart risk.'),
 ('code',"contrast=metadata['planned_contrast']\nprint(f\"Synthetic difference: {contrast['estimate']*100:.2f} percentage points\")\nprint(f\"95% cluster-bootstrap interval: {contrast['ci_low']*100:.2f} to {contrast['ci_high']*100:.2f} points\")\ncontrast"),
 ('md','## Adjusted original-delivery failure associations\n\nA binomial logistic model adjusts daypart comparisons for station and 60-second duration. Standard errors cluster by campaign. Intervals are exploratory and unadjusted for multiple comparisons.'),
 ('code',"associations=pd.read_csv(REPORTS/'adjusted_original_failure_associations.csv')\nselected=associations[associations.term.str.contains('daypart|duration_60',regex=True)].copy()\nselected"),
 ('code',"labels=selected.term.str.replace(\"C(daypart, Treatment(reference='Daytime'))[T.\",'',regex=False).str.replace(']','',regex=False).replace({'duration_60':'60 seconds vs 30'})\nfig,ax=plt.subplots(figsize=(9,4))\nax.errorbar(selected.odds_ratio,labels,xerr=[selected.odds_ratio-selected.ci_low,selected.ci_high-selected.odds_ratio],fmt='o',capsize=4,color='#243B55')\nax.axvline(1,color='#999999',linestyle='--');ax.set_xscale('log');ax.set_xlabel('Adjusted odds ratio, original-delivery failure');ax.set_title('Synthetic associations, nominal 95% intervals');plt.tight_layout();plt.show()"),
 ('md','## Evidence-based action list\n\nDelivery: review mature unconfirmed roots and approved replacement opportunities. Billing: prioritize root-level discrepancies and reconcile credits. Engineering: resolve conflicting logs and unknown keys. Product/analytics reviewers: approve cutoffs, definitions and priority rules before deployment. These are proposed roles, not a claim of completed stakeholder collaboration.'),
 ('code',"print((REPORTS/'recommendations.md').read_text())"),
 ('md','## Bias, limitations and next phase\n\nStation mix, campaign composition, billing lag and observation cutoff change measured rates. Original-delivery failure differs from eventual failure after replacements. No audience ratings, conversions, paid spend, payments or randomized treatments are available. No BI dashboard is created; use the documented Tableau-ready data contract for the next phase.'),
])
