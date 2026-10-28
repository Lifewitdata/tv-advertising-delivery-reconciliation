"""Generate local verification inputs. The test oracle is deliberately excluded."""
import json
from pathlib import Path
from tvads.pipeline import current_output
from tvads.warehouse import read_raw
import pandas as pd

current=current_output()
tables=read_raw(current/'raw')
payload={'as_of':json.loads((current/'reports/summary.json').read_text())['as_of'],
    'tables':{name:frame.to_dict('records') for name,frame in tables.items()},
    'expected_fact':pd.read_parquet(current/'fact_commitments.parquet').to_dict('records')}
Path('data/postgres_input.json').write_text(json.dumps(payload,allow_nan=False))
