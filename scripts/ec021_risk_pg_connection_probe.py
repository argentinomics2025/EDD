"""EC-021 risk-country PG authentication preflight: strictly read-only.

Validates the GitHub secret and the dedicated database role without publishing
data, writing anything or displaying credentials. Intentionally independent of
the EC021_RISK_WRITES_ENABLED kill switch.
"""
import json
import os
from decimal import Decimal

from scripts.ec021_risk_country_scoped_writer import (
    assert_writer_role, public_rows, public_summary, validate_dsn, ROLE
)


def check(*, connect=None, read_rows=public_rows, read_summary=public_summary):
    dsn=validate_dsn(os.environ.get("EC021_RISK_DB_DSN"))
    if connect is None:
        import psycopg
        connect=psycopg.connect
    with connect(dsn,connect_timeout=15,sslmode="require",autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            assert_writer_role(cur)
            cur.execute("SELECT fecha, valor FROM public.historial_riesgo_pais ORDER BY fecha DESC LIMIT 30")
            stored={str(d):int(v) for d,v in cur.fetchall()}
            cur.execute("SELECT sell_value FROM public.economic_indicators WHERE id='riesgo-pais'")
            headline=cur.fetchone()
            if headline is None:
                raise RuntimeError("Risk headline not visible to dedicated role")
            cur.execute("SELECT current_setting('transaction_read_only')")
            readonly=cur.fetchone()
            if readonly is None or readonly[0] != "on":
                raise RuntimeError("Read-only PG transaction guard failed")
        conn.rollback()
    public=read_rows()
    if stored!=public:
        raise RuntimeError("Dedicated PG role snapshot differs from public snapshot")
    if Decimal(str(headline[0])) != read_summary() or Decimal(str(headline[0])) != Decimal(str(stored[max(stored)])):
        raise RuntimeError("PG risk headline does not match latest observations")
    return {"status":"connection_verified",
            "role":ROLE,"mode":"read_only_postgresql_preflight",
            "read_only_transaction":True,"latest_date":max(stored),
            "observations_verified":len(stored),
            "writes_to_supabase":False}


if __name__=="__main__":
    print(json.dumps(check(),ensure_ascii=False,sort_keys=True))
