"""EC-021 Etapa 3: monitor RIPTE oficial, EXCLUSIVAMENTE lectura.

No Supabase imports, credentials, DELETE, UPDATE, UPSERT or INSERT.
The existing salary table has conflicting January 2026 rows. Never auto-reconcile.
"""
import hashlib
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

SOURCE_URL = "https://www.argentina.gob.ar/trabajo/seguridadsocial/ripte"
MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5,
    "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9,
    "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}
PERIOD = re.compile(r"^([A-Za-zÁÉÍÓÚáéíóú]+)\s*/\s*(20\d{2})$")
PERCENT = re.compile(r"^([+-]?\d{1,3}(?:[.,]\d{1,2})?)\s*%?$")


class RipteValidationError(ValueError):
    """A source or historical mismatch must stop publication."""


def parse_official(html):
    soup = BeautifulSoup(html, "html.parser")
    matching = []
    for table in soup.find_all("table"):
        head = " ".join(table.stripped_strings).lower()
        if "variación respecto mes anterior" in head or "variacion respecto mes anterior" in head:
            matching.append(table)
    if len(matching) != 1:
        raise RipteValidationError("Expected exactly one official RIPTE monthly-variation table")
    table = matching[0]
    records = {}
    for tr in table.select("tr"):
        cells = tr.find_all("td", recursive=False)
        if not cells:
            continue
        if len(cells) < 3:
            raise RipteValidationError("Incomplete RIPTE table row")
        raw_month = cells[0].get_text(" ", strip=True).lower()
        m = PERIOD.fullmatch(raw_month)
        if not m or m.group(1) not in MONTHS:
            raise RipteValidationError("Unexpected RIPTE month label: " + raw_month[:30])
        d = date(int(m.group(2)), MONTHS[m.group(1)], 1).isoformat()
        pct = cells[2].get_text(" ", strip=True)
        match = PERCENT.fullmatch(pct)
        if not match:
            raise RipteValidationError("Invalid or missing monthly percentage for " + d)
        try:
            value = Decimal(match.group(1).replace(",", "."))
        except InvalidOperation as exc:
            raise RipteValidationError("Invalid numeric percentage") from exc
        if not value.is_finite() or not Decimal("-50") <= value <= Decimal("100"):
            raise RipteValidationError("Out-of-bounds percentage")
        if d in records:
            raise RipteValidationError("Duplicate official RIPTE period " + d)
        records[d] = value
    if len(records) < 12:
        raise RipteValidationError("Official page has too few monthly observations")
    latest = max(records)
    if date.fromisoformat(latest).year < 2026:
        raise RipteValidationError("Official page stale")
    return [{"fecha": k, "var_ripte_mensual": str(records[k])} for k in sorted(records)]


def validate_existing(official, stored):
    """Return at most one NEW consecutive month; abort on any ambiguity.
    
    stored must include ALL periods in production, not a truncated range.
    No mutation is implemented here.
    """
    mapping = {}
    for row in stored:
        period = str(row["fecha"])
        if period in mapping:
            raise RipteValidationError("Duplicate stored RIPTE period " + period)
        mapping[period] = Decimal(str(row["var_ripte_mensual"]))
    official_map = {x["fecha"]: Decimal(x["var_ripte_mensual"]) for x in official}
    if not mapping:
        raise RipteValidationError("Empty production overlap")
    overlap = set(mapping) & set(official_map)
    if len(overlap) < 2:
        raise RipteValidationError("Insufficient historical overlap")
    for period in sorted(overlap):
        if mapping[period] != official_map[period]:
            raise RipteValidationError("Historical revision requires manual decision: " + period)
    last_stored = max(mapping)
    missing = sorted(p for p in official_map if p > last_stored)
    if len(missing) > 1:
        raise RipteValidationError("Multiple months pending: requires approval")
    if missing:
        previous = date.fromisoformat(last_stored)
        expected_year = previous.year + (previous.month == 12)
        expected_month = previous.month % 12 + 1
        if missing[0] != date(expected_year, expected_month, 1).isoformat():
            raise RipteValidationError("Unexpected gap in RIPTE periods")
    return [{"fecha": p, "var_ripte_mensual": str(official_map[p])} for p in missing]


def main():
    # Enforce HTTPS, certificate verification (requests default), bounded response.
    parsed = urlparse(SOURCE_URL)
    if parsed.scheme != "https" or parsed.hostname != "www.argentina.gob.ar":
        raise RipteValidationError("Untrusted source host")
    response = requests.get(SOURCE_URL, timeout=25,
                            headers={"User-Agent": "EconomiaCriolla-RIPTE-readonly/1.0"})
    response.raise_for_status()
    if len(response.content) > 3_000_000:
        raise RipteValidationError("Unexpected source size")
    rows = parse_official(response.text)
    print(json.dumps({
        "source": SOURCE_URL,
        "sha256": hashlib.sha256(response.content).hexdigest(),
        "mode": "read_only_no_publication",
        "latest": rows[-1],
        "observations": len(rows),
        "writes_to_supabase": False,
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
