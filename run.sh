#!/usr/bin/env bash
# NAM v2 full-stack quickstart: builds client (if npm is available) and starts FastAPI on :8000.
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then python3 -m venv .venv; fi
source .venv/bin/activate
pip install -q -r requirements.txt
[ -f data/seeds/flyovers.json ] || python scripts/make_seeds.py
[ -f data/seeds/demo_grid.npz ] || python scripts/make_demo_grid.py
if command -v npm >/dev/null 2>&1 && [ -d client ] && [ ! -f client/dist/index.html ]; then
  (cd client && npm install --no-audit --no-fund && npm run build)
fi
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${NAM_PORT:-8000}"
