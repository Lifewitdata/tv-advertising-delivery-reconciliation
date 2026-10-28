"""Seeded synthetic contracts and event ledgers, with independent test oracles.

Rules are invented, explicit case-study assumptions, not real TV market terms.
Amounts are integer USD cents. Oracle files never enter analytical SQL/models.
"""
import json
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

MARKETS = [
    ('New York', 'America/New_York'), ('Boston', 'America/New_York'),
    ('Chicago', 'America/Chicago'), ('Dallas', 'America/Chicago'),
    ('Denver', 'America/Denver'), ('Phoenix', 'America/Phoenix'),
    ('Los Angeles', 'America/Los_Angeles'), ('Seattle', 'America/Los_Angeles'),
]
DAYPART_HOURS = {'Morning': [7, 9, 11], 'Daytime': [13, 15, 17],
                 'Prime': [19, 20, 21], 'Overnight': [0, 1, 23]}
TABLES = ['advertisers', 'campaigns', 'stations', 'booking_lines', 'commitments',
          'scheduled_spots', 'airing_logs', 'invoice_lines', 'credits']


def stamp(value):
    value = pd.Timestamp(value)
    if value.tzinfo is None:
        value = value.tz_localize('UTC')
    return value.tz_convert('UTC').strftime('%Y-%m-%dT%H:%M:%SZ')


def generate(config):
    rng = np.random.default_rng(config['seed'])
    n, na, nc, ns = (config[k] for k in ['n_commitments', 'n_advertisers', 'n_campaigns', 'n_stations'])
    if n < nc * 2 or ns < 4 or na < 2:
        raise ValueError('Use at least two commitments per campaign, four stations and two advertisers')
    advertiser = [{'advertiser_id': i, 'advertiser_name': f'Synthetic advertiser {i}',
        'industry': ['Retail', 'Travel', 'Services', 'Consumer goods'][i % 4]} for i in range(1, na+1)]
    stations = []
    for i in range(1, ns+1):
        market, tz = MARKETS[(i-1) % len(MARKETS)]
        stations.append({'station_id': i, 'station_name': f'Synthetic station {i}', 'market': market,
                         'timezone': tz, 'delivery_partner': f'Partner {(i-1)%4+1}'})
    campaigns, bookings = [], []
    start, end = pd.Timestamp(config['start_date']), pd.Timestamp(config['end_date'])
    for i in range(1, nc+1):
        first = start + pd.Timedelta(days=int(rng.integers(0, 135)))
        last = min(first + pd.Timedelta(days=int(rng.integers(21, 47))), end)
        campaigns.append({'campaign_id': i, 'advertiser_id': (i-1) % na+1,
            'campaign_name': f'Synthetic campaign {i}', 'start_date': first.strftime('%Y-%m-%d'),
            'end_date': last.strftime('%Y-%m-%d'), 'creative_id': f'CR{i:04d}'})
        for j in range(3):
            sid = int(rng.integers(1, ns+1))
            duration = int(rng.choice([30, 60], p=[0.8, 0.2]))
            part = list(DAYPART_HOURS)[int(rng.integers(4))]
            rate = int(rng.integers(5000, 25001)) * (2 if duration == 60 else 1)
            bookings.append({'booking_line_id': f'B{i:04d}-{j}', 'campaign_id': i,
                'station_id': sid, 'daypart': part, 'duration_seconds': duration,
                'unit_rate_cents': rate, 'currency': 'USD'})
    campaign_map = {x['campaign_id']: x for x in campaigns}
    station_map = {x['station_id']: x for x in stations}
    commitments, schedules, logs, invoices, credits = [], [], [], [], []
    truth_roots, truth_flags = [], []

    def flag(kind, entity_type, entity_id):
        truth_flags.append({'exception_type': kind, 'entity_type': entity_type, 'entity_id': str(entity_id)})

    def slot(slot_id, root, booking, when, is_makegood=0, replaces=''):
        return {'scheduled_spot_id': slot_id, 'commitment_id': root, 'station_id': booking['station_id'],
            'scheduled_at': stamp(when), 'window_start': stamp(when-timedelta(minutes=5)),
            'window_end': stamp(when+timedelta(minutes=15)), 'duration_seconds': booking['duration_seconds'],
            'creative_id': campaign_map[booking['campaign_id']]['creative_id'],
            'is_makegood': is_makegood, 'replaces_spot_id': replaces}

    def airing(schedule, event_id, when, mode='normal'):
        payload = {'source_event_id': event_id, 'scheduled_spot_id': schedule['scheduled_spot_id'],
            'station_id': schedule['station_id'], 'aired_at': stamp(when),
            'duration_seconds': schedule['duration_seconds'], 'creative_id': schedule['creative_id']}
        if mode == 'off_window':
            payload['aired_at'] = stamp(when + timedelta(minutes=90))
        if mode == 'wrong_creative':
            payload['creative_id'] = 'CR-WRONG'
        if mode == 'wrong_duration':
            payload['duration_seconds'] += 15
        ingest = pd.Timestamp(payload['aired_at']) + pd.Timedelta(hours=int(rng.choice([1, 3, 12, 72], p=[0.4,0.3,0.2,0.1])))
        record = {**payload, 'ingestion_id': f'L{len(logs)+1:07d}', 'ingested_at': stamp(ingest)}
        logs.append(record)
        if mode in ['off_window', 'wrong_creative', 'wrong_duration']:
            flag(mode, 'source_event', event_id)
        return record

    def invoice(root, payer, rate, quantity, issued):
        record = {'invoice_line_id': f'I{len(invoices)+1:07d}', 'invoice_id': f'INV{len(invoices)//5+1:06d}',
            'commitment_id': root, 'advertiser_id': payer, 'unit_rate_cents': int(rate),
            'quantity': quantity, 'amount_cents': int(rate)*quantity,
            'issued_at': stamp(issued), 'ingested_at': stamp(issued+timedelta(hours=6))}
        invoices.append(record)
        return record

    # Ensure every campaign has commitments before adding random allocations.
    allocated = np.concatenate([np.arange(nc*3) % len(bookings), rng.integers(0, len(bookings), n-nc*3)]) if n >= nc*3 else np.arange(n) % len(bookings)
    for idx, bidx in enumerate(allocated):
        booking = bookings[int(bidx)]
        campaign = campaign_map[booking['campaign_id']]
        station = station_map[booking['station_id']]
        first, last = pd.Timestamp(campaign['start_date']), pd.Timestamp(campaign['end_date'])
        day = first + pd.Timedelta(days=int(rng.integers(0, (last-first).days+1)))
        hour = int(rng.choice(DAYPART_HOURS[booking['daypart']]))
        local = datetime(day.year, day.month, day.day, hour, 20, tzinfo=ZoneInfo(station['timezone']))
        when = pd.Timestamp(local).tz_convert('UTC').to_pydatetime()
        root = f'C{idx+1:07d}'
        cancelled = int(rng.random() < 0.03)
        due = when + timedelta(minutes=15)
        commitments.append({'commitment_id': root, 'booking_line_id': booking['booking_line_id'],
            'cancelled': cancelled, 'due_at': stamp(due),
            'evidence_due_at': stamp(due+timedelta(hours=config['log_grace_hours']))})
        original = slot(root+'-O', root, booking, when)
        schedules.append(original)
        # Explicit simulated relationships. These are not empirical industry effects.
        defect_logit = -3.25 + 0.85*(booking['daypart']=='Overnight') + 0.5*(booking['duration_seconds']==60) + 0.9*(booking['station_id']%4==0)
        defect = rng.random() < 1/(1+np.exp(-defect_logit))
        mode = str(rng.choice(['missing','off_window','wrong_creative','wrong_duration'], p=[0.55,0.25,0.1,0.1])) if defect else 'normal'
        if not defect:
            mode = str(rng.choice(['normal','replay','duplicate_airing','conflict'], p=[0.96,0.02,0.015,0.005]))
        if cancelled:
            mode = 'cancelled_airing' if rng.random() < 0.15 else 'cancelled'
        original_valid = mode in ['normal','replay','duplicate_airing'] and not cancelled
        delivered = original_valid
        if mode not in ['missing','cancelled']:
            event = airing(original, f'E{idx+1:07d}', when, mode)
            if mode == 'replay':
                logs.append({**event, 'ingestion_id': f'L{len(logs)+1:07d}',
                             'ingested_at': stamp(pd.Timestamp(event['ingested_at'])+timedelta(hours=1))})
                flag('log_replay','source_event',event['source_event_id'])
            if mode == 'conflict':
                logs.append({**event, 'ingestion_id': f'L{len(logs)+1:07d}',
                             'aired_at': stamp(when+timedelta(seconds=1)),
                             'ingested_at': stamp(pd.Timestamp(event['ingested_at'])+timedelta(hours=1))})
                flag('conflicting_log','source_event',event['source_event_id'])
            if mode == 'duplicate_airing':
                airing(original, f'E{idx+1:07d}-D', when+timedelta(seconds=10))
                flag('duplicate_airing','scheduled_spot',original['scheduled_spot_id'])
            if mode == 'cancelled_airing':
                flag('cancelled_airing','source_event',event['source_event_id'])
        makegood = mode in ['missing','off_window','wrong_creative','wrong_duration'] and not cancelled and rng.random() < 0.55
        if makegood:
            replacement_time=(pd.Timestamp(when).tz_convert(station['timezone'])+pd.DateOffset(days=int(rng.integers(1,config['makegood_grace_days']+1)))).to_pydatetime()
            replacement = slot(root+'-M', root, booking, replacement_time, 1, original['scheduled_spot_id'])
            schedules.append(replacement)
            airing(replacement, f'E{idx+1:07d}-M', pd.Timestamp(replacement['scheduled_at']).to_pydatetime())
            delivered = True
        if not cancelled and not delivered:
            flag('undelivered_commitment','commitment',root)
        expected = booking['unit_rate_cents'] if delivered and not cancelled else 0
        issued = when+timedelta(days=int(rng.integers(9,12)))
        ledger_net, line_count = 0, 0
        payer = campaign['advertiser_id']
        if expected:
            billing = str(rng.choice(['correct','unbilled','wrong_rate','duplicate','quantity','wrong_advertiser','corrected_rate'], p=[0.78,0.06,0.05,0.04,0.025,0.02,0.025]))
            if billing != 'unbilled':
                rate = booking['unit_rate_cents'] + (1500 if billing in ['wrong_rate','corrected_rate'] else 0)
                quantity = 2 if billing == 'quantity' else 1
                actual_payer = payer % na+1 if billing == 'wrong_advertiser' else payer
                line = invoice(root, actual_payer, rate, quantity, issued)
                ledger_net += line['amount_cents']; line_count += 1
                if rate != booking['unit_rate_cents']:
                    flag('rate_mismatch','invoice_line',line['invoice_line_id'])
                if quantity != 1:
                    flag('quantity_mismatch','invoice_line',line['invoice_line_id'])
                if actual_payer != payer:
                    flag('advertiser_mismatch','invoice_line',line['invoice_line_id'])
                if billing == 'duplicate':
                    duplicate = invoice(root,payer,rate,1,issued+timedelta(seconds=1))
                    ledger_net += duplicate['amount_cents']; line_count += 1
                    flag('duplicate_charge','invoice_line',duplicate['invoice_line_id'])
                if billing == 'corrected_rate':
                    credits.append({'credit_id': f'K{len(credits)+1:06d}', 'invoice_line_id': line['invoice_line_id'],
                        'amount_cents':1500,'issued_at':stamp(issued+timedelta(days=1)),
                        'ingested_at':stamp(issued+timedelta(days=1,hours=2)),'reason':'Synthetic rate correction'})
                    ledger_net -= 1500
        elif rng.random() < 0.20:
            line = invoice(root,payer,booking['unit_rate_cents'],1,issued)
            ledger_net += line['amount_cents']; line_count += 1
        if expected > 0 and line_count == 0:
            flag('unbilled_delivery','commitment',root)
        if expected == 0 and ledger_net > 0:
            flag('billed_without_delivery','commitment',root)
        if ledger_net > expected:
            flag('overbilled','commitment',root)
        if ledger_net < expected:
            flag('underbilled','commitment',root)
        truth_roots.append({'commitment_id':root,'expected_delivered':int(delivered and not cancelled),
            'expected_original_delivery':int(original_valid),'expected_billable_cents':expected,
            'expected_net_invoiced_cents':ledger_net,'injected_delivery_mode':mode})
    # Known orphan records test quarantine and monetary controls explicitly.
    orphan = dict(logs[0]); orphan.update(ingestion_id=f'L{len(logs)+1:07d}',source_event_id='E-UNMATCHED',scheduled_spot_id='S-UNKNOWN')
    logs.append(orphan); flag('unmatched_schedule','source_event','E-UNMATCHED')
    orphan_invoice = invoice('C-UNKNOWN',1,12345,1,pd.Timestamp('2026-06-01',tz='UTC').to_pydatetime())
    flag('unmatched_invoice','invoice_line',orphan_invoice['invoice_line_id'])
    credits.append({'credit_id':f'K{len(credits)+1:06d}','invoice_line_id':'I-UNKNOWN','amount_cents':1000,
        'issued_at':'2026-06-02T00:00:00Z','ingested_at':'2026-06-02T01:00:00Z','reason':'Synthetic orphan credit'})
    flag('unmatched_credit','credit',credits[-1]['credit_id'])
    frames = {name:pd.DataFrame(rows) for name,rows in zip(TABLES,[advertiser,campaigns,stations,bookings,commitments,schedules,logs,invoices,credits])}
    return frames, pd.DataFrame(truth_roots), pd.DataFrame(truth_flags).drop_duplicates()


def write(config, output):
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    tables, roots, flags=generate(config)
    for name,frame in tables.items():
        frame.to_csv(out/f'{name}.csv',index=False,lineterminator='\n')
    oracle=out.parent/'oracles';oracle.mkdir(exist_ok=True)
    roots.to_csv(oracle/'expected_commitments.csv',index=False)
    flags.to_csv(oracle/'expected_exceptions.csv',index=False)
    (out/'manifest.json').write_text(json.dumps({'synthetic':True,'seed':config['seed'],
        'final_as_of':config['final_as_of'],'currency':'USD','amount_unit':'cents',
        'rows':{k:len(v) for k,v in tables.items()}},indent=2)+'\n')
    return tables, roots, flags
