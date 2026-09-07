"""
Incremental schema migrations for BuyersForce (PostgreSQL).

schema.sql only ever runs against a brand-new, empty database (seed.py
skips it once real data exists), so a change that needs to reach the
LIVE database has to happen here instead, as an idempotent migration
that's safe to run on every deploy. start.sh runs this once, in a single
process, before gunicorn starts any workers -- so there's no risk of two
workers racing to add the same column.

Every statement below is written to be safe to run repeatedly: CREATE
TABLE/INDEX IF NOT EXISTS, ADD COLUMN IF NOT EXISTS, and a constraint
check that only touches the DB when the constraint actually needs
widening.
"""
import psycopg2

from db import _database_url


def run_migrations():
    con = psycopg2.connect(_database_url())
    con.autocommit = True
    try:
        with con.cursor() as cur:
            _add_contacts_table(cur)
            _add_direct_messaging_columns(cur)
            _widen_thread_type_check(cur)
            _add_thread_reads_table(cur)
    finally:
        con.close()


def _add_contacts_table(cur):
    # A per-user personal address book. A row with contact_user_id set is
    # a fellow BuyersForce member; a row with external_email set instead
    # is someone reached by email who isn't a member (yet). Rows are
    # added automatically the first time two people message each other.
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS contacts (
            id SERIAL PRIMARY KEY,
            owner_user_id INTEGER NOT NULL REFERENCES users(id),
            contact_user_id INTEGER REFERENCES users(id),
            external_name TEXT,
            external_email TEXT,
            created_at TEXT NOT NULL DEFAULT (to_char(now(), 'YYYY-MM-DD HH24:MI:SS'))
        )
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS contacts_owner_contact_uniq
        ON contacts (owner_user_id, contact_user_id)
        WHERE contact_user_id IS NOT NULL
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS contacts_owner_external_email_uniq
        ON contacts (owner_user_id, external_email)
        WHERE contact_user_id IS NULL AND external_email IS NOT NULL
        """
    )


def _add_direct_messaging_columns(cur):
    # New columns on threads supporting 1:1 "direct" conversations --
    # teammate-to-teammate, or a message to someone who isn't a member
    # yet (participant_b_id stays NULL and external_name/email carry
    # who it's for). The existing 'vendor' and 'teammate' thread shapes
    # are untouched.
    for ddl in (
        "ALTER TABLE threads ADD COLUMN IF NOT EXISTS participant_a_id INTEGER REFERENCES users(id)",
        "ALTER TABLE threads ADD COLUMN IF NOT EXISTS participant_b_id INTEGER REFERENCES users(id)",
        "ALTER TABLE threads ADD COLUMN IF NOT EXISTS external_name TEXT",
        "ALTER TABLE threads ADD COLUMN IF NOT EXISTS external_email TEXT",
        "ALTER TABLE threads ADD COLUMN IF NOT EXISTS pending_email_sent_at TEXT",
    ):
        cur.execute(ddl)


def _widen_thread_type_check(cur):
    # Find whichever CHECK constraint governs threads.type (Postgres
    # auto-names it, and we'd rather not guess) and, if it doesn't
    # already allow 'direct', replace it with one that does.
    cur.execute(
        """
        SELECT con.conname, pg_get_constraintdef(con.oid) AS def
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        WHERE rel.relname = 'threads' AND con.contype = 'c'
        """
    )
    for conname, condef in cur.fetchall():
        if "'vendor'" in condef and "type" in condef and "'direct'" not in condef:
            cur.execute(f'ALTER TABLE threads DROP CONSTRAINT "{conname}"')
            cur.execute(
                "ALTER TABLE threads ADD CONSTRAINT threads_type_check "
                "CHECK (type IN ('vendor','teammate','partner','direct'))"
            )


def _add_thread_reads_table(cur):
    # Tracks the highest message id each user has seen in each thread, so
    # we can show an unread-messages badge. Deliberately a message-id
    # cursor rather than a timestamp: this app's timestamps only have
    # one-second resolution, so a message posted in the same second as a
    # "mark as read" could otherwise tie and be miscounted as read.
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS thread_reads (
            user_id INTEGER NOT NULL REFERENCES users(id),
            thread_id INTEGER NOT NULL REFERENCES threads(id),
            last_read_message_id INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, thread_id)
        )
        """
    )


if __name__ == "__main__":
    run_migrations()
    print("Migrations applied.")
