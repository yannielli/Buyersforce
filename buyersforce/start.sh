#!/usr/bin/env bash
# Seed the database only if it doesn't already exist, so real data isn't
# wiped on every container restart/redeploy -- only on a genuinely fresh
# database. DB_PATH should point at a persistent volume mount in production
# (e.g. /data/buyersforce.db) so it survives redeploys; it falls back to a
# local file next to this script otherwise.
set -e
DB_FILE="${DB_PATH:-buyersforce.db}"
if [ ! -f "$DB_FILE" ]; then
  echo "No database found at $DB_FILE -- seeding..."
  python3 seed.py
fi
exec gunicorn app:app --bind "0.0.0.0:${PORT:-5055}" --workers 2 --threads 4 --timeout 60
