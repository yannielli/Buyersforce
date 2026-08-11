#!/usr/bin/env bash
# seed.py connects to the PostgreSQL database at DATABASE_URL and checks
# whether the `users` table already has data, skipping the seed step if so
# -- so real data isn't wiped on every restart/redeploy, only a genuinely
# empty database gets seeded.
set -e
python3 seed.py
exec gunicorn app:app --bind "0.0.0.0:${PORT:-5055}" --workers 2 --threads 4 --timeout 60


