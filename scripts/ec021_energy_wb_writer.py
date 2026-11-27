"""Exclusive append-only writer for World Bank MONTHLY energy benchmark prices.

Fails closed on revisions, missing metadata, gaps, unknown DB roles or a missing
kill switch. No UPDATE, DELETE, UPSERT, legacy energy table, or service_role key.
Requires private PostgreSQL URI for role ec021_energy_wb_writer (not in source).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from decimal import Decimal

from scripts.ec021_energy_worldbank import fetch_bytes, parse_monthly, SourceError

EXPECTED_ROLE = "ec021_energy_wb_writer"
EXPECTED = {"brent_monthly_wb": "USD/barrel", "wti_monthly_wb": "USD/barrel", "gas_us_monthly_wb": "USD/MMBtu"}


def _month_before(period: str) -> str:
    year, month = [int(x) for x in period.split("-")]
    if month == 1:
        return f"{year - 1}-12"
    return f"{year}-{month-1:02d}"


def decide(latest: list[dict], existing: list[dict], current_max: str | None, period: str) -> str:
    if len(latest) != 3 or {x["asset"] for x in latest} != set(EXPECTED):
        raise SourceError("Incomplete official source batch")
    if any(x["period"] != period or x["unit"] != EXPECTED[x["asset"]] for x in latest):
        raise SourceError("Inconsistent period or commodity unit")
    if current_max is not None and current_max[:7] > period:
        raise SourceError("Database contains newer month than source")
    if existing:
        if len(existing) != 3 or {x["serie"] for x in existing} != set(EXPECTED):
            raise SourceError("Partial or duplicate database month")
        for remote in latest:
            stored = next(x for x in existing if x["serie"] == remote["asset"])
            if stored["unidad"] != remote["unit"] or Decimal(str(stored["precio"])) != Decimal(str(remote["value"])):
                raise SourceError("Official revision: new edition differs from stored month; no overwrite")
        return "no_change"
    if current_max is None or current_max[:7] != _month_before(period):
        raise SourceError("Missing previous month, unexpected gap or out-of-order edition")
    return "insert"


def run(*, apply: bool = False, check_db: bool = False) -> dict:
    if apply and os.getenv("EC021_ENERGY_WB_WRITES_ENABLED") != "true":
        raise SourceError("Energy writer kill switch disabled")
    report = parse_monthly(fetch_bytes())
    if not (check_db or apply):
        return report
    dsn = os.getenv("EC021_ENERGY_WB_DB_DSN", "")
    if not dsn:
        raise SourceError("Exclusive database DSN missing")
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError:
        raise SourceError("Pinned psycopg driver missing") from None
    period = report["period"]
    with psycopg.connect(dsn, autocommit=False, row_factory=dict_row, connect_timeout=10) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout = '15s'")
                cur.execute("SET LOCAL lock_timeout = '5s'")
                cur.execute("SELECT current_user AS rol")
                if cur.fetchone()["rol"] != EXPECTED_ROLE:
                    raise SourceError("Wrong DB role: exclusive writer required")
                # Serialize repeat/manual/scheduled executions.
                cur.execute("SELECT pg_try_advisory_xact_lock(21021, 2327) AS acquired")
                if not cur.fetchone()["acquired"]:
                    raise SourceError("Concurrent energy execution blocked")
                cur.execute("SELECT max(periodo)::text AS ultimo FROM public.energia_referencias_mensuales")
                latest_db = cur.fetchone()["ultimo"]
                cur.execute(
                    "SELECT serie, precio, unidad FROM public.energia_referencias_mensuales WHERE periodo=%s",
                    (dt.date.fromisoformat(period + "-01"),),
                )
                existing = cur.fetchall()
                status = decide(report["records"], existing, latest_db, period)
                if apply and status == "insert":
                    cur.executemany(
                        """INSERT INTO public.energia_referencias_mensuales
                           (periodo, serie, precio, unidad, fuente, archivo_sha256)
                           VALUES (%s,%s,%s,%s,%s,%s)""",
                        [(dt.date.fromisoformat(period + "-01"),
                          x["asset"], Decimal(str(x["value"])), x["unit"],
                          report["dataset"], report["file_sha256"])
                         for x in report["records"]],
                    )
                # A check is not a write. Never let it accidentally persist.
                if not apply:
                    report.update({"status": "db_checked_read_only", "db_role": EXPECTED_ROLE,
                                   "next_action": status, "applied": False})
                    return report
                report.update({"status": status, "db_role": EXPECTED_ROLE,
                               "applied": status == "insert", "inserted": 3 if status == "insert" else 0})
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    opts = parser.add_mutually_exclusive_group(required=True)
    opts.add_argument("--check-source", action="store_true")
    opts.add_argument("--check-db", action="store_true")
    opts.add_argument("--commit", action="store_true")
    args = parser.parse_args()
    try:
        output = run(apply=args.commit, check_db=args.check_db)
    except Exception as exc:
        # Do not echo DB URIs, provider URLs with secrets, or opaque exceptions.
        if isinstance(exc, SourceError):
            print(json.dumps({"status": "rejected", "reason": str(exc), "applied": False}))
        else:
            print(json.dumps({"status": "rejected", "reason": "upstream or DB execution failure", "applied": False}))
        return 1
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
