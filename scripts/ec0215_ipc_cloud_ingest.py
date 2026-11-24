"""EC-021.5: scheduled INDEC IPC monitor and OPTIONAL least-privilege PostgreSQL writer.

No shared service_role key, no UPDATE, no DELETE and no historical backfill.
The scheduled writer is OFF unless explicit repository variable and secret are set.
"""
import argparse
import json
import os
from datetime import date
from decimal import Decimal
from urllib.parse import unquote, urlsplit

import requests
from scripts.ec0215_indec_ipc_nacional import read_official_csv, parse_national_monthly
from scripts.ec0215_ipc_insert_plan import plan_increment

PROJECT = "fvyzacodrrmlxgzhneyt"
ENDPOINT = f"https://{PROJECT}.supabase.co/rest/v1/datos_inflacion"
ROLE = "ec0215_ipc_writer"


def snapshot_http(public_key, http=requests):
    if not public_key or not (public_key.startswith("sb_publishable_") or public_key.startswith("eyJ")):
        raise RuntimeError("Read-only Supabase publishable key required")
    headers = {"apikey": public_key, "Accept": "application/json"}
    if public_key.startswith("eyJ"):
        headers["Authorization"] = "Bearer " + public_key
    response = http.get(ENDPOINT, params={"select": "date,value", "order": "date.desc", "limit": "4"},
                        headers=headers, timeout=20)
    response.raise_for_status()
    rows = response.json()
    if not isinstance(rows, list) or len(rows) < 2:
        raise RuntimeError("Failed to retrieve IPC public snapshot")
    return rows


def validate_pg_dsn(dsn):
    """Allow only project's direct or shared pooler endpoint, never arbitrary servers."""
    p = urlsplit(dsn or "")
    if p.scheme not in ("postgres", "postgresql") or p.password is None:
        raise ValueError("Dedicated PostgreSQL connection secret missing or invalid")
    username = unquote(p.username or "")
    host = (p.hostname or "").lower()
    direct = host == f"db.{PROJECT}.supabase.co" and username == ROLE
    pooler = host.endswith(".pooler.supabase.com") and username == f"{ROLE}.{PROJECT}"
    if not (direct or pooler) or p.path != "/postgres" or p.port not in (5432, 6543):
        raise ValueError("Dedicated IPC writer must connect to its project and its own role")
    return dsn


def _privileges(cursor):
    cursor.execute("""SELECT current_user::text, session_user::text,
      has_column_privilege(current_user,'public.datos_inflacion','date','INSERT'),
      has_column_privilege(current_user,'public.datos_inflacion','value','INSERT'),
      has_table_privilege(current_user,'public.datos_inflacion','UPDATE'),
      has_table_privilege(current_user,'public.datos_inflacion','DELETE'),
      r.rolbypassrls
      FROM pg_roles r WHERE r.rolname=current_user""")
    row = cursor.fetchone()
    if row is None or row[0] != ROLE or row[1] != ROLE or not row[2] or not row[3] or row[4] or row[5] or row[6]:
        raise RuntimeError("Refusing write: connection is not the isolated IPC INSERT-only role")


def _database_snapshot(cursor):
    cursor.execute("SELECT date, value FROM public.datos_inflacion ORDER BY date DESC LIMIT 4")
    return [{"date": d.isoformat() if isinstance(d, date) else str(d), "value": str(v)} for d, v in cursor.fetchall()]


def apply_with_connection(source, connection):
    """Entire check and optional INSERT run in one transaction; caller commits only on success."""
    with connection.cursor() as cursor:
        _privileges(cursor)
        # Advisory transaction lock prevents overlapping runs of THIS writer.
        cursor.execute("SELECT pg_advisory_xact_lock(202115, 52)")
        plan = plan_increment(source, _database_snapshot(cursor))
        added = plan["insert_only"]
        if len(added) > 1:
            raise RuntimeError("Unexpected multi-row INSERT plan")
        if not added:
            return {**plan, "applied": False, "reason": "already_current"}
        row = added[0]
        cursor.execute(
            "INSERT INTO public.datos_inflacion (date, value) VALUES (%s, %s) "
            "ON CONFLICT (date) DO NOTHING RETURNING date, value",
            (row["date"], Decimal(row["value"])),
        )
        inserted = cursor.fetchone()
        cursor.execute("SELECT date,value FROM public.datos_inflacion WHERE date=%s", (row["date"],))
        verified = cursor.fetchall()
        if len(verified) != 1 or Decimal(verified[0][1]) != Decimal(row["value"]):
            raise RuntimeError("Insertion conflicted with different value, rolling back")
        return {**plan, "applied": inserted is not None, "reason": "inserted" if inserted else "identical_duplicate"}


def run(*, apply=False, http=requests, connect=None):
    source = parse_national_monthly(read_official_csv())
    rows = snapshot_http(os.environ.get("EC0215_IPC_READ_KEY"), http=http)
    preview = plan_increment(source, rows)
    if not apply:
        return {**preview, "applied": False, "mode": "read_only_monitor"}
    if os.environ.get("EC0215_IPC_WRITES_ENABLED") != "true":
        raise RuntimeError("IPC writes disabled by explicit kill switch")
    dsn = validate_pg_dsn(os.environ.get("EC0215_IPC_DB_DSN"))
    if connect is None:
        import psycopg
        connect = psycopg.connect
    # sslmode=require is mandatory; never print the connection string or secrets.
    with connect(dsn, connect_timeout=15, sslmode="require", autocommit=False) as conn:
        result = apply_with_connection(source, conn)
    # Read via public endpoint again to establish result visible to frontend.
    after = snapshot_http(os.environ.get("EC0215_IPC_READ_KEY"), http=http)
    check = plan_increment(source, after)
    if check["insert_only"]:
        raise RuntimeError("IPC not visible through public read API after committed transaction")
    return {**result, "mode": "scoped_pg_writer", "public_read_verified": True}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true", help="Requires explicit kill switch and DB secret")
    args = p.parse_args()
    result = run(apply=args.apply)
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
