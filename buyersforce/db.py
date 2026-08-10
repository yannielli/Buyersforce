import sqlite3
import os
from flask import g

# DB_PATH can be overridden via env var to point at a persistent volume
# mount (e.g. /data/buyersforce.db on Railway) so data survives redeploys.
# Falls back to a file next to this script for local development.
DB_PATH = os.environ.get("DB_PATH") or os.path.join(os.path.dirname(__file__), "buyersforce.db")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_app(app):
    app.teardown_appcontext(close_db)


def query(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv


def execute(sql, args=()):
    db = get_db()
    cur = db.execute(sql, args)
    db.commit()
    return cur.lastrowid
