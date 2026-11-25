"""EC-021: audit a single source observation before any manual approval-based load.

Read-only, checks overlap and returns only the next pending observation.
"""
import json
from datetime import datetime, timezone
import requests
from scripts.ec021_risk_country_readonly import (
  SOURCE_URL, DATABASE_URL, PUBLIC_KEY, fetch_json, parse_rows, RiskSourceError
)

def inspect(http=requests):
  raw, source_sha = fetch_json(SOURCE_URL, http=http)
  source = parse_rows(raw, minimum=5)
  db_raw, db_sha = fetch_json(DATABASE_URL, http=http,
      params={"select":"fecha,valor", "order":"fecha.desc", "limit":"30"},
      headers={"apikey":PUBLIC_KEY,"Accept":"application/json"})
  stored = parse_rows(db_raw, minimum=5)
  latest = max(stored)
  overlap = set(source) & set(stored)
  if len(overlap) < 15:
      raise RiskSourceError("Insufficient overlap for update")
  conflict = [d for d in overlap if source[d] != stored[d]]
  if conflict:
      raise RiskSourceError("Historical mismatches, blocked: " + str(len(conflict)))
  pending = sorted(d for d in source if d > latest)
  if len(pending) > 1:
      raise RiskSourceError("More than one missing date: manual review")
  if pending and pending[0] > datetime.now(timezone.utc).date().isoformat():
      raise RiskSourceError("Future observation")
  return {"status":"single_new_observation" if pending else "no_change",
          "date":pending[0] if pending else None,
          "value":source[pending[0]] if pending else None,
          "last_stored":latest,"checked_overlap":len(overlap),
          "source_sha256":source_sha,"db_sha256":db_sha,
          "mode":"preflight_read_only","writes":False}

if __name__ == "__main__":
    print(json.dumps(inspect(),sort_keys=True))
