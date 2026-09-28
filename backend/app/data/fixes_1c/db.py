"""Plain psycopg connection for the 1C fix scripts (one transaction per run)."""
import os
import sys

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv


def connect():
    load_dotenv()
    dsn = os.environ["DB_STRING"]
    conn = psycopg.connect(dsn, row_factory=dict_row, prepare_threshold=None, autocommit=False)
    host = conn.info.host
    print(f"[1c] connected to {host}/{conn.info.dbname}", file=sys.stderr)
    return conn


def apply_flag() -> bool:
    """Scripts are dry-run by default; pass --apply to commit."""
    return "--apply" in sys.argv


def finish(conn, apply: bool):
    if apply:
        conn.commit()
        print("[1c] COMMITTED")
    else:
        conn.rollback()
        print("[1c] dry run: rolled back (pass --apply to commit)")


def one(conn, sql, params=None):
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        row = cur.fetchone()
        return list(row.values())[0] if row else None


def rows(conn, sql, params=None):
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        return cur.fetchall()


def exec_(conn, sql, params=None) -> int:
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        return cur.rowcount
