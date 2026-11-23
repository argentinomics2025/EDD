"""EC-021.5 / IPC: pure fail-closed monthly insert planner. NO database writes."""
from datetime import date
from decimal import Decimal, InvalidOperation


def _period(raw):
    if not isinstance(raw, str):
        raise ValueError("Period must be a string")
    try:
        d = date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("Invalid IPC period") from exc
    if d.isoformat() != raw or d.day != 1:
        raise ValueError("IPC period must be canonical YYYY-MM-01")
    return d


def _value(raw):
    if raw is None or isinstance(raw, bool):
        raise ValueError("Invalid IPC value")
    try:
        value = Decimal(str(raw))
    except InvalidOperation as exc:
        raise ValueError("Invalid IPC value") from exc
    if not value.is_finite() or not Decimal("-10") <= value <= Decimal("100"):
        raise ValueError("IPC value outside allowed bounds")
    return value


def _normalize(records, date_key, value_key):
    result = {}
    for row in records:
        period = _period(row[date_key])
        if period in result:
            raise ValueError("Duplicate IPC period")
        result[period] = _value(row[value_key])
    return result


def _next_month(d):
    return date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def plan_increment(source, stored_rows):
    """Return at most one new month, never updates. Caller MUST obtain DB snapshot."""
    if source.get("source") != "INDEC" or source.get("status") != "read_only_no_publication":
        raise ValueError("Unverified IPC source")
    if source.get("writes_to_supabase") is not False:
        raise ValueError("Source must be read-only")
    sha = source.get("sha256")
    if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError("Invalid SHA256")
    official = _normalize(source.get("latest", []), "date", "monthly_pct")
    stored = _normalize(stored_rows, "date", "value")
    if len(official) < 2 or not stored:
        raise ValueError("Insufficient observations")
    last_stored = max(stored)
    last_official = max(official)
    if last_stored not in official:
        raise ValueError("Latest stored month missing from source overlap")
    for period in set(official) & set(stored):
        if official[period] != stored[period]:
            raise ValueError(f"Historical revision needs approval: {period.isoformat()}")
    if last_official < last_stored:
        raise ValueError("Official source older than stored month")
    new_periods = sorted(d for d in official if d > last_stored)
    if len(new_periods) > 1:
        raise ValueError("Multi-month backfill needs manual approval")
    if new_periods and new_periods[0] != _next_month(last_stored):
        raise ValueError("Nonconsecutive new month")
    if any(d < last_stored and d not in stored for d in official):
        raise ValueError("Missing historical month requires investigation")
    additions = [{"date": d.isoformat(), "value": str(official[d])} for d in new_periods]
    return {"source_sha256": sha, "last_stored_month": last_stored.isoformat(),
            "last_official_month": last_official.isoformat(), "insert_only": additions,
            "status": "requires_authorized_writer" if additions else "no_change"}
