"""EC-021 BCRA: official five-series API reader and restricted atomic Postgres writer.

No service_role or Google intermediary. Board changes only for strictly newer
official dates. All existing historical observations are immutable.
"""
import argparse
import json
import os
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

import requests

SOURCE = "https://api.bcra.gob.ar/estadisticas/v4.0/Monetarias"
IDS = (1, 7, 15, 16, 31)
ROLE = "ec021_bcra_writer"
AR = ZoneInfo("America/Argentina/Buenos_Aires")


def _amount(value):
    if value is None or isinstance(value, bool):
        raise ValueError("Missing BCRA value")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Invalid BCRA numeric value") from exc
    if not amount.is_finite() or amount <= 0:
        raise ValueError("Invalid/nonpositive BCRA value")
    return amount


def validate(payload, *, today=None):
    """Fail closed unless the official catalog contains all five known series."""
    today = today or datetime.now(AR).date()
    if not isinstance(payload, dict) or payload.get("status") not in (200, "200"):
        raise ValueError("Invalid official BCRA response")
    rows = payload.get("results")
    if not isinstance(rows, list) or not 20 <= len(rows) <= 1500:
        raise ValueError("Unexpected BCRA catalog size")
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Malformed catalog entry")
        var_id = row.get("idVariable")
        if var_id not in IDS:
            continue
        if var_id in result:
            raise ValueError("Duplicate official series")
        try:
            when = date.fromisoformat(str(row.get("ultFechaInformada")))
        except ValueError as exc:
            raise ValueError("Invalid official date") from exc
        if when > today:
            raise ValueError("Future official date")
        desc = row.get("descripcion")
        if not isinstance(desc, str) or not desc.strip():
            raise ValueError("Missing official description")
        result[var_id] = {"date": when, "value": _amount(row.get("ultValorInformado"))}
    if set(result) != set(IDS):
        raise ValueError("Incomplete official series")
    return result


def collect(*, http=requests):
    response = http.get(SOURCE, params={"limit": 1500},
                        headers={"User-Agent": "EconomiaCriolla-EC021-BCRA/1"},
                        timeout=25)
    response.raise_for_status()
    if len(response.content) > 3_000_000:
        raise ValueError("Oversized official API response")
    return validate(response.json())


def plan(official, board, latest_history, *, today=None):
    today = today or datetime.now(AR).date()
    if set(board) != set(IDS) or set(latest_history) != set(IDS):
        raise ValueError("Incomplete or unexpected BCRA dashboard/history")
    updates = {}
    insertions = {}
    anomalies = {}
    for var_id in IDS:
        src = official[var_id]
        old_date, old_value = board[var_id]
        hist_date, hist_value = latest_history[var_id]
        if any(d > today for d in (old_date, hist_date, src["date"])):
            raise ValueError("Future observation")
        if old_date != hist_date or old_value != hist_value:
            raise ValueError("Dashboard and history disagree for variable " + str(var_id))
        if src["date"] < old_date:
            anomalies[var_id] = "official_behind_database"
        elif src["date"] == old_date:
            if src["value"] != old_value:
                anomalies[var_id] = "same_date_revision_requires_review"
        else:
            updates[var_id] = src
            insertions[var_id] = src
    return updates, insertions, anomalies


def run(*, check_db=False, apply=False):
    official = collect()
    result = {
        "source": SOURCE,
        "mode": "source_checked",
        "series": len(official),
        "official_dates": {str(k): str(v["date"]) for k, v in sorted(official.items())},
        "applied": False,
    }
    if not (check_db or apply):
        return result
    if not os.getenv("EC021_BCRA_DB_DSN"):
        raise RuntimeError("Dedicated BCRA PostgreSQL DSN missing")
    import psycopg
    with psycopg.connect(os.environ["EC021_BCRA_DB_DSN"], connect_timeout=15) as conn:
        with conn.cursor() as cur:
            if not apply:
                cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SELECT current_user")
            role = cur.fetchone()[0]
            if role != ROLE:
                raise RuntimeError("Incorrect PostgreSQL role")
            cur.execute("SELECT id_variable,fecha,valor FROM public.bcra_data WHERE id_variable=ANY(%s)",
                        (list(IDS),))
            board = {i: (d, v) for i, d, v in cur.fetchall()}
            cur.execute(
                "SELECT DISTINCT ON(id_variable) id_variable,fecha,valor "
                "FROM public.historial_bcra WHERE id_variable=ANY(%s) "
                "ORDER BY id_variable,fecha DESC",
                (list(IDS),),
            )
            latest = {i: (d, v) for i, d, v in cur.fetchall()}
            updates, inserts, anomalies = plan(official, board, latest)
            result.update({"db_role": role, "updates_planned": len(updates),
                           "history_inserts_planned": len(inserts),
                           "anomalies": {str(k): v for k, v in anomalies.items()}})
            if not apply:
                conn.rollback()
                result["mode"] = "authenticated_read_only"
                return result
            if os.environ.get("EC021_BCRA_WRITES_ENABLED") != "true":
                raise RuntimeError("BCRA write kill switch disabled")
            if anomalies:
                raise RuntimeError("BCRA source/revision mismatch; no writes")
            for i, source in sorted(updates.items()):
                expected_date, expected_value = board[i]
                # Optimistic concurrency guard; any partial run rolls back.
                cur.execute(
                    "UPDATE public.bcra_data SET fecha=%s,valor=%s,last_updated=now() "
                    "WHERE id_variable=%s AND fecha=%s AND valor=%s AND fecha<%s",
                    (source["date"], source["value"], i, expected_date,
                     expected_value, source["date"]),
                )
                if cur.rowcount != 1:
                    raise RuntimeError("Concurrent BCRA update; transaction rolled back")
                cur.execute(
                    "INSERT INTO public.historial_bcra (id_variable,fecha,valor) "
                    "VALUES (%s,%s,%s)",
                    (i, source["date"], source["value"]),
                )
                if cur.rowcount != 1:
                    raise RuntimeError("Unexpected BCRA history insertion count")
            conn.commit()
            result["applied"] = bool(updates)
            result["mode"] = "atomic_append_only" if updates else "no_change"
            return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-db", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(check_db=args.check_db, apply=args.apply),
                     sort_keys=True, default=str))
