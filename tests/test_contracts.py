import pandas as pd
import pytest
from tvads.generate import generate,stamp
from tvads.warehouse import validate,ContractError,analytical_queries

def test_seed_repeats_all_tables_and_oracles(config,generated):
    other=generate(config)
    for name,frame in generated[0].items():pd.testing.assert_frame_equal(frame,other[0][name])
    pd.testing.assert_frame_equal(generated[1],other[1]);pd.testing.assert_frame_equal(generated[2],other[2])

def test_valid_sources_keep_unknown_references_for_investigation(tables,config):
    report=validate(tables,config)
    assert report['quarantine_candidates']=={'unmatched_schedule_rows':1,'unmatched_invoice_rows':1,'unmatched_credit_rows':1}

@pytest.mark.parametrize('case',['missing_column','extra_column','duplicate_pk','bad_time','orphan_booking',
    'negative_money','fractional_money','invoice_arithmetic','unknown_currency','invalid_flag','bad_window','bad_grace','bad_replacement','bad_daypart','bad_flight'])
def test_broken_contracts_fail(tables,config,case):
    data={k:v.copy() for k,v in tables.items()}
    if case=='missing_column':data['airing_logs']=data['airing_logs'].drop(columns='aired_at')
    if case=='extra_column':data['airing_logs']['mystery']=1
    if case=='duplicate_pk':data['invoice_lines'].loc[1,'invoice_line_id']=data['invoice_lines'].loc[0,'invoice_line_id']
    if case=='bad_time':data['airing_logs'].loc[0,'aired_at']='not-a-timestamp'
    if case=='orphan_booking':data['commitments'].loc[0,'booking_line_id']='unknown'
    if case=='negative_money':data['invoice_lines'].loc[0,'amount_cents']=-100
    if case=='fractional_money':data['booking_lines']['unit_rate_cents']=data['booking_lines'].unit_rate_cents.astype(float);data['booking_lines'].loc[0,'unit_rate_cents']=1.5
    if case=='invoice_arithmetic':data['invoice_lines'].loc[0,'amount_cents']+=1
    if case=='unknown_currency':data['booking_lines'].loc[0,'currency']='GBP'
    if case=='invalid_flag':data['commitments'].loc[0,'cancelled']=2
    if case=='bad_window':data['scheduled_spots'].loc[0,'window_end']=data['scheduled_spots'].loc[0,'scheduled_at']
    if case=='bad_grace':data['commitments'].loc[0,'evidence_due_at']=data['commitments'].loc[0,'due_at']
    if case=='bad_replacement':
        ix=data['scheduled_spots'].index[data['scheduled_spots'].is_makegood.eq(1)][0]
        data['scheduled_spots'].loc[ix,'replaces_spot_id']='unknown'
    if case=='bad_daypart':data['booking_lines']['daypart']='Unrecognized'
    if case=='bad_flight':data['campaigns'].loc[0,'end_date']='2025-01-01'
    with pytest.raises(ContractError):validate(data,config)

def test_local_dst_makegood_stays_in_contracted_daypart(config,tables):
    # Contract validation checks original and replacement slots in station local time.
    assert validate(tables,config)['schema']=='PASS'

def test_canonical_timestamp_normalizes_offsets():
    assert stamp('2026-03-08T07:00:00+00:00')=='2026-03-08T07:00:00Z'
    assert stamp('2026-03-08T03:00:00-04:00')=='2026-03-08T07:00:00Z'

def test_analytical_statement_parser_ignores_comment_semicolons():
    assert len(analytical_queries())==8
