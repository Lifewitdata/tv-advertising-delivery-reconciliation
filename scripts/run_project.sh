#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python -m tvads.pipeline
python -m scripts.prepare_postgres
node scripts/verify_postgres.mjs
python -m scripts.execute_notebooks
python -m pytest -q
python -m scripts.package_outputs
