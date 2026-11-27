"""Read official EIA *spot* energy observations, never write a database.

Requires EC021_EIA_API_KEY in GitHub environment secret. No fallback to Yahoo
Finance, no fabricated values, and no mapping to historic futures asset keys.
This is an opt-in, read-only probe: no cron and no database credentials.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from scripts.ec021_energy_validation import EnergyValidationError, validate_snapshot

BASE = "https://api.eia.gov/v2/"
ROUTES = (
    ("petroleum/pri/spt/data/", {"RWTC": ("wti_spot_eia", "USD/barrel"), "RBRTE": ("brent_spot_eia", "USD/barrel")}),
    ("natural-gas/pri/fut/data/", {"RNGWHHD": ("henry_hub_spot_eia", "USD/MMBtu")}),
)


def parse_eia_response(body: object, series: dict[str, tuple[str, str]]) -> list[dict[str, Any]]:
    if not isinstance(body, dict) or not isinstance(body.get("response"), dict):
        raise EnergyValidationError("Missing EIA response object")
    raw = body["response"].get("data")
    if not isinstance(raw, list) or not raw:
        raise EnergyValidationError("Empty EIA result")
    latest: dict[str, dict[str, Any]] = {}
    for item in raw:
        if not isinstance(item, dict) or item.get("series") not in series:
            raise EnergyValidationError("Unexpected EIA series")
        key = item["series"]
        day = item.get("period")
        if not isinstance(day, str) or len(day) != 10:
            raise EnergyValidationError("Expected daily EIA observation")
        try:
            dt.date.fromisoformat(day)
        except ValueError as exc:
            raise EnergyValidationError("Invalid date from EIA") from exc
        price = item.get("value")
        if isinstance(price, bool) or not isinstance(price, (str, int, float)):
            raise EnergyValidationError("Missing numeric EIA value")
        try:
            value = float(price)
        except (ValueError, TypeError) as exc:
            raise EnergyValidationError("Missing numeric EIA value") from exc
        if not math.isfinite(value) or value <= 0:
            raise EnergyValidationError("Invalid EIA observation value")
        asset, unit = series[key]
        row = {"asset": asset, "date": day, "price": value, "unit": unit}
        if asset not in latest or day > latest[asset]["date"]:
            latest[asset] = row
    if len(latest) != len(series):
        raise EnergyValidationError("Partial EIA series response")
    return list(latest.values())


def make_url(route: str, series: dict[str, tuple[str, str]], key: str) -> str:
    if route not in {entry[0] for entry in ROUTES} or not key.strip():
        raise EnergyValidationError("Route or API key missing")
    pairs = [
        ("api_key", key), ("frequency", "daily"), ("data[0]", "value"),
        ("sort[0][column]", "period"), ("sort[0][direction]", "desc"),
        ("offset", "0"), ("length", "8"),
    ]
    for code in series:
        pairs.append(("facets[series][]", code))
    return BASE + route + "?" + urlencode(pairs)


def read_eia(*, api_key: str, today: dt.date | None = None, fetch=None) -> dict:
    if not api_key.strip():
        raise EnergyValidationError("EC021_EIA_API_KEY missing")
    if fetch is None:
        def fetch(url: str) -> object:
            # Do not print URL or underlying exceptions: the URL contains the key.
            try:
                req = Request(url, headers={"Accept": "application/json", "User-Agent": "EconomiaCriolla-EC021/1.0"})
                with urlopen(req, timeout=20) as response:
                    data = response.read(262145)
                if len(data) > 262144:
                    raise EnergyValidationError("EIA response too large")
                return json.loads(data.decode("utf-8"))
            except Exception:
                raise EnergyValidationError("EIA network or parsing failure") from None
    rows = []
    for route, series in ROUTES:
        response = fetch(make_url(route, series, api_key))
        rows.extend(parse_eia_response(response, series))
    return validate_snapshot({"source": "EIA", "basis": "spot", "rows": rows}, today=today)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-source", action="store_true", required=True)
    parser.parse_args()
    report = read_eia(api_key=os.environ.get("EC021_EIA_API_KEY", ""))
    # Do not output a key, HTTP request URL or unvalidated upstream payload.
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
