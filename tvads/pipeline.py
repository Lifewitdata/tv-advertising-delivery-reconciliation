"""Run generation, contracts, SQL, reconciliation, analyses and data exports."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

from tvads.generate import write,stamp
from tvads.warehouse import ROOT,validate,build,query
from tvads.controls import reconcile,evaluate_oracle
from tvads.report import export
from tvads.analysis import analyze


def current_output(root=None):
    root=Path(root or ROOT)
    pointer=json.loads((root/'outputs/latest.json').read_text())
    return root/pointer['path']


def run(config_path=None,as_of=None):
    config=json.loads(Path(config_path or ROOT/'config/project.json').read_text())
    cutoff=stamp(as_of or config['final_as_of'])
    if cutoff>config['final_as_of']:
        raise ValueError('Requested cutoff exceeds declared source observation horizon')
    data=ROOT/'data';data.mkdir(exist_ok=True)
    outputs=ROOT/'outputs';outputs.mkdir(exist_ok=True)
    lock=(outputs/'.pipeline.lock').open('a+')
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close();raise RuntimeError('Another refresh is active') from None
    stage=Path(tempfile.mkdtemp(prefix='.stage-',dir=outputs))
    try:
        tables,oracle_roots,oracle_flags=write(config,stage/'raw')
        validation=validate(tables,config)
        db=build(tables,cutoff,stage/'warehouse.sqlite')
        try:
            fact=query(db,'v_commitment_finance');exceptions=query(db,'v_exceptions')
            controls=reconcile(tables,cutoff,fact,query(db,'v_airing_review'),query(db,'v_invoice_ledger'),db)
            oracle=evaluate_oracle(fact,exceptions,oracle_roots,oracle_flags) if cutoff==config['final_as_of'] else {
                'status':'NOT_APPLICABLE','reason':'The independent oracle describes only the final cutoff'}
            summary=export(db,tables,cutoff,stage,controls,oracle)
        finally:
            db.close()
        statistics=analyze(fact,config,stage/'reports')
        hashes={path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted((stage/'raw').glob('*.csv'))}
        manifest={'synthetic':True,'seed':config['seed'],'as_of':cutoff,'source_sha256':hashes,
            'source_rows':{name:len(frame) for name,frame in tables.items()},'validation':validation,
            'statistics':statistics,'dashboard_status':'Deferred by request; Tableau datasets only'}
        (stage/'run_manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n')
        runs=outputs/'runs';runs.mkdir(exist_ok=True)
        final=runs/stage.name.replace('.stage-','run-')
        stage.rename(final)
        pointer=outputs/'latest.next.json'
        pointer.write_text(json.dumps({'path':str(final.relative_to(ROOT)),'as_of':cutoff})+'\n')
        os.replace(pointer,outputs/'latest.json')
        print(json.dumps(summary,indent=2))
        return final
    finally:
        if stage.exists():shutil.rmtree(stage)
        fcntl.flock(lock,fcntl.LOCK_UN);lock.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--config')
    parser.add_argument('--as-of')
    args=parser.parse_args()
    run(args.config,args.as_of)
