#!/usr/bin/env bash
# NAM v2 backend quickstart: one command on the reference laptop.
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then python3 -m venv .venv; fi
source .venv/bin/activate
pip install -q -r requirements.txt
[ -f data/seeds/gazetteer_curated.json ] || python scripts/make_seeds.py
[ -f data/seeds/demo_grid.npz ] || python scripts/make_demo_grid.py
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${NAM_PORT:-8000}"
