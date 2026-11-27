"""EC-021 Agro: exclusive PostgreSQL INSERT-only writer for MAGyP official FOB.

No service role, no broad Supabase secrets, no legacy datos_agro table.
Dates are official publication dates; shipment windows and NCM retained.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
from decimal import Decimal

from scripts.ec021_agro_magyp_fob_reader import fetch_latest, AgroFOBError, CODES, SOURCE

ROLE = "ec021_agro_fob_writer"
TABLE = "public.agro_fob_oficial"


def decide(batch: list[dict], existing: list[dict], last_db_date: str | None, official_date: str) -> str:
    if len(batch) != 4 or {x["serie"] for x in batch} != set(CODES):
        raise AgroFOBError("Incomplete official four-product batch")
    if any(x["fecha"] != official_date or x["posicion"] != CODES[x["serie"]] or x["fuente"] != SOURCE for x in batch):
        raise AgroFOBError("Changed source identity or mixed official periods")
    if last_db_date and last_db_date > official_date:
        raise AgroFOBError("Official feed older than stored publication")
    if existing:
        if len(existing) != 4 or {x["serie"] for x in existing} != set(CODES):
            raise AgroFOBError("Incomplete previously inserted publication")
        for row in batch:
            old = next(x for x in existing if x["serie"] == row["serie"])
            fields = ("posicion", "embarque_desde", "embarque_hasta", "circular", "fuente")
            if any(str(old[key]) != str(row[key]) for key in fields) or Decimal(str(old["precio_usd_tn"])) != Decimal(str(row["precio_usd_tn"])):
                raise AgroFOBError("Official historical revision detected; append-only, do not overwrite")
        return "no_change"
    if last_db_date is None:
        raise AgroFOBError("Unapproved empty database bootstrap")
    lag = (dt.date.fromisoformat(official_date) - dt.date.fromisoformat(last_db_date)).days
    if not 1 <= lag <= 7:
        raise AgroFOBError("Unexpected publication gap or date order")
    return "insert"


def run(*, apply: bool = False, check_db: bool = False) -> dict:
    if apply and os.getenv("EC021_AGRO_FOB_WRITES_ENABLED") != "true":
        raise AgroFOBError("Production writer kill switch off")
    report = fetch_latest()
    if not (apply or check_db):
        return report
    dsn = os.getenv("EC021_AGRO_FOB_DB_DSN", "")
    if not dsn:
        raise AgroFOBError("Exclusive database connection missing")
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError:
        raise AgroFOBError("Pinned psycopg driver missing") from None
    with psycopg.connect(dsn, row_factory=dict_row, connect_timeout=10, autocommit=True) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout = '15s'")
                cur.execute("SET LOCAL lock_timeout = '5s'")
                if not apply:
                    cur.execute("SET LOCAL transaction_read_only = on")
                cur.execute("SELECT current_user AS rol")
                if cur.fetchone()["rol"] != ROLE:
                    raise AgroFOBError("Wrong role, require exclusive FOB writer")
                cur.execute("SELECT pg_try_advisory_xact_lock(21021, 3846) AS acquired")
                if not cur.fetchone()["acquired"]:
                    raise AgroFOBError("Concurrent Agro run rejected")
                cur.execute("SELECT max(fecha)::text AS ultimo FROM " + TABLE)
                last_db_date = cur.fetchone()["ultimo"]
                cur.execute(
                    "SELECT serie,posicion,precio_usd_tn,circular,embarque_desde::text,embarque_hasta::text,fuente "
                    "FROM " + TABLE + " WHERE fecha=%s",
                    (dt.date.fromisoformat(report["fecha"]),)
                )
                action = decide(report["series"],cur.fetchall(),last_db_date,report["fecha"])
                if apply and action == "insert":
                    cur.executemany(
                        "INSERT INTO " + TABLE +
                        " (fecha,serie,posicion,precio_usd_tn,circular,embarque_desde,embarque_hasta,fuente,lote_sha256) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        [(dt.date.fromisoformat(x["fecha"]),x["serie"],x["posicion"],
                          Decimal(str(x["precio_usd_tn"])),x["circular"],
                          dt.date.fromisoformat(x["embarque_desde"]),
                          dt.date.fromisoformat(x["embarque_hasta"]),x["fuente"],report["sha256"])
                         for x in report["series"]]
                    )
                report.update({"status": "no_change" if action == "no_change" else (
                    "inserted" if apply else "db_checked_read_only"),
                    "db_role":ROLE,"next_action":action,
                    "applied":apply and action=="insert",
                    "inserted":4 if apply and action=="insert" else 0})
    return report


def main() -> int:
    parser=argparse.ArgumentParser()
    choices=parser.add_mutually_exclusive_group(required=True)
    choices.add_argument("--source-only",action="store_true")
    choices.add_argument("--check-db",action="store_true")
    choices.add_argument("--commit",action="store_true")
    args=parser.parse_args()
    try:
        result=run(apply=args.commit,check_db=args.check_db)
    except AgroFOBError as exc:
        print(json.dumps({"status":"rejected","reason":str(exc),"applied":False}))
        return 1
    except Exception:
        # Keep connection strings, upstream request details and tokens out of logs.
        print(json.dumps({"status":"rejected","reason":"source or database execution failed","applied":False}))
        return 1
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
