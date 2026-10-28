import json
from pathlib import Path
import fcntl
import numpy as np
import pandas as pd
import pytest

from tvads.pipeline import current_output
from tvads.warehouse import build,query
from tvads.controls import reconcile
from tvads.report import export
from tvads.analysis import analyze


def test_failed_refresh_does_not_replace_last_good_pointer(tmp_path,monkeypatch,config):
    import tvads.pipeline as pipeline
    (tmp_path/'outputs/runs/good').mkdir(parents=True)
    (tmp_path/'outputs/latest.json').write_text(json.dumps({'path':'outputs/runs/good'}))
    path=tmp_path/'config.json';path.write_text(json.dumps(config))
    def fail(*args,**kwargs):raise ValueError('source unavailable')
    monkeypatch.setattr(pipeline,'ROOT',tmp_path);monkeypatch.setattr(pipeline,'write',fail)
    with pytest.raises(ValueError,match='source unavailable'):pipeline.run(path)
    assert pipeline.current_output(tmp_path)==tmp_path/'outputs/runs/good'
    assert not list((tmp_path/'outputs').glob('.stage-*'))


def test_overlapping_refresh_is_rejected(tmp_path,monkeypatch,config):
    import tvads.pipeline as pipeline
    (tmp_path/'outputs').mkdir()
    path=tmp_path/'config.json';path.write_text(json.dumps(config))
    monkeypatch.setattr(pipeline,'ROOT',tmp_path)
    with (tmp_path/'outputs/.pipeline.lock').open('a+') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(RuntimeError,match='Another refresh'):pipeline.run(path)


def test_future_cutoff_is_rejected_before_writing(config,tmp_path):
    from tvads.pipeline import run
    path=tmp_path/'config.json';path.write_text(json.dumps(config))
    with pytest.raises(ValueError,match='observation horizon'):run(path,'2027-01-01')


def test_empty_due_population_exports_undefined_rate_not_false_success(tables,config,tmp_path):
    cutoff='2025-12-31T00:00:00Z';db=build(tables,cutoff)
    try:
        fact=query(db,'v_commitment_finance')
        controls=reconcile(tables,cutoff,fact,query(db,'v_airing_review'),query(db,'v_invoice_ledger'),db)
        summary=export(db,tables,cutoff,tmp_path,controls,{'status':'NOT_APPLICABLE'})
        assert summary['due_commitments']==0 and summary['delivery_rate'] is None
        metadata=analyze(fact,config,tmp_path/'reports')
        assert metadata['regression_status'].startswith('SKIPPED')
    finally:db.close()


@pytest.fixture
def current():
    if not Path('outputs/latest.json').exists():pytest.skip('Run the default pipeline for integration assertions')
    return current_output()


def test_published_fact_and_exception_grains(current):
    folder=current/'tableau_ready'
    fact=pd.read_csv(folder/'fact_commitment_delivery_billing.csv')
    airings=pd.read_csv(folder/'fact_airing_review.csv')
    invoices=pd.read_csv(folder/'fact_invoice_ledger.csv')
    exceptions=pd.read_csv(folder/'exception_queue.csv')
    assert fact.commitment_id.is_unique and airings.source_event_id.is_unique and invoices.invoice_line_id.is_unique
    assert not exceptions.duplicated(['exception_type','entity_type','entity_id']).any()
    assert 'injected_delivery_mode' not in fact and 'expected_delivered' not in fact
    assert fact.as_of.nunique()==airings.as_of.nunique()==invoices.as_of.nunique()==1


def test_statistics_are_exploratory_and_finite(current):
    metadata=json.loads((current/'reports/statistics_metadata.json').read_text())
    assert metadata['causal_claim'] is False and metadata['regression_status']=='CONVERGED'
    coefficients=pd.read_csv(current/'reports/adjusted_original_failure_associations.csv')
    assert np.isfinite(coefficients[['odds_ratio','ci_low','ci_high','p_value']]).all().all()
    intervals=pd.read_csv(current/'reports/daypart_intervals.csv')
    assert intervals.ci_low.between(0,1).all() and intervals.ci_high.between(0,1).all()


def test_no_bi_dashboard_or_workbook_is_created(current):
    forbidden={'.twb','.twbx','.pbix','.pbit','.hyper'}
    assert not any(path.suffix.lower() in forbidden for path in Path('.').rglob('*') if 'node_modules' not in path.parts)


def test_report_totals_are_money_bridge_not_summed_exception_flags(current):
    summary=json.loads((current/'reports/summary.json').read_text())
    assert summary['expected_billable_cents']+summary['overbilled_cents']-summary['underbilled_cents']==summary['matched_net_invoiced_cents']
    assert summary['delivered_commitments']==summary['original_deliveries']+summary['makegood_recoveries']
    assert summary['exception_flags']>=summary['distinct_affected_commitments']


def test_optional_postgres_result_parity_and_access_checks(current):
    path=current/'reports/postgres_verification.json'
    if not path.exists():pytest.skip('Run PostgreSQL verification')
    value=json.loads(path.read_text())
    assert value['sqlite_postgres_parity']=='MATCH' and value['analytical_queries_executed']==8
    assert value['raw_invoice_access']==value['report_writes']=='DENIED'


def test_snapshot_keeps_its_exact_input_sources(current):
    import hashlib
    manifest=json.loads((current/'run_manifest.json').read_text())
    for name,digest in manifest['source_sha256'].items():
        assert hashlib.sha256((current/'raw'/name).read_bytes()).hexdigest()==digest


def test_empty_operational_feeds_are_valid_not_healthy_delivery(tables,config):
    from tvads.warehouse import validate
    data={k:v.copy() for k,v in tables.items()}
    for name in ['airing_logs','invoice_lines','credits']:data[name]=data[name].iloc[:0]
    assert validate(data,config)['schema']=='PASS'
    db=build(data,config['final_as_of'])
    try:
        fact=query(db,'v_commitment_finance')
        assert fact.delivered.eq(0).all() and fact.net_invoiced_cents.eq(0).all()
    finally:db.close()
