"""EC-021 risk-country: source and DB validation only. No write functionality.

Data provider: ArgentinaDatos; its upstream source: Ambito; index: JP Morgan EMBI.
Attribution is necessary but does NOT grant third-party redistribution rights.
"""
import hashlib
import json
from datetime import date, timedelta, timezone, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

import requests

SOURCE_URL = "https://api.argentinadatos.com/v1/finanzas/indices/riesgo-pais"
DATABASE_URL = "https://fvyzacodrrmlxgzhneyt.supabase.co/rest/v1/historial_riesgo_pais"
PUBLIC_KEY = "sb_publishable_32r2WZE28EI-O4aIP1D4Mw_fnwZ826j"
ATTRIBUTION = "Fuente: ArgentinaDatos, sobre datos de Ámbito. Índice EMBI de J.P. Morgan."
RIGHTS_STATUS = "third_party_redistribution_not_verified"
MAX_BYTES = 5_000_000


class RiskSourceError(ValueError):
    pass


def parse_rows(data, *, minimum=1):
    if not isinstance(data, list) or not minimum <= len(data) < 100_000:
        raise RiskSourceError("Invalid or empty risk-country series")
    records = {}
    for row in data:
        if not isinstance(row, dict) or set(("fecha", "valor")) - row.keys():
            raise RiskSourceError("Missing source fields")
        if not isinstance(row["fecha"], str):
            raise RiskSourceError("Invalid date type")
        try:
            d = date.fromisoformat(row["fecha"])
            value = Decimal(str(row["valor"]))
        except (TypeError, ValueError, InvalidOperation) as e:
            raise RiskSourceError("Invalid date or value") from e
        if not value.is_finite() or value != value.to_integral_value() or not 50 <= value <= 10000:
            raise RiskSourceError("Out-of-bounds country-risk points")
        key = d.isoformat()
        if key in records:
            raise RiskSourceError("Duplicate risk-country date")
        records[key] = int(value)
    return records


def fetch_json(url, *, http=requests, params=None, headers=None):
    host = urlparse(url)
    if host.scheme != "https" or host.hostname not in (
        "api.argentinadatos.com", "fvyzacodrrmlxgzhneyt.supabase.co"
    ):
        raise RiskSourceError("Source host not allowlisted")
    response = http.get(url, params=params, headers=headers, timeout=25)
    response.raise_for_status()
    if len(response.content) > MAX_BYTES:
        raise RiskSourceError("Oversized response")
    return response.json(), hashlib.sha256(response.content).hexdigest()


def monitor(*, http=requests, today=None):
    raw, source_hash = fetch_json(SOURCE_URL, http=http)
    official = parse_rows(raw, minimum=5)
    stored_raw, db_hash = fetch_json(
        DATABASE_URL, http=http,
        params={"select": "fecha,valor", "order": "fecha.desc", "limit": "30"},
        headers={"apikey": PUBLIC_KEY, "Accept": "application/json"}
    )
    stored = parse_rows(stored_raw, minimum=5)
    now = today or datetime.now(timezone.utc).date()
    source_latest = max(official)
    db_latest = max(stored)
    if date.fromisoformat(source_latest) > now + timedelta(days=1):
        raise RiskSourceError("Future-dated source observation")
    overlap = sorted(set(official) & set(stored), reverse=True)
    if len(overlap) < 5:
        raise RiskSourceError("Insufficient source/DB historical overlap")
    mismatches = [d for d in overlap[:15] if official[d] != stored[d]]
    if mismatches:
        raise RiskSourceError("Historical discrepancy, manual review required: " + ", ".join(mismatches[:5]))
    if source_latest < db_latest:
        raise RiskSourceError("Data provider behind DB; cannot reconcile safely")
    new = sorted(d for d in official if d > db_latest)
    # Read-only mode may accumulate a long backlog while publication rights are pending.
    # Never fail solely because there are more than seven unpublishable observations.
    return {
        "status": "no_change" if not new else "source_ahead_publication_blocked",
        "mode": "read_only_monitor",
        "source": SOURCE_URL,
        "attribution": ATTRIBUTION,
        "third_party_rights": RIGHTS_STATUS,
        "last_source_date": source_latest,
        "last_stored_date": db_latest,
        "new_observations_count": len(new),
        "source_sha256": source_hash,
        "db_snapshot_sha256": db_hash,
        "checked_overlap_count": len(overlap[:15]),
        "writes_to_supabase": False,
        "publishes_to_website": False,
    }


if __name__ == "__main__":
    print(json.dumps(monitor(), ensure_ascii=False, sort_keys=True))
