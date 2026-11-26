"""EC-021: auditable seven-quote reader and constrained PostgreSQL writer.

Not scheduled for writes until third-party provenance and economic methodology
are approved. Never update or delete existing historical rows.
"""
import argparse
import json
import os
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

import requests

SOURCE = "https://dolarapi.com/v1/dolares"
TICKERS = {
    "oficial": "dolar-oficial", "blue": "dolar-blue",
    "bolsa": "dolar-mep", "contadoconliqui": "dolar-ccl",
    "cripto": "dolar-cripto", "mayorista": "dolar-mayorista",
    "tarjeta": "dolar-tarjeta",
}
AR = ZoneInfo("America/Argentina/Buenos_Aires")


def parse_amount(raw, *, optional=False):
    if raw is None and optional:
        return None
    if raw is None or isinstance(raw, bool):
        raise ValueError("Missing or invalid quote amount")
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Non-numeric quote") from exc
    if not value.is_finite() or not Decimal("1") <= value <= Decimal("100000"):
        raise ValueError("Quote is non-finite or out of range")
    return value


def validate(payload, now=None):
    """Preserve each quote's own timestamp; markets can close on different dates."""
    now = now or datetime.now(timezone.utc)
    if not isinstance(payload, list) or not 7 <= len(payload) <= 15:
        raise ValueError("Unexpected DolarAPI quote count")
    quotes = {}
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("Malformed quote record")
        ticker = TICKERS.get(item.get("casa"))
        if ticker is None:
            continue
        if ticker in quotes:
            raise ValueError("Duplicate canonical quote")
        raw_time = item.get("fechaActualizacion")
        if not isinstance(raw_time, str):
            raise ValueError("Missing source timestamp")
        try:
            changed = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("Invalid source timestamp") from exc
        if changed.tzinfo is None:
            raise ValueError("Timezone missing in quote timestamp")
        changed = changed.astimezone(timezone.utc)
        age_seconds = (now - changed).total_seconds()
        if age_seconds < -900 or age_seconds > 6 * 86400:
            raise ValueError("Source price too old or in the future")
        buy = parse_amount(item.get("compra"), optional=True)
        sell = parse_amount(item.get("venta"))
        if buy is not None and buy > sell:
            raise ValueError("Buy price exceeds sell price")
        quotes[ticker] = {
            "buy": buy, "sell": sell, "updated": changed,
            "day": changed.astimezone(AR).date(),
        }
    if set(quotes) != set(TICKERS.values()):
        raise ValueError("Incomplete canonical seven-quote response")
    return quotes


def collect():
    response = requests.get(
        SOURCE, timeout=20,
        headers={"User-Agent": "EconomiaCriolla-EC021/1"},
    )
    response.raise_for_status()
    if len(response.content) > 300000:
        raise ValueError("Source payload exceeds size limit")
    return validate(response.json())


def plan(quotes, board, history, today):
    """Immutable-first-observed daily series and independently updated dashboard.

    Historical mismatches are reported, never updated. A historical record is
    only appended for a new source day that equals today's Argentina date.
    """
    if set(board) != set(quotes):
        raise ValueError("Board lacks required canonical tickers")
    desired_board = {}
    new_history = {}
    conflicts = []
    for ticker, quote in quotes.items():
        existing = board[ticker]
        recorded = existing[2]
        if recorded is None or quote["updated"] > recorded.astimezone(timezone.utc):
            desired_board[ticker] = quote
        key = (ticker, quote["day"])
        if key in history:
            if history[key] != (quote["buy"], quote["sell"]):
                conflicts.append(ticker)
        elif quote["day"] == today:
            new_history[ticker] = quote
    return desired_board, new_history, sorted(conflicts)


def run(*, check_db=False, apply=False):
    quotes = collect()
    today = datetime.now(AR).date()
    result = {
        "source": SOURCE, "quotes": len(quotes), "applied": False,
        "source_dates": {k: str(v["day"]) for k, v in sorted(quotes.items())},
        "mode": "source_checked",
    }
    if not apply and not check_db:
        return result
    dsn = os.getenv("EC021_DOLLAR_DB_DSN")
    if not dsn:
        raise RuntimeError("Dedicated PostgreSQL DSN missing")
    import psycopg
    with psycopg.connect(dsn, connect_timeout=15) as conn:
        with conn.cursor() as cur:
            if not apply:
                cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SELECT current_user")
            role = cur.fetchone()[0]
            if role != "ec021_dollar_writer":
                raise RuntimeError("Connection does not use the dedicated role")
            cur.execute(
                "SELECT id,buy_value,sell_value,last_updated "
                "FROM public.economic_indicators WHERE id=ANY(%s)",
                (list(quotes),),
            )
            board = {row[0]: row[1:] for row in cur.fetchall()}
            days = sorted({row["day"] for row in quotes.values()})
            cur.execute(
                "SELECT ticker,fecha,precio_compra,precio_venta "
                "FROM public.historial_cotizaciones "
                "WHERE ticker=ANY(%s) AND fecha=ANY(%s)",
                (list(quotes), days),
            )
            history = {(r[0], r[1]): (r[2], r[3]) for r in cur.fetchall()}
            updates, inserts, conflicts = plan(quotes, board, history, today)
            result.update({
                "db_role": role, "dashboard_updates_planned": len(updates),
                "history_inserts_planned": len(inserts),
                "history_existing_differences": conflicts,
            })
            if not apply:
                conn.rollback()
                result["mode"] = "authenticated_read_only"
                return result
            if os.getenv("EC021_DOLLAR_WRITES_ENABLED") != "true":
                raise RuntimeError("Write kill switch disabled")
            for ticker, quote in updates.items():
                cur.execute(
                    "UPDATE public.economic_indicators SET "
                    "buy_value=%s,sell_value=%s,last_updated=%s WHERE id=%s "
                    "AND (last_updated IS NULL OR last_updated<%s)",
                    (quote["buy"], quote["sell"], quote["updated"], ticker,
                     quote["updated"]),
                )
                if cur.rowcount != 1:
                    raise RuntimeError("Concurrent change in dashboard; rollback")
            for ticker, quote in inserts.items():
                cur.execute(
                    "INSERT INTO public.historial_cotizaciones "
                    "(fecha,ticker,precio_compra,precio_venta) "
                    "VALUES (%s,%s,%s,%s)",
                    (quote["day"], ticker, quote["buy"], quote["sell"]),
                )
            conn.commit()
            result["applied"] = bool(updates or inserts)
            result["mode"] = "atomic_append" if result["applied"] else "no_change"
            return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-db", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(check_db=args.check_db, apply=args.apply),
                     default=str, sort_keys=True))
