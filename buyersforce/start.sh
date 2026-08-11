#!/usr/bin/env bash
# seed.py itself checks whether a database already exists at DB_PATH and
# skips seeding if so, so real data isn't wiped on every container
# restart/redeploy -- only a genuinely fresh database gets seeded. DB_PATH
# should point at a persistent volume mount in production (e.g.
# /data/buyersforce.db) so it survives redeploys; it falls back to a local
# file next to this script otherwise. The check lives in Python (not here)
# so it reliably sees the same DB_PATH the app itself uses.
set -e
python3 seed.py
exec gunicorn app:app --bind "0.0.0.0:${PORT:-5055}" --workers 2 --threads 4 --timeout 60

