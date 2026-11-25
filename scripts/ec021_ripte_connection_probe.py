"""EC-021 RIPTE: PostgreSQL connection check without any writes.

ONLY tests the dedicated role and SELECT; never logs URLs, usernames with
passwords, raw DSNs, source HTML or environment variables.
"""
import json
import os

from scripts.bot_ripte import validate_existing
from scripts.ec021_ripte_scoped_writer import (
    read_source, validate_dsn, assert_writer_role, db_snapshot, public_snapshot
)


def probe(connect=None):
    official, source_hash = read_source()
    dsn = validate_dsn(os.environ.get("EC021_RIPTE_DB_DSN"))
    if connect is None:
        import psycopg
        connect = psycopg.connect
    # READ ONLY at database transaction level, never commit a data change.
    with connect(dsn, connect_timeout=15, sslmode="require", autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            assert_writer_role(cur)
            stored = db_snapshot(cur)
            pending = validate_existing(official, stored)
            cur.execute("SELECT current_setting('transaction_read_only')")
            if str(cur.fetchone()[0]).lower() != "on":
                raise RuntimeError("Expected read-only database transaction")
        conn.rollback()
    public = public_snapshot()
    if validate_existing(official, public) != pending:
        raise RuntimeError("Public Supabase snapshot differs from dedicated-role SELECT")
    return {
        "status": "connection_verified",
        "role": "ec021_ripte_writer",
        "mode": "read_only_postgresql_probe",
        "read_only_transaction": True,
        "last_official_month": official[-1]["fecha"],
        "last_stored_month": max(r["fecha"] for r in stored),
        "insert_only_plan": pending,
        "source_sha256": source_hash,
        "writes_to_supabase": False,
    }


if __name__ == "__main__":
    print(json.dumps(probe(), ensure_ascii=False, sort_keys=True))
