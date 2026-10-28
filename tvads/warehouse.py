"""Validated source contracts and portable SQLite/PostgreSQL analytical models."""
import json
import sqlite3
from pathlib import Path

import pandas as pd

from tvads.generate import TABLES,stamp

ROOT=Path(__file__).resolve().parents[1]
KEYS={name:key for name,key in zip(TABLES,['advertiser_id','campaign_id','station_id','booking_line_id',
    'commitment_id','scheduled_spot_id','ingestion_id','invoice_line_id','credit_id'])}
SQL_FILES=['10_delivery_models.sql','20_billing_models.sql']


class ContractError(ValueError):
    pass


def schema_columns():
    with sqlite3.connect(':memory:') as db:
        db.executescript((ROOT/'sql/00_schema.sql').read_text())
        return {name:[r[1] for r in db.execute(f'PRAGMA table_info({name})')] for name in TABLES}


def validate(tables,config):
    expected=schema_columns()
    report={'schema':'PASS','synthetic':True,'tables':{}}
    for name in TABLES:
        if name not in tables or set(tables[name].columns)!=set(expected[name]):
            raise ContractError(f'{name}: unexpected/missing source columns')
        frame=tables[name]
        if (frame.empty and name not in ['airing_logs','invoice_lines','credits']) or frame.isna().any().any():
            raise ContractError(f'{name}: empty table or null source values')
        if frame[KEYS[name]].duplicated().any():
            raise ContractError(f'{name}: duplicate primary key')
        report['tables'][name]={'rows':len(frame),'primary_key':KEYS[name]}
        for col in frame.columns:
            if col.endswith('_at') or col in ['window_start','window_end']:
                values=frame[col].astype(str)
                parsed=pd.to_datetime(values,errors='coerce',utc=True,format='ISO8601')
                if parsed.isna().any() or not values.str.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$').all():
                    raise ContractError(f'{name}.{col}: expected canonical UTC timestamps')
    for child,key,parent,parentkey in [
        ('campaigns','advertiser_id','advertisers','advertiser_id'),
        ('booking_lines','campaign_id','campaigns','campaign_id'),
        ('booking_lines','station_id','stations','station_id'),
        ('commitments','booking_line_id','booking_lines','booking_line_id'),
        ('scheduled_spots','commitment_id','commitments','commitment_id'),
        ('scheduled_spots','station_id','stations','station_id'),
        ('invoice_lines','advertiser_id','advertisers','advertiser_id')]:
        if not tables[child][key].isin(tables[parent][parentkey]).all():
            raise ContractError(f'{child}.{key}: orphan contract key')
    if not tables['booking_lines'].currency.eq('USD').all():
        raise ContractError('Only USD contracts are supported')
    for name,cols in [('booking_lines',['unit_rate_cents','duration_seconds']),
                      ('scheduled_spots',['duration_seconds']),('invoice_lines',['quantity','unit_rate_cents','amount_cents']),
                      ('credits',['amount_cents'])]:
        for col in cols:
            values=pd.to_numeric(tables[name][col],errors='coerce')
            if values.isna().any() or (values<=0).any() or values.mod(1).ne(0).any():
                raise ContractError(f'{name}.{col}: expected positive integers')
    for name,col in [('commitments','cancelled'),('scheduled_spots','is_makegood')]:
        if not tables[name][col].isin([0,1]).all():
            raise ContractError(f'{name}.{col}: expected 0 or 1')
    for name,eventtime in [('airing_logs','aired_at'),('invoice_lines','issued_at'),('credits','issued_at')]:
        if (tables[name].ingested_at < tables[name][eventtime]).any():
            raise ContractError(f'{name}: ingestion precedes event')
    inv=tables['invoice_lines']
    if (inv.amount_cents!=inv.quantity*inv.unit_rate_cents).any():
        raise ContractError('Invoice amount does not equal quantity times rate')
    slots=tables['scheduled_spots']
    if ((slots.window_start>slots.scheduled_at)|(slots.scheduled_at>slots.window_end)).any():
        raise ContractError('Invalid airing window')
    originals=slots[slots.is_makegood.eq(0)]
    if originals.commitment_id.duplicated().any() or set(originals.commitment_id)!=set(tables['commitments'].commitment_id):
        raise ContractError('Exactly one original schedule per commitment is required')
    campaign_dates=tables['campaigns']
    start=pd.to_datetime(campaign_dates.start_date,errors='coerce')
    end=pd.to_datetime(campaign_dates.end_date,errors='coerce')
    if start.isna().any() or end.isna().any() or (start>end).any():
        raise ContractError('Invalid campaign flight dates')
    windows=pd.to_datetime(slots.window_end,utc=True)-pd.to_datetime(slots.window_start,utc=True)
    if not windows.eq(pd.Timedelta(minutes=20)).all():
        raise ContractError('Expected approved 20-minute airing window')
    due=tables['commitments'].merge(originals[['commitment_id','window_end']],on='commitment_id',validate='one_to_one')
    if due.due_at.ne(due.window_end).any():
        raise ContractError('Original window end must equal commitment due time')
    grace=pd.to_datetime(due.evidence_due_at,utc=True)-pd.to_datetime(due.due_at,utc=True)
    if not grace.eq(pd.Timedelta(hours=config['log_grace_hours'])).all():
        raise ContractError('Inconsistent source-log grace period')
    c=tables['commitments'].merge(tables['booking_lines'],on='booking_line_id',validate='many_to_one')
    c=c.merge(tables['campaigns'][['campaign_id','creative_id']],on='campaign_id',validate='many_to_one')
    linked=slots.merge(c[['commitment_id','station_id','creative_id','duration_seconds']],on='commitment_id',suffixes=('','_contract'),validate='many_to_one')
    for col in ['station_id','creative_id','duration_seconds']:
        if linked[col].ne(linked[col+'_contract']).any():
            raise ContractError(f'Schedule violates contracted {col}')
    local=slots.merge(c[['commitment_id','daypart','campaign_id']],on='commitment_id',validate='many_to_one')
    local=local.merge(tables['stations'][['station_id','timezone']],on='station_id',validate='many_to_one')
    local=local.merge(campaign_dates[['campaign_id','start_date','end_date']],on='campaign_id',validate='many_to_one')
    for timezone,group in local.groupby('timezone'):
        try:
            times=pd.to_datetime(group.scheduled_at,utc=True).dt.tz_convert(timezone)
        except Exception as exc:
            raise ContractError('Invalid station timezone') from exc
        hour=times.dt.hour
        valid=((group.daypart.eq('Morning')&hour.between(6,11))|
            (group.daypart.eq('Daytime')&hour.between(12,17))|
            (group.daypart.eq('Prime')&hour.between(18,22))|
            (group.daypart.eq('Overnight')&((hour>=23)|(hour<=5))))
        if not valid.all():
            raise ContractError('Scheduled spot violates local station daypart')
        original=group.is_makegood.eq(0)
        dates=times.dt.strftime('%Y-%m-%d')
        if (original&((dates<group.start_date)|(dates>group.end_date))).any():
            raise ContractError('Original spot is outside its local campaign flight')
    replacements=slots[slots.is_makegood.eq(1)]
    parent=replacements.merge(originals[['scheduled_spot_id','commitment_id','scheduled_at']],
        left_on='replaces_spot_id',right_on='scheduled_spot_id',how='left',suffixes=('','_parent'),validate='many_to_one')
    if parent.scheduled_spot_id_parent.isna().any() or parent.commitment_id.ne(parent.commitment_id_parent).any():
        raise ContractError('Replacement must refer to its own original commitment')
    if len(parent):
        delay=pd.to_datetime(parent.scheduled_at,utc=True)-pd.to_datetime(parent.scheduled_at_parent,utc=True)
        if ((delay<=pd.Timedelta(0))|(delay>pd.Timedelta(days=config['makegood_grace_days']))).any():
            raise ContractError('Replacement is outside the authorized grace period')
    report['quarantine_candidates']={
        'unmatched_schedule_rows':int((~tables['airing_logs'].scheduled_spot_id.isin(slots.scheduled_spot_id)).sum()),
        'unmatched_invoice_rows':int((~inv.commitment_id.isin(tables['commitments'].commitment_id)).sum()),
        'unmatched_credit_rows':int((~tables['credits'].invoice_line_id.isin(inv.invoice_line_id)).sum())}
    return report


def build(tables,as_of,path=':memory:'):
    db=sqlite3.connect(str(path))
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript((ROOT/'sql/00_schema.sql').read_text())
    db.execute('INSERT INTO settings VALUES (?)',(stamp(as_of),))
    columns=schema_columns()
    for name in TABLES:
        ordered=columns[name]
        quoted=','.join('"'+col+'"' for col in ordered)
        placeholders=','.join('?' for _ in ordered)
        db.executemany(f'INSERT INTO {name} ({quoted}) VALUES ({placeholders})',tables[name][ordered].itertuples(index=False,name=None))
    for sql in SQL_FILES:
        db.executescript((ROOT/'sql'/sql).read_text())
    db.commit()
    return db


def query(db,view):
    return pd.read_sql_query('SELECT * FROM '+view,db)


def read_raw(folder):
    return {name:pd.read_csv(Path(folder)/f'{name}.csv',keep_default_na=False) for name in TABLES}


def analytical_queries():
    # These committed statements contain no semicolons inside literals.
    source='\n'.join(line for line in (ROOT/'sql/30_analytical_queries.sql').read_text().splitlines() if not line.lstrip().startswith('--'))
    return [part.strip() for part in source.split(';') if part.strip()]
