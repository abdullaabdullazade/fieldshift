#!/usr/bin/env bash
# Build the frontend (if needed) and serve API + site on http://127.0.0.1:8077
# Optional env: DEEPSEEK_API_KEY (AI chat), PORT, HOST
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d backend/.venv ]; then
  uv venv -q backend/.venv
  uv pip install -q --python backend/.venv/bin/python -r backend/requirements.txt
fi
if [ ! -f data/fieldshift.db ]; then
  # the Kür salt-water module runs from data/kur/*.json; the legacy crop/climate pages need ./refresh_data.sh
  echo "No database yet: starting with empty tables (run ./refresh_data.sh for the full crop/climate dataset)" >&2
fi
if [ ! -d frontend/dist ] || [ -n "$(find frontend/src -newer frontend/dist/index.html -print -quit)" ]; then
  (cd frontend && npm install --silent && npx vite build)
fi
cd backend
if [ -f .env ]; then set -a; . ./.env; set +a; fi   # DEEPSEEK_API_KEY etc.
exec .venv/bin/uvicorn app.main:app --host "${HOST:-127.0.0.1}" --port "${PORT:-8077}"
