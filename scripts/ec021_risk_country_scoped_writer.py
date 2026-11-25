"""EC-021 Riesgo País: guarded append-only PG writer, OFF by default.

Provider: ArgentinaDatos (upstream Ámbito; J.P. Morgan EMBI).
The operator has authorized loading facts; the operator's approval is NOT a third-party
redistribution license. No service_role. No DELETE, historical UPDATE or UPSERT.
To activate: dedicated LOGIN ec021_risk_writer, GitHub Actions secret EC021_RISK_DB_DSN,
repository variable EC021_RISK_WRITES_ENABLED=true. Do not reuse the RIPTE secret.
"""
import argparse
import json
import os
from datetime import date, datetime
from decimal import Decimal
from urllib.parse import unquote, urlsplit
from zoneinfo import ZoneInfo

import requests
from scripts.ec021_risk_country_readonly import (
    SOURCE_URL, DATABASE_URL, PUBLIC_KEY, fetch_json, parse_rows, RiskSourceError
)

PROJECT = "fvyzacodrrmlxgzhneyt"
ROLE = "ec021_risk_writer"
SUMMARY_URL = f"https://{PROJECT}.supabase.co/rest/v1/economic_indicators"


def validate_dsn(dsn):
    u = urlsplit(dsn or "")
    if u.scheme not in ("postgres", "postgresql") or not u.password:
        raise ValueError("Missing dedicated risk-country PostgreSQL credential")
    hostname = (u.hostname or "").lower()
    username = unquote(u.username or "")
    direct = hostname == f"db.{PROJECT}.supabase.co" and username == ROLE
    pooler = hostname.endswith(".pooler.supabase.com") and username == f"{ROLE}.{PROJECT}"
    if not (direct or pooler) or u.path != "/postgres" or u.port not in (5432, 6543):
        raise ValueError("Untrusted role, project or PostgreSQL endpoint")
    return dsn


def plan(source, stored, summary, *, today=None):
    """Verify immutable historical overlap and propose at most one new observation."""
    if len(source) < 20 or len(stored) < 15:
        raise RiskSourceError("Insufficient risk-country observations")
    last_stored = max(stored)
    last_source = max(source)
    overlap = set(source) & set(stored)
    if len(overlap) < 15:
        raise RiskSourceError("Too few matching historical dates")
    if any(source[d] != stored[d] for d in overlap):
        raise RiskSourceError("Historical revision: manual review, no write")
    if last_source < last_stored:
        raise RiskSourceError("Source older than production")
    if Decimal(str(summary)) != Decimal(str(stored[last_stored])):
        raise RiskSourceError("Headline differs from last stored observation")
    pending = sorted(d for d in source if d > last_stored)
    if len(pending) > 1:
        raise RiskSourceError("More than one new trading date: manual review")
    if not pending:
        return []
    today = today or datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date()
    day = date.fromisoformat(pending[0])
    if day > today or pending[0] < "2026-11-25" or (day - date.fromisoformat(last_stored)).days > 7:
        raise RiskSourceError("Source date violates append-only guard")
    return [{"fecha": pending[0], "valor": source[pending[0]]}]


def public_rows(*, http=requests):
    raw, _ = fetch_json(
        DATABASE_URL, http=http,
        params={"select":"fecha,valor", "order":"fecha.desc", "limit":"30"},
        headers={"apikey":PUBLIC_KEY,"Accept":"application/json"}
    )
    return parse_rows(raw, minimum=15)


def public_summary(*, http=requests):
    raw, _ = fetch_json(
        SUMMARY_URL, http=http,
        params={"select":"id,sell_value","id":"eq.riesgo-pais","limit":"2"},
        headers={"apikey":PUBLIC_KEY,"Accept":"application/json"}
    )
    if not isinstance(raw,list) or len(raw) != 1 or raw[0].get("id") != "riesgo-pais":
        raise RiskSourceError("Risk-country headline missing or duplicated")
    return Decimal(str(raw[0]["sell_value"]))


def assert_writer_role(cur):
    cur.execute("""
      SELECT current_user::text, session_user::text,
        has_column_privilege(current_user,'public.historial_riesgo_pais','fecha','INSERT'),
        has_column_privilege(current_user,'public.historial_riesgo_pais','valor','INSERT'),
        has_column_privilege(current_user,'public.historial_riesgo_pais','valor','UPDATE'),
        has_table_privilege(current_user,'public.historial_riesgo_pais','DELETE'),
        has_column_privilege(current_user,'public.economic_indicators','sell_value','UPDATE'),
        has_column_privilege(current_user,'public.economic_indicators','last_updated','UPDATE'),
        has_column_privilege(current_user,'public.economic_indicators','buy_value','UPDATE'),
        has_table_privilege(current_user,'public.economic_indicators','DELETE'),
        r.rolbypassrls,
        (SELECT relrowsecurity FROM pg_class WHERE oid='public.historial_riesgo_pais'::regclass),
        (SELECT relrowsecurity FROM pg_class WHERE oid='public.economic_indicators'::regclass)
      FROM pg_roles r WHERE r.rolname=current_user
    """)
    row=cur.fetchone()
    if (row is None or row[0:2] != (ROLE,ROLE) or
        tuple(row[2:]) != (True,True,False,False,True,True,False,False,False,True,True)):
        raise RuntimeError("Dedicated append-only and limited-headline role not verified")


def write_in_transaction(source, conn):
    with conn.cursor() as cur:
        assert_writer_role(cur)
        cur.execute("SELECT pg_advisory_xact_lock(20261125, 21)")
        cur.execute("SELECT fecha,valor FROM public.historial_riesgo_pais ORDER BY fecha DESC LIMIT 30")
        stored = {str(d): int(v) for d,v in cur.fetchall()}
        cur.execute("SELECT sell_value FROM public.economic_indicators WHERE id='riesgo-pais'")
        row = cur.fetchone()
        if row is None:
            raise RiskSourceError("Risk headline missing")
        pending = plan(source,stored,row[0])
        if not pending:
            return {"status":"no_change","applied":False,"date":None}
        observation = pending[0]
        cur.execute("INSERT INTO public.historial_riesgo_pais(fecha,valor) VALUES(%s,%s) RETURNING fecha,valor",
                    (observation["fecha"],Decimal(observation["valor"])))
        inserted = cur.fetchone()
        if not inserted or str(inserted[0]) != observation["fecha"] or int(inserted[1]) != observation["valor"]:
            raise RiskSourceError("Risk historical insert verification failed")
        cur.execute("""
          UPDATE public.economic_indicators
          SET sell_value=%s,last_updated=now()
          WHERE id='riesgo-pais' AND sell_value=%s
          RETURNING sell_value
        """,(Decimal(observation["valor"]),Decimal(row[0])))
        updated=cur.fetchall()
        if len(updated)!=1 or Decimal(str(updated[0][0])) != Decimal(observation["valor"]):
            raise RiskSourceError("Risk headline update mismatch")
        return {"status":"inserted","applied":True,"date":observation["fecha"],"value":observation["valor"]}


def run(*, apply=False, http=requests, connect=None):
    raw, sha=fetch_json(SOURCE_URL,http=http)
    source=parse_rows(raw,minimum=20)
    stored=public_rows(http=http)
    headline=public_summary(http=http)
    pending=plan(source,stored,headline)
    result={"mode":"read_only" if not apply else "dedicated_pg_writer",
            "source":SOURCE_URL,"source_sha256":sha,
            "last_source_date":max(source),"last_stored_date":max(stored),
            "insert_only":pending,"writes_to_supabase":False}
    if not apply:
        return {**result,"status":"needs_approval" if pending else "no_change"}
    if os.environ.get("EC021_RISK_WRITES_ENABLED") != "true":
        raise RuntimeError("Country-risk writer kill switch is OFF")
    dsn=validate_dsn(os.environ.get("EC021_RISK_DB_DSN"))
    if connect is None:
        import psycopg
        connect=psycopg.connect
    with connect(dsn,connect_timeout=15,sslmode="require",autocommit=False) as conn:
        outcome=write_in_transaction(source,conn)
    visible=public_rows(http=http)
    visible_headline=public_summary(http=http)
    if plan(source,visible,visible_headline):
        raise RiskSourceError("Risk write not visible in public Supabase after commit")
    return {**result,**outcome,"public_read_verified":True,
            "writes_to_supabase":outcome["applied"]}


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--apply",action="store_true")
    args=parser.parse_args()
    print(json.dumps(run(apply=args.apply),ensure_ascii=False,sort_keys=True))
