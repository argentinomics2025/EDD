"""EC-021.5: test dedicated IPC PostgreSQL connection, strictly read-only.

Never publishes or changes data, and does not require the write kill-switch.
Does not print the DSN or password.
"""
import json
import os
from datetime import date
from decimal import Decimal

from scripts.ec0215_ipc_cloud_ingest import (
    ROLE, validate_pg_dsn, _privileges, snapshot_http
)

READ_KEY = "sb_publishable_32r2WZE28EI-O4aIP1D4Mw_fnwZ826j"


def check(*, connect=None, public_snapshot=None):
    dsn=validate_pg_dsn(os.environ.get("EC0215_IPC_DB_DSN"))
    if connect is None:
        import psycopg
        connect=psycopg.connect
    with connect(dsn,connect_timeout=15,sslmode="require",autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            _privileges(cur)
            cur.execute("SELECT date,value FROM public.datos_inflacion ORDER BY date DESC LIMIT 4")
            got=cur.fetchall()
            cur.execute("SELECT current_setting('transaction_read_only')")
            marker=cur.fetchone()
            if marker != ("on",):
                raise RuntimeError("IPC probe not in a read-only transaction")
        conn.rollback()
    if len(got) != 4:
        raise RuntimeError("Dedicated IPC role cannot read four expected months")
    stored={d.isoformat() if isinstance(d,date) else str(d):Decimal(str(v)) for d,v in got}
    if len(stored) != 4:
        raise RuntimeError("Duplicate IPC date in PG snapshot")
    rows=(public_snapshot if public_snapshot is not None else
          snapshot_http(READ_KEY))
    public={str(row["date"]):Decimal(str(row["value"])) for row in rows}
    if len(public)!=4 or public != stored:
        raise RuntimeError("Dedicated IPC PG snapshot differs from public API")
    return {"status":"connection_verified","role":ROLE,
            "mode":"read_only_postgresql_preflight",
            "read_only_transaction":True,"months_compared":4,
            "latest_month":max(stored),"latest_pct":str(stored[max(stored)]),
            "writes_to_supabase":False}


if __name__ == "__main__":
    print(json.dumps(check(),sort_keys=True,ensure_ascii=False))
