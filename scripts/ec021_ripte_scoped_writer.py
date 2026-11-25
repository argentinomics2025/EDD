"""EC-021 RIPTE: one-month official append-only PostgreSQL writer, gated OFF.

No service_role or PostgREST write credentials. Requires dedicated ec021_ripte_writer
PG LOGIN account and explicit EC021_RIPTE_WRITES_ENABLED=true. Never UPDATE/DELETE.
"""
import argparse
import hashlib
import json
import os
from datetime import date
from decimal import Decimal
from urllib.parse import unquote, urlsplit

import requests
from scripts.bot_ripte import SOURCE_URL, parse_official, validate_existing, RipteValidationError

PROJECT = "fvyzacodrrmlxgzhneyt"
ROLE = "ec021_ripte_writer"
ENDPOINT = f"https://{PROJECT}.supabase.co/rest/v1/datos_salarios"
PUBLIC_KEY = "sb_publishable_32r2WZE28EI-O4aIP1D4Mw_fnwZ826j"


def read_source(http=requests):
    resp = http.get(SOURCE_URL, timeout=25,
                    headers={"User-Agent": "EconomiaCriolla-RIPTE-readonly/1.0"})
    resp.raise_for_status()
    if len(resp.content) > 3_000_000:
        raise RipteValidationError("Oversized official RIPTE response")
    official = parse_official(resp.text)
    return official, hashlib.sha256(resp.content).hexdigest()


def public_snapshot(http=requests, public_key=PUBLIC_KEY):
    if not public_key.startswith("sb_publishable_"):
        raise ValueError("Expected read-only Supabase publishable key")
    resp = http.get(ENDPOINT, timeout=20,
                    headers={"apikey": public_key, "Accept": "application/json"},
                    params={"select": "fecha,var_ripte_mensual", "order": "fecha.asc", "limit": "500"})
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list) or not 2 <= len(data) < 500:
        raise RipteValidationError("Untrusted or truncated RIPTE public snapshot")
    return data


def validate_dsn(dsn):
    parsed = urlsplit(dsn or "")
    if parsed.scheme not in ("postgres", "postgresql") or not parsed.password:
        raise ValueError("Missing dedicated RIPTE PostgreSQL credential")
    username = unquote(parsed.username or "")
    hostname = (parsed.hostname or "").lower()
    direct = hostname == f"db.{PROJECT}.supabase.co" and username == ROLE
    pooler = hostname.endswith(".pooler.supabase.com") and username == f"{ROLE}.{PROJECT}"
    if not (direct or pooler) or parsed.path != "/postgres" or parsed.port not in (5432, 6543):
        raise ValueError("Only dedicated RIPTE role and production project accepted")
    return dsn


def assert_writer_role(cur):
    cur.execute("""
        SELECT current_user::text, session_user::text,
          has_column_privilege(current_user,'public.datos_salarios','fecha','INSERT'),
          has_column_privilege(current_user,'public.datos_salarios','var_ripte_mensual','INSERT'),
          has_column_privilege(current_user,'public.datos_salarios','id','INSERT'),
          has_column_privilege(current_user,'public.datos_salarios','var_ripte_mensual','UPDATE'),
          has_table_privilege(current_user,'public.datos_salarios','DELETE'),
          r.rolbypassrls, t.relrowsecurity
        FROM pg_roles r CROSS JOIN pg_class t
        WHERE r.rolname=current_user AND t.oid='public.datos_salarios'::regclass
    """)
    row = cur.fetchone()
    if (row is None or row[0] != ROLE or row[1] != ROLE or
            row[2] is not True or row[3] is not True or
            row[4] is not False or row[5] is not False or
            row[6] is not False or row[7] is not False or row[8] is not True):
        raise RuntimeError("RIPTE writer privilege guard rejected: not dedicated append-only role")


def db_snapshot(cur):
    cur.execute("SELECT fecha,var_ripte_mensual FROM public.datos_salarios ORDER BY fecha")
    return [{"fecha": d.isoformat() if isinstance(d, date) else str(d),
             "var_ripte_mensual": str(v)} for d,v in cur.fetchall()]


def write_in_transaction(source, conn):
    with conn.cursor() as cur:
        assert_writer_role(cur)
        cur.execute("SELECT pg_advisory_xact_lock(202115, 53)")
        existing = db_snapshot(cur)
        pending = validate_existing(source, existing)
        if len(pending) > 1:
            raise RuntimeError("RIPTE multi-month write forbidden")
        if not pending:
            return {"status": "no_change", "applied": False, "reason": "already_current", "insert_only": []}
        r = pending[0]
        cur.execute(
            "INSERT INTO public.datos_salarios(fecha,var_ripte_mensual) VALUES(%s,%s) "
            "ON CONFLICT(fecha) DO NOTHING RETURNING fecha,var_ripte_mensual",
            (r["fecha"], Decimal(r["var_ripte_mensual"]))
        )
        inserted = cur.fetchone()
        cur.execute("SELECT fecha,var_ripte_mensual FROM public.datos_salarios WHERE fecha=%s", (r["fecha"],))
        observed = cur.fetchall()
        if len(observed) != 1 or Decimal(str(observed[0][1])) != Decimal(r["var_ripte_mensual"]):
            raise RuntimeError("RIPTE conflicting row; transaction must roll back")
        return {"status": "inserted" if inserted else "identical_duplicate",
                "applied": inserted is not None, "insert_only": [r]}


def run(*, apply=False, http=requests, connect=None):
    source, sha = read_source(http)
    stored = public_snapshot(http)
    pending = validate_existing(source, stored)
    data = {"source": SOURCE_URL, "source_sha256": sha,
            "last_official_month": source[-1]["fecha"],
            "last_stored_month": max(row["fecha"] for row in stored),
            "insert_only": pending, "writes_to_supabase": False}
    if not apply:
        return {**data, "mode": "read_only_monitor", "status": "needs_approval" if pending else "no_change"}
    if os.environ.get("EC021_RIPTE_WRITES_ENABLED") != "true":
        raise RuntimeError("RIPTE writes disabled by kill switch")
    dsn = validate_dsn(os.environ.get("EC021_RIPTE_DB_DSN"))
    if connect is None:
        import psycopg
        connect = psycopg.connect
    with connect(dsn, connect_timeout=15, sslmode="require", autocommit=False) as conn:
        result = write_in_transaction(source, conn)
    visible = public_snapshot(http)
    if validate_existing(source, visible):
        raise RuntimeError("RIPTE new observation not publicly visible after commit")
    return {**data, **result, "mode": "scoped_pg_writer",
            "public_read_verified": True, "writes_to_supabase": result["applied"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(apply=args.apply), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
