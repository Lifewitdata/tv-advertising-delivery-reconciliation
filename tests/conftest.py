import json
from pathlib import Path
import pytest
from tvads.generate import generate
from tvads.warehouse import build

@pytest.fixture(scope='session')
def config():
    value=json.loads(Path('config/project.json').read_text())
    value.update(n_commitments=1500,n_campaigns=12,n_advertisers=4,n_stations=8)
    return value

@pytest.fixture(scope='session')
def generated(config):
    return generate(config)

@pytest.fixture(scope='session')
def tables(generated):
    return generated[0]

@pytest.fixture(scope='session')
def db(tables,config):
    connection=build(tables,config['final_as_of'])
    yield connection
    connection.close()
