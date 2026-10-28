import pandas as pd
import pytest
from tvads.controls import evaluate_oracle,reconcile
from tvads.warehouse import query,build,analytical_queries
from tvads.generate import stamp

def test_all_final_commitments_and_exception_flags_match_independent_oracle(db,generated):
    result=evaluate_oracle(query(db,'v_commitment_finance'),query(db,'v_exceptions'),generated[1],generated[2])
    assert result['precision']==result['recall']==1

def test_source_controls_include_orphans_and_credits(db,tables,config):
    report=reconcile(tables,config['final_as_of'],query(db,'v_commitment_finance'),query(db,'v_airing_review'),query(db,'v_invoice_ledger'),db)
    assert len(report)==10 and report.difference.eq(0).all()

def test_reconciliation_detects_dropped_commitment(db,tables,config):
    with pytest.raises(ValueError,match='reconciliation'):
        reconcile(tables,config['final_as_of'],query(db,'v_commitment_finance').iloc[1:],query(db,'v_airing_review'),query(db,'v_invoice_ledger'),db)

def test_replays_are_deduplicated_conflicts_quarantined(db):
    data=query(db,'v_airing_review')
    assert data.source_event_id.is_unique
    replay=data[data.raw_record_count.gt(1)&data.variant_count.eq(1)]
    conflicts=data[data.variant_count.gt(1)]
    assert len(replay)>0 and len(conflicts)>0
    assert conflicts.airing_status.eq('conflicting_log').all()

def test_makegoods_never_inflate_commitment_grain_or_value(db,tables):
    fact=query(db,'v_commitment_finance')
    assert fact.commitment_id.is_unique and len(fact)==len(tables['commitments'])
    recovered=fact[fact.original_delivered.eq(0)&fact.makegood_delivered.eq(1)]
    assert len(recovered)>0
    assert recovered.expected_billable_cents.eq(recovered.unit_rate_cents).all()

def test_duplicate_valid_airings_still_bill_one_unit(db):
    fact=query(db,'v_commitment_finance')
    dup=fact[fact.qualifying_events.gt(1)]
    assert len(dup)>0 and dup.expected_billable_cents.eq(dup.unit_rate_cents).all()

def test_cancelled_commitments_cannot_be_due_or_billable(db):
    fact=query(db,'v_commitment_finance');cancelled=fact[fact.cancelled.eq(1)]
    assert not cancelled.due_commitment.any() and not cancelled.expected_billable_cents.any()
    assert not cancelled.delivered.any()

def test_rate_corrected_by_credit_keeps_audit_flag_without_net_exposure(db):
    rows=pd.read_sql_query("SELECT i.invoice_line_id,f.billing_difference_cents FROM v_invoice_ledger i JOIN v_commitment_finance f ON f.commitment_id=i.commitment_id WHERE i.credited_cents>0",db)
    assert len(rows)>0 and rows.billing_difference_cents.eq(0).all()
    flags=query(db,'v_exceptions')
    assert set(rows.invoice_line_id).issubset(set(flags.loc[flags.exception_type.eq('rate_mismatch'),'entity_id']))

def test_late_arriving_valid_log_resolves_apparent_underdelivery(tables,generated):
    modes=generated[1].set_index('commitment_id').injected_delivery_mode
    slots=tables['scheduled_spots'].set_index('scheduled_spot_id')
    source=tables['airing_logs']
    delay=pd.to_datetime(source.ingested_at,utc=True)-pd.to_datetime(source.aired_at,utc=True)
    selected=source[delay.gt(pd.Timedelta(hours=48))].copy()
    selected['root']=selected.scheduled_spot_id.map(slots.commitment_id)
    row=selected[selected.root.map(modes).eq('normal')].iloc[0]
    before=stamp(pd.Timestamp(row.ingested_at)-pd.Timedelta(seconds=1))
    after=row.ingested_at
    a=build(tables,before);b=build(tables,after)
    try:
        av=query(a,'v_commitment_finance').set_index('commitment_id').loc[row.root]
        bv=query(b,'v_commitment_finance').set_index('commitment_id').loc[row.root]
        assert av.delivered==0 and bv.delivered==1
    finally:a.close();b.close()

def test_future_events_and_invoice_rows_are_not_visible(tables):
    db=build(tables,'2026-01-01T00:00:00Z')
    try:
        assert query(db,'v_visible_airings').empty
        assert query(db,'v_visible_invoices').empty
    finally:db.close()

def test_due_boundary_is_inclusive(tables):
    due=tables['commitments'].loc[tables['commitments'].cancelled.eq(0),'due_at'].min()
    db=build(tables,due)
    try:
        fact=query(db,'v_commitment_finance')
        assert fact.loc[fact.due_at.eq(due)&fact.cancelled.eq(0),'due_commitment'].eq(1).all()
    finally:db.close()


@pytest.mark.parametrize('boundary,offset,expected',[('window_start',0,'qualifying'),('window_end',0,'qualifying'),('window_start',-1,'off_window'),('window_end',1,'off_window')])
def test_airing_window_boundaries(tables,generated,boundary,offset,expected):
    data={k:v.copy() for k,v in tables.items()}
    root=generated[1].loc[generated[1].injected_delivery_mode.eq('normal'),'commitment_id'].iloc[0]
    schedule=data['scheduled_spots'].loc[data['scheduled_spots'].commitment_id.eq(root)].iloc[0]
    row=data['airing_logs'].index[data['airing_logs'].scheduled_spot_id.eq(schedule.scheduled_spot_id)][0]
    data['airing_logs'].loc[row,'aired_at']=stamp(pd.Timestamp(schedule[boundary])+pd.Timedelta(seconds=offset))
    data['airing_logs'].loc[row,'ingested_at']=stamp(pd.Timestamp(data['airing_logs'].loc[row,'aired_at'])+pd.Timedelta(hours=1))
    connection=build(data,'2026-07-15T00:00:00Z')
    try:
        record=query(connection,'v_airing_review').set_index('source_event_id').loc[data['airing_logs'].loc[row,'source_event_id']]
        assert record.airing_status==expected
    finally:connection.close()

def test_each_analytical_query_executes(db):
    for sql in analytical_queries():
        result=pd.read_sql_query(sql,db)
        assert isinstance(result,pd.DataFrame)
