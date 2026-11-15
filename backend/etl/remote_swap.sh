#!/usr/bin/env bash
# Runs ON the server: backup live DB, swap data tables from new_data.db, restart. Service is always restarted.
set -uo pipefail
D=/opt/fieldshift/data
cd /opt/fieldshift/backend
trap 'systemctl start fieldshift' EXIT
systemctl stop fieldshift
python3 - <<'PY'
import sqlite3
s = sqlite3.connect("/opt/fieldshift/data/fieldshift.db")
d = sqlite3.connect("/opt/fieldshift/data/fieldshift.db.bak")
s.backup(d); d.close(); s.close()
print("backup ok")
PY
chown fieldshift:fieldshift "$D/fieldshift.db.bak" "$D/new_data.db"
if sudo -u fieldshift .venv/bin/python -m etl.swap_data "$D/new_data.db"; then
  rm -f "$D/new_data.db"
  echo "swap ok"
else
  echo "SWAP FAILED: restoring backup" >&2
  cp -p "$D/fieldshift.db.bak" "$D/fieldshift.db"
  rm -f "$D/fieldshift.db-wal" "$D/fieldshift.db-shm"
fi
