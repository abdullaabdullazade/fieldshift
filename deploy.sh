#!/usr/bin/env bash
# Ship code + frontend to the production server (systemd service `fieldshift` + nginx). The live database is NOT overwritten,
# so accounts, reviews and feedback created on the site survive. Pass --with-data to also replace the data tables
# (climate, yields, world layer) from data/fieldshift.db; app tables are kept and a backup is written first.
set -euo pipefail
cd "$(dirname "$0")"
# server and SSH key come from deploy.env (not in git):  FS_HOST=user@host  FS_KEY=~/.ssh/key
[ -f deploy.env ] && . ./deploy.env
KEY="${FS_KEY:?set FS_KEY in deploy.env}"
HOST="${FS_HOST:?set FS_HOST in deploy.env}"
# one SSH connection reused by every step (each new handshake to this server takes ~10 s)
CTL="${XDG_RUNTIME_DIR:-/tmp}/fieldshift-deploy-%C"
SSH="ssh -i $KEY -o BatchMode=yes -o ControlMaster=auto -o ControlPath=$CTL -o ControlPersist=60"
trap '$SSH -O exit "$HOST" 2>/dev/null || true' EXIT
(cd frontend && npx vite build)
rsync -az --delete -e "$SSH" --exclude .venv --exclude __pycache__ --exclude .env backend/app backend/requirements-runtime.txt "$HOST:/opt/fieldshift/backend/"
$SSH "$HOST" 'mkdir -p /opt/fieldshift/backend/etl'
rsync -az -e "$SSH" backend/etl/__init__.py backend/etl/swap_data.py "$HOST:/opt/fieldshift/backend/etl/"
rsync -az --delete -e "$SSH" frontend/dist "$HOST:/opt/fieldshift/frontend/"
rsync -az -e "$SSH" data/regions.geojson data/rayons.json "$HOST:/opt/fieldshift/data/"
rsync -az --delete -e "$SSH" data/geo_web "$HOST:/opt/fieldshift/data/"
rsync -az -e "$SSH" --include='labels_*.npy' --include='grids.json' --include='cm_*.xml' --exclude='*' data/sat/ "$HOST:/opt/fieldshift/data/sat/"
# Kür salt-water module: river geometry, villages and the 2020+ back-test (live state is rebuilt on the server)
$SSH "$HOST" 'mkdir -p /opt/fieldshift/data/kur'
for f in river villages history grace soil; do [ -f "data/kur/$f.json" ] && rsync -az -e "$SSH" "data/kur/$f.json" "$HOST:/opt/fieldshift/data/kur/"; done
if [ "${1:-}" = "--with-data" ]; then
  # swap only the data tables; users, farms, reviews, feedback on the live site are kept (backup taken first)
  tmp=$(mktemp); sqlite3 data/fieldshift.db ".backup '$tmp'"
  rsync -az -e "$SSH" "$tmp" "$HOST:/opt/fieldshift/data/new_data.db"; rm -f "$tmp"
  rsync -az -e "$SSH" backend/etl/remote_swap.sh "$HOST:/opt/fieldshift/backend/etl/"
  $SSH "$HOST" 'bash /opt/fieldshift/backend/etl/remote_swap.sh'
fi
$SSH "$HOST" 'cd /opt/fieldshift/backend && .venv/bin/pip install -q -r requirements-runtime.txt && chown -R fieldshift:fieldshift /opt/fieldshift && systemctl restart fieldshift && sleep 2 && systemctl is-active fieldshift'
