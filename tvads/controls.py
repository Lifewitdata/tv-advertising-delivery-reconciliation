"""Independent source controls and separate synthetic-oracle evaluation."""
import pandas as pd


def reconcile(tables,as_of,fact,airings,ledger,db):
    rows=[]
    def check(name,source,modeled,unit):
        rows.append({'control':name,'source_value':int(source),'modeled_value':int(modeled),
            'difference':int(modeled-source),'unit':unit,'status':'MATCH' if source==modeled else 'MISMATCH'})
    roots=tables['commitments']
    due=roots[(roots.due_at<=as_of)&roots.cancelled.eq(0)]
    check('commitment_grain',len(roots),len(fact),'commitments')
    check('due_commitments',len(due),fact.due_commitment.sum(),'commitments')
    logs=tables['airing_logs']
    visible=logs[(logs.ingested_at<=as_of)&(logs.aired_at<=as_of)]
    check('visible_airing_records',len(visible),airings.raw_record_count.sum(),'source rows')
    check('canonical_airing_events',visible.source_event_id.nunique(),len(airings),'events')
    inv=tables['invoice_lines']
    inv=inv[(inv.issued_at<=as_of)&(inv.ingested_at<=as_of)]
    credit=tables['credits']
    credit=credit[(credit.issued_at<=as_of)&(credit.ingested_at<=as_of)]
    check('visible_invoice_lines',len(inv),len(ledger),'invoice lines')
    check('gross_invoices',inv.amount_cents.sum(),ledger.amount_cents.sum(),'USD cents')
    matched_credit=credit[credit.invoice_line_id.isin(inv.invoice_line_id)]
    check('applied_credit_amount',matched_credit.amount_cents.sum(),ledger.credited_cents.sum(),'USD cents')
    unmatched_invoice=ledger[~ledger.commitment_id.isin(roots.commitment_id)]
    unmatched_credit=credit[~credit.invoice_line_id.isin(inv.invoice_line_id)]
    source_net=inv.amount_cents.sum()-credit.amount_cents.sum()
    modeled_net=fact.net_invoiced_cents.sum()+unmatched_invoice.net_invoiced_cents.sum()-unmatched_credit.amount_cents.sum()
    check('full_ledger_net_including_quarantine',source_net,modeled_net,'USD cents')
    check('matched_billing_bridge',fact.gross_invoiced_cents.sum()-fact.credited_cents.sum(),fact.net_invoiced_cents.sum(),'USD cents')
    check('expected_to_billed_bridge',fact.expected_billable_cents.sum()+fact.overbilled_cents.sum()-fact.underbilled_cents.sum(),fact.net_invoiced_cents.sum(),'USD cents')
    report=pd.DataFrame(rows)
    if report.status.ne('MATCH').any():
        raise ValueError('Source reconciliation failed: '+','.join(report.loc[report.status.ne('MATCH'),'control']))
    return report


def evaluate_oracle(fact,exceptions,expected_roots,expected_flags):
    merged=fact.merge(expected_roots,on='commitment_id',validate='one_to_one')
    assert len(merged)==len(fact)==len(expected_roots)
    for actual,expected in [('delivered','expected_delivered'),('original_delivered','expected_original_delivery'),
        ('expected_billable_cents','expected_billable_cents'),('net_invoiced_cents','expected_net_invoiced_cents')]:
        if actual==expected:
            a,b=actual+'_x',expected+'_y'
        else:
            a,b=actual,expected
        if merged[a].ne(merged[b]).any():
            raise AssertionError(f'Synthetic oracle disagreement: {actual}')
    keys=['exception_type','entity_type','entity_id']
    actual=set(map(tuple,exceptions[keys].astype(str).to_numpy()))
    expected=set(map(tuple,expected_flags[keys].astype(str).to_numpy()))
    tp=len(actual&expected);fp=len(actual-expected);fn=len(expected-actual)
    result={'scope':'Known injected synthetic defects at final observation cutoff only',
        'expected_exceptions':len(expected),'detected_exceptions':len(actual),
        'true_positives':tp,'false_positives':fp,'false_negatives':fn,
        'precision':tp/(tp+fp) if tp+fp else None,'recall':tp/(tp+fn) if tp+fn else None,
        'commitment_oracle':'MATCH','unexpected':sorted(actual-expected)[:20], 'missed':sorted(expected-actual)[:20]}
    if fp or fn:
        raise AssertionError(str(result))
    return result
