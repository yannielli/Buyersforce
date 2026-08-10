#!/usr/bin/env bash
# Seed the demo database only if it doesn't already exist, so live demo data
# isn't wiped on every container restart -- only on a fresh deploy where the
# filesystem starts empty.
set -e
if [ ! -f "buyersforce.db" ]; then
  echo "No database found -- seeding demo data..."
  python3 seed.py
fi
exec gunicorn app:app --bind "0.0.0.0:${PORT:-5055}" --workers 2 --threads 4 --timeout 60
