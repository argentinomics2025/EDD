"""EC-021.5 IPC: gated INSERT-only writer. NOT scheduled or authorized for production.

No schema migration, no secret values, no historical updates.
The live robot is deliberately disabled pending DEC-003 and dedicated credential.
"""
import argparse
import json
import os
from decimal import Decimal

import requests

from scripts.ec0215_indec_ipc_nacional import read_official_csv, parse_national_monthly
from scripts.ec0215_ipc_insert_plan import plan_increment

EXPECTED_DB = "https://fvyzacodrrmlxgzhneyt.supabase.co"
APPROVAL = "IPC_INSERT_ONLY_APPROVED"


def _client(url, key):
    if url.rstrip("/") != EXPECTED_DB:
        raise ValueError("Refusing to access another Supabase project")
    if not key or not isinstance(key, str):
        raise ValueError("Missing Supabase credential")
    headers = {"apikey": key, "Accept": "application/json", "Content-Type": "application/json"}
    if key.startswith("eyJ"):
        headers["Authorization"] = "Bearer " + key
    return EXPECTED_DB + "/rest/v1/datos_inflacion", headers


def _recent(endpoint, headers, http=requests):
    response = http.get(endpoint, params={"select": "date,value", "order": "date.desc", "limit": "4"},
                        headers=headers, timeout=15)
    response.raise_for_status()
    rows = response.json()
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("Inflation table unavailable")
    return rows


def inspect_and_maybe_apply(source, *, url, read_key, write_key=None, apply=False, http=requests):
    read_endpoint, read_headers = _client(url, read_key)
    snapshot = _recent(read_endpoint, read_headers, http)
    plan = plan_increment(source, snapshot)
    if not apply or not plan["insert_only"]:
        return {**plan, "applied": False}
    if os.environ.get("EC0215_PRODUCTION_APPROVAL") != APPROVAL:
        raise RuntimeError("EC0215 production writer remains disabled")
    endpoint, write_headers = _client(url, write_key)
    row = plan["insert_only"][0]
    # PostgREST: one atomic INSERT / ON CONFLICT DO NOTHING; never updates history.
    headers = {**write_headers, "Prefer": "resolution=ignore-duplicates,return=representation"}
    response = http.post(endpoint, params={"on_conflict": "date"}, data=json.dumps([row]),
                         headers=headers, timeout=15)
    response.raise_for_status()
    after = _recent(endpoint, write_headers, http)
    matched = [r for r in after if r.get("date") == row["date"]]
    if len(matched) != 1 or Decimal(str(matched[0]["value"])) != Decimal(row["value"]):
        raise RuntimeError("IPC post-insert mismatch or competing writer; requires review")
    return {**plan, "applied": True}


def main():
    parser = argparse.ArgumentParser(description="IPC new-month reader or guarded writer")
    parser.add_argument("--apply", action="store_true", help="Not enabled until authorized")
    args = parser.parse_args()
    if args.apply and os.environ.get("EC0215_PRODUCTION_APPROVAL") != APPROVAL:
        raise RuntimeError("EC0215 production write not approved")
    source = parse_national_monthly(read_official_csv())
    plan = inspect_and_maybe_apply(source,
                                  url=os.environ["SUPABASE_URL"],
                                  read_key=os.environ["EC0215_IPC_READ_KEY"],
                                  write_key=os.environ.get("EC0215_IPC_WRITE_KEY"),
                                  apply=args.apply)
    print(json.dumps(plan, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
