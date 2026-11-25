"""EC-021: long-running read-only country-risk watcher.

No ingestion, no Supabase mutations and no right to redistribute EMBI data.
Uses the already-tested ArgentinaDatos and public Supabase read helpers.
"""
import json
from datetime import date, datetime, timedelta, timezone
import requests
from scripts.ec021_risk_country_readonly import (
    ATTRIBUTION, DATABASE_URL, PUBLIC_KEY, RIGHTS_STATUS,
    SOURCE_URL, RiskSourceError, fetch_json, parse_rows
)

def watch(*, http=requests, today=None):
    source_data, source_hash = fetch_json(SOURCE_URL, http=http)
    source = parse_rows(source_data, minimum=5)
    stored_data, stored_hash = fetch_json(
        DATABASE_URL, http=http,
        params={"select": "fecha,valor", "order": "fecha.desc", "limit": "30"},
        headers={"apikey": PUBLIC_KEY, "Accept": "application/json"}
    )
    stored = parse_rows(stored_data, minimum=5)
    today = today or datetime.now(timezone.utc).date()
    last_source = max(source)
    last_stored = max(stored)
    if date.fromisoformat(last_source) > today + timedelta(days=1):
        raise RiskSourceError("Future-dated source value")
    overlap = sorted(set(source) & set(stored), reverse=True)[:15]
    if len(overlap) < 5:
        raise RiskSourceError("Insufficient historical overlap")
    if any(source[d] != stored[d] for d in overlap):
        raise RiskSourceError("Historical mismatch; stop and review")
    if last_source < last_stored:
        raise RiskSourceError("Source behind the stored series")
    pending = sum(1 for d in source if d > last_stored)
    return {
        "status": "source_ahead_publication_blocked" if pending else "no_change",
        "source": SOURCE_URL,
        "attribution": ATTRIBUTION,
        "third_party_rights": RIGHTS_STATUS,
        "last_source_date": last_source,
        "last_stored_date": last_stored,
        "new_observations_count": pending,
        "checked_overlap_count": len(overlap),
        "source_sha256": source_hash,
        "db_snapshot_sha256": stored_hash,
        "mode": "read_only_watchdog",
        "writes_to_supabase": False,
        "publishes_to_website": False,
    }

if __name__ == "__main__":
    print(json.dumps(watch(), ensure_ascii=False, sort_keys=True))
