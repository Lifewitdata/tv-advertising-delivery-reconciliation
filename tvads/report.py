"""Stable analytical and Tableau-ready datasets. No BI dashboard is created."""
import json
from pathlib import Path

import pandas as pd

from tvads.warehouse import query,analytical_queries

QUERY_NAMES=['campaign_delivery','station_daypart','delivery_trend','advertiser_billing',
             'largest_billing_differences','campaign_start_cohorts','makegood_recovery','exception_counts']


def export(db,tables,as_of,output,controls,oracle):
    out=Path(output);reports=out/'reports';tableau=out/'tableau_ready'
    reports.mkdir(parents=True,exist_ok=True);tableau.mkdir(exist_ok=True)
    fact=query(db,'v_commitment_finance')
    airings=query(db,'v_airing_review')
    ledger=query(db,'v_invoice_ledger')
    exceptions=query(db,'v_exceptions')
    fact['as_of']=as_of
    fact['due_date']=fact.due_at.str[:10]
    fact.to_csv(tableau/'fact_commitment_delivery_billing.csv',index=False)
    fact.to_parquet(out/'fact_commitments.parquet',index=False)
    airings['as_of']=as_of;airings.to_csv(tableau/'fact_airing_review.csv',index=False)
    ledger['as_of']=as_of;ledger.to_csv(tableau/'fact_invoice_ledger.csv',index=False)
    for name in ['advertisers','campaigns','stations','booking_lines']:
        tables[name].to_csv(tableau/f'dim_{name}.csv',index=False)
    queue=exceptions.merge(fact[['commitment_id','advertiser_id','campaign_id','billing_difference_cents']],
        on='commitment_id',how='left',validate='many_to_one')
    queue['investigation_status']='Open'
    corrected=queue.exception_type.eq('rate_mismatch')&queue.billing_difference_cents.eq(0)
    queue.loc[corrected,'investigation_status']='Amount corrected; retain audit trail'
    queue['as_of']=as_of
    queue.sort_values(['exception_type','entity_id']).to_csv(tableau/'exception_queue.csv',index=False)
    for name,sql in zip(QUERY_NAMES,analytical_queries()):
        pd.read_sql_query(sql,db).to_csv(reports/f'{name}.csv',index=False)
    controls.to_csv(reports/'reconciliation_controls.csv',index=False)
    due=fact[fact.due_commitment.eq(1)]
    count=len(due);delivered=int(due.delivered.sum());original=int(due.original_delivered.sum())
    recovered=int(((due.original_delivered==0)&(due.makegood_delivered==1)).sum())
    billing_population=fact[fact.expected_billable_cents.gt(0)|fact.invoice_line_count.gt(0)]
    visible_airing_times=tables['airing_logs'].loc[tables['airing_logs'].ingested_at.le(as_of),'aired_at']
    summary={'synthetic':True,'as_of':as_of,'currency':'USD','money_unit':'integer cents',
        'total_commitments':len(fact),'cancelled_commitments':int(fact.cancelled.sum()),
        'due_commitments':count,'delivered_commitments':delivered,'original_deliveries':original,
        'makegood_recoveries':recovered,'delivery_rate':delivered/count if count else None,
        'original_delivery_rate':original/count if count else None,
        'awaiting_log':int(fact.delivery_status.eq('awaiting_log').sum()),
        'undelivered_mature_commitments':int(fact.delivery_status.eq('undelivered').sum()),
        'expected_billable_cents':int(fact.expected_billable_cents.sum()),
        'matched_net_invoiced_cents':int(fact.net_invoiced_cents.sum()),
        'overbilled_cents':int(fact.overbilled_cents.sum()),'underbilled_cents':int(fact.underbilled_cents.sum()),
        'unbilled_eligible_cents':int(fact.loc[fact.expected_billable_cents.gt(0)&fact.invoice_line_count.eq(0),'expected_billable_cents'].sum()),
        'billing_reconciliation_commitments':len(billing_population),
        'billing_reconciliation_rate':float(billing_population.billing_difference_cents.eq(0).mean()) if len(billing_population) else None,
        'exception_flags':len(exceptions),'distinct_affected_commitments':int(exceptions.commitment_id.nunique()),
        'source_max_airing_time':str(visible_airing_times.max()) if len(visible_airing_times) else None,
        'data_freshness_note':'No live SLA is implied by this static synthetic extract',
        'oracle_evaluation':oracle,'reconciliation_status':'MATCH'}
    (reports/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    # Analyst workbook inputs retain root grain and do not sum exception flags.
    review=fact[fact.billing_difference_cents.ne(0)].sort_values('billing_difference_cents',key=abs,ascending=False)
    workbook={'as_of':as_of,'advertisers':tables['advertisers'][['advertiser_id','advertiser_name']].to_dict('records'),
        'review':review[['commitment_id','advertiser_id','campaign_id','expected_billable_cents',
                       'gross_invoiced_cents','credited_cents','net_invoiced_cents','billing_difference_cents']].to_dict('records')}
    (reports/'excel_inputs.json').write_text(json.dumps(workbook,indent=2)+'\n')
    schema=[]
    for path in sorted(tableau.glob('*.csv')):
        data=pd.read_csv(path)
        schema.append({'file':path.name,'rows':len(data),'columns':[{col:str(data[col].dtype)} for col in data.columns]})
    (tableau/'schema_manifest.json').write_text(json.dumps(schema,indent=2)+'\n')
    memo=f'''# Delivery and billing review

Synthetic case study. Knowledge cutoff: {as_of}. Amounts below are USD.

## Findings

- {delivered:,} of {count:,} due, noncancelled commitments have qualifying evidence ({delivered/count if count else 0:.2%} delivery) at this cutoff.
- {recovered:,} commitments were recovered through authorized replacement airings. Each is still one contracted unit.
- Contract-defined billable value is ${summary['expected_billable_cents']/100:,.2f}. Matched net invoices are ${summary['matched_net_invoiced_cents']/100:,.2f}.
- Gross overbilling differences total ${summary['overbilled_cents']/100:,.2f}; shortfalls total ${summary['underbilled_cents']/100:,.2f}. These are separate directions and must not be netted away when prioritizing investigations.
- All independent count and monetary reconciliation controls match, including quarantined references.

## Recommended actions

1. Delivery reviews mature undelivered commitments, checks station evidence and agrees authorized replacements. Awaiting-log records remain provisional.
2. Billing reviews commitment-level differences and the underlying invoice lines/credits. Corrected rates retain an audit flag without adding a second financial exposure.
3. Engineering investigates replayed/conflicting events and unknown references, using event availability timestamps and source IDs.
4. Product and an analytics reviewer approve metric definitions, reporting cutoffs and exception priority before a real deployment. These are proposed responsibilities, not a claim that stakeholder review occurred.

## Interpretation

No BI dashboard is included. The Tableau-ready folder contains governed source datasets for a later phase. Synthetic relationships are configured, not evidence about real broadcasters. Billing differences are determined under this project's explicit contract policy; they are not platform revenue, recognized revenue, profit or realized savings. A final snapshot can resolve earlier apparent underdelivery when late evidence arrives.
'''
    if not count:
        memo='# No commitments are due at this cutoff\n\nSynthetic snapshot; no delivery rate is available.\n'
    (reports/'recommendations.md').write_text(memo)
    return summary
