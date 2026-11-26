"""Read-only Dólar freshness check for the legacy-to-dedicated cutover.

Never writes to Supabase. It avoids false alerts from normal intraday drift:
a new source timestamp may be up to twelve hours ahead of the stored board.
"""
import json
from datetime import datetime, timezone
from decimal import Decimal
from scripts.ec021_dollar_safe_writer import collect, TICKERS
from scripts.ec021_dollar_readonly_audit import read_json, DB, KEY


def evaluate(source, db, *, max_lag_hours=12):
    if not isinstance(db, list):
        raise ValueError("Invalid dashboard response")
    board = {}
    allowed = set(TICKERS.values())
    for record in db:
        ticker = record.get("id")
        if ticker not in allowed:
            continue
        if ticker in board:
            raise ValueError("Duplicate dashboard ticker")
        raw = record.get("last_updated")
        if not isinstance(raw, str):
            raise ValueError("Missing dashboard timestamp")
        date = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if date.tzinfo is None:
            raise ValueError("Naive dashboard timestamp")
        board[ticker] = date.astimezone(timezone.utc)
    if set(board) != allowed:
        raise ValueError("Incomplete seven-ticker dashboard")
    lag_hours = {
        ticker: round((quote["updated"] - board[ticker]).total_seconds() / 3600, 2)
        for ticker, quote in sorted(source.items())
    }
    behind = sorted(ticker for ticker, lag in lag_hours.items() if lag > max_lag_hours)
    return {
        "mode": "read_only_health",
        "checked_tickers": len(source),
        "lag_hours": lag_hours,
        "stale_dashboard_tickers": behind,
        "status": "stale_dashboard" if behind else "healthy",
        "writes_to_supabase": False,
    }


def run():
    source = collect()
    stored = read_json(
        DB,
        params={"select": "id,buy_value,sell_value,last_updated", "id": "like.dolar-*", "limit": "20"},
        headers={"apikey": KEY, "Accept": "application/json"},
    )
    return evaluate(source, stored)


if __name__ == "__main__":
    report = run()
    print(json.dumps(report, sort_keys=True))
    if report["status"] != "healthy":
        raise SystemExit("Dollar dashboard remains >12h behind source; see issue #33")
