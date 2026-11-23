"""EC-021.5: official INDEC national level-general monthly IPC, READ ONLY."""
import csv
import hashlib
import io
import json
import re
import ssl
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

URL = "https://www.indec.gob.ar/ftp/cuadros/economia/serie_ipc_divisiones.csv"
ALLOWED = frozenset({"indec.gob.ar", "www.indec.gob.ar"})
LIMIT = 10 * 1024 * 1024
COLUMNS = {"Codigo", "Descripcion", "Clasificador", "Periodo", "Indice_IPC", "v_m_IPC", "v_i_a_IPC", "Region"}


def official_url(url):
    parsed = urlsplit(url)
    return parsed.scheme == "https" and parsed.hostname in ALLOWED and not parsed.username and not parsed.password


class SafeRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not official_url(newurl):
            raise ValueError("INDEC redirected outside official HTTPS hosts")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def read_official_csv(url=URL):
    if not official_url(url):
        raise ValueError("Unapproved INDEC URL")
    opener = build_opener(SafeRedirects(), HTTPSHandler(context=ssl.create_default_context()))
    req = Request(url, headers={"User-Agent": "EconomiaCriolla-INDEC-IPC-ReadOnly/1.0"})
    with opener.open(req, timeout=20) as response:
        if not official_url(response.geturl()):
            raise ValueError("Redirected outside official host")
        data = response.read(LIMIT + 1)
        if response.headers.get("Content-Type", "").split(";")[0].lower() in {"text/html", "application/pdf"}:
            raise ValueError("INDEC response is not CSV")
    if not data or len(data) > LIMIT or b"\\x00" in data:
        raise ValueError("Invalid CSV payload")
    return data


def parse_national_monthly(data):
    if not data or len(data) > LIMIT or b"\\x00" in data:
        raise ValueError("Invalid CSV payload")
    try:
        decoded = data.decode("utf-8-sig")
        encoding = "utf-8-sig"
    except UnicodeDecodeError:
        decoded = data.decode("cp1252", errors="strict")
        encoding = "cp1252"
    lines = decoded.splitlines()
    if len(lines) < 2:
        raise ValueError("CSV has no data")
    dialect = csv.Sniffer().sniff("\\n".join(lines[:5]), delimiters=",;\\t")
    reader = csv.DictReader(io.StringIO(decoded), dialect=dialect)
    if not COLUMNS.issubset(set(reader.fieldnames or [])):
        raise ValueError("Official INDEC schema changed")
    rows = {}
    for row in reader:
        if not (row["Codigo"].strip() == "0"
                and row["Descripcion"].strip().casefold() == "nivel general"
                and row["Clasificador"].strip() == "Nivel general y divisiones COICOP"
                and row["Region"].strip().casefold() == "nacional"):
            continue
        raw_period = row["Periodo"].strip()
        if not re.fullmatch(r"20\\d{4}", raw_period):
            raise ValueError("Unexpected national IPC period")
        period = date(int(raw_period[:4]), int(raw_period[4:]), 1).isoformat()
        if period in rows:
            raise ValueError("Duplicate national IPC period: " + period)
        raw_value = row["v_m_IPC"].strip()
        if raw_value.upper() == "NA":
            val = None
        else:
            try:
                val = Decimal(raw_value.replace(",", "."))
            except InvalidOperation as exc:
                raise ValueError("Invalid IPC monthly value: " + period) from exc
            if not val.is_finite():
                raise ValueError("Nonfinite IPC monthly value")
        rows[period] = val
    if not rows:
        raise ValueError("National level-general IPC missing")
    periods = sorted(rows)
    if rows[periods[-1]] is None:
        raise ValueError("Latest IPC monthly change unavailable")
    return {"source": "INDEC", "source_url": URL, "sha256": hashlib.sha256(data).hexdigest(),
            "encoding": encoding, "series_length": len(periods),
            "latest": [{"date": p, "monthly_pct": str(rows[p]) if rows[p] is not None else None}
                       for p in periods[-4:]],
            "status": "read_only_no_publication", "writes_to_supabase": False}


if __name__ == "__main__":
    print(json.dumps(parse_national_monthly(read_official_csv()), ensure_ascii=False, sort_keys=True))
