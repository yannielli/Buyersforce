import os
import psycopg2
import psycopg2.extras
from flask import g


def _database_url():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. This app requires a PostgreSQL database "
            "(e.g. Railway's Postgres plugin, which injects DATABASE_URL automatically)."
        )
    # psycopg2 expects the "postgresql://" scheme; some providers hand out
    # "postgres://" instead.
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


def get_db():
    if "db" not in g:
        g.db = psycopg2.connect(_database_url())
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_app(app):
    app.teardown_appcontext(close_db)


def _pg(sql):
    """Translate the app's SQLite-style '?' placeholders to psycopg2's '%s'."""
    return sql.replace("?", "%s")


def query(sql, args=(), one=False):
    db = get_db()
    with db.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(_pg(sql), args)
        rv = cur.fetchall()
    return (rv[0] if rv else None) if one else rv


def execute(sql, args=()):
    """Run an INSERT/UPDATE/DELETE. For INSERTs, returns the new row's id
    (mirroring sqlite3's cursor.lastrowid, which psycopg2 has no equivalent
    for) by appending a RETURNING id clause when the statement doesn't
    already have one.
    """
    db = get_db()
    stripped = sql.strip()
    is_insert = stripped.upper().startswith("INSERT")
    if is_insert and "RETURNING" not in stripped.upper():
        sql = stripped.rstrip(";") + " RETURNING id"
    with db.cursor() as cur:
        cur.execute(_pg(sql), args)
        row = cur.fetchone() if is_insert else None
    db.commit()
    return row[0] if row else None
