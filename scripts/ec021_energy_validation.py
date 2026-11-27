"""EC-021 Energía: validation boundary, without network or database writes.

Candidate source: EIA official daily *spot* series. This is NOT a futures feed.
The EIA API reader and an exclusive database writer remain separately gated.
This module intentionally cannot fetch Yahoo or connect to Supabase.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import re
from pathlib import Path

# New keys must not be silently mapped onto historic Yahoo futures keys.
EXPECTED = {
    "wti_spot_eia": "USD/barrel",
    "brent_spot_eia": "USD/barrel",
    "henry_hub_spot_eia": "USD/MMBtu",
}
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class EnergyValidationError(ValueError):
    pass


def validate_snapshot(payload: object, *, today: dt.date | None = None) -> dict:
    if not isinstance(payload, dict) or payload.get("source") != "EIA":
        raise EnergyValidationError("Source must be the official EIA")
    if payload.get("basis") != "spot":
        raise EnergyValidationError("Spot prices are not futures settlements")
    rows = payload.get("rows")
    if not isinstance(rows, list) or len(rows) != 3:
        raise EnergyValidationError("Require three independent asset observations")
    today = today or dt.datetime.now(dt.timezone.utc).date()
    validated = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise EnergyValidationError("Row must be an object")
        asset = row.get("asset")
        if not isinstance(asset, str) or asset not in EXPECTED or asset in seen:
            raise EnergyValidationError("Unknown or duplicated energy benchmark")
        seen.add(asset)
        if row.get("unit") != EXPECTED[asset]:
            raise EnergyValidationError("Wrong unit for energy benchmark")
        date_text = row.get("date")
        if not isinstance(date_text, str) or not ISO_DATE.fullmatch(date_text):
            raise EnergyValidationError("Invalid observation date")
        try:
            observation_date = dt.date.fromisoformat(date_text)
        except ValueError as exc:
            raise EnergyValidationError("Impossible observation date") from exc
        lag = (today - observation_date).days
        if lag < 0 or lag > 7:
            raise EnergyValidationError("Future or stale observation")
        raw = row.get("price")
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise EnergyValidationError("Price must be numeric")
        price = float(raw)
        if not math.isfinite(price) or price <= 0:
            raise EnergyValidationError("Invalid price")
        # One source date per observation; never use today's ingestion date.
        validated.append({"asset": asset, "date": date_text, "price": price, "unit": EXPECTED[asset]})
    if seen != set(EXPECTED):
        raise EnergyValidationError("Missing required assets")
    validated.sort(key=lambda row: row["asset"])
    encoded = json.dumps(validated, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "status": "validated_read_only",
        "source": "EIA",
        "basis": "spot",
        "records": validated,
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "applied": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True, help="Local EIA-shaped JSON fixture; no live fetch")
    args = parser.parse_args()
    report = validate_snapshot(json.loads(args.fixture.read_text(encoding="utf-8")))
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
