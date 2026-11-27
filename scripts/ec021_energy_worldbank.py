"""World Bank Pink Sheet monthly energy reference prices — READ ONLY.

Official XLSX (World Bank Commodity Markets), CC BY 4.0 dataset catalog:
https://datacatalog.worldbank.org/search/dataset/0038238/
These MONTHLY AVERAGES are NOT Yahoo Finance daily futures quotations.
No Supabase connection, no credentials, no writes, no fabricated fallbacks.
"""
from __future__ import annotations

import argparse
import calendar
import datetime as dt
import hashlib
import io
import json
import math
import re
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import PurePosixPath
from urllib.parse import urlparse

SOURCE_URL = (
    "https://thedocs.worldbank.org/en/doc/"
    "74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/"
    "related/CMO-Historical-Data-Monthly.xlsx"
)
LICENSE_URL = "https://datacatalog.worldbank.org/search/dataset/0038238/"
MAX_BYTES = 8_000_000
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      "p": "http://schemas.openxmlformats.org/package/2006/relationships"}
HEADERS = {
    "brent_monthly_wb": ({"CRUDE_BRENT", "OIL_BRENT", "CRUDE OIL, BRENT"}, "USD/barrel"),
    "wti_monthly_wb": ({"CRUDE_WTI", "OIL_WTI", "CRUDE OIL, WTI"}, "USD/barrel"),
    "gas_us_monthly_wb": ({"NGAS_US", "NATURAL GAS, U.S.", "NATURAL GAS, US"}, "USD/MMBtu"),
}
PERIOD = re.compile(r"^(20\d{2}|19\d{2})(?:M|[-/])(0[1-9]|1[0-2])$", re.I)
COL = re.compile(r"^([A-Z]+)\d+$")


class SourceError(ValueError):
    pass


def fetch_bytes(url: str = SOURCE_URL) -> bytes:
    if url != SOURCE_URL:
        raise SourceError("Unexpected World Bank resource URL")
    request = urllib.request.Request(url, headers={"User-Agent": "EconomiaCriolla-EC021/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            if urlparse(response.url).hostname != "thedocs.worldbank.org":
                raise SourceError("World Bank redirect hostname changed")
            data = response.read(MAX_BYTES + 1)
    except SourceError:
        raise
    except Exception:
        raise SourceError("Official XLSX download failed") from None
    if len(data) > MAX_BYTES or not zipfile.is_zipfile(io.BytesIO(data)):
        raise SourceError("Unexpected workbook format or size")
    return data


def _col_number(ref: str) -> int:
    m = COL.fullmatch(ref)
    if not m:
        raise SourceError("Invalid cell reference")
    result = 0
    for char in m.group(1):
        result = result * 26 + ord(char) - 64
    return result - 1


def _sheet_rows(data: bytes) -> list[dict[int, str]]:
    if not zipfile.is_zipfile(io.BytesIO(data)):
        raise SourceError("Not an XLSX archive")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        if len(z.namelist()) > 120 or sum(x.file_size for x in z.infolist()) > 35_000_000:
            raise SourceError("Workbook expansion limit")
        names = set(z.namelist())
        required = {"xl/workbook.xml", "xl/_rels/workbook.xml.rels"}
        if not required.issubset(names):
            raise SourceError("Missing workbook manifest")
        book = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        relmap = {r.get("Id"): r.get("Target") for r in rels}
        sheets = book.find("m:sheets", NS)
        if sheets is None:
            raise SourceError("No worksheets")
        named = [s for s in sheets if s.get("name") == "Monthly Prices"]
        if len(named) != 1:
            raise SourceError("Monthly Prices worksheet not found uniquely")
        rel = named[0].get("{" + NS["r"] + "}id")
        target = relmap.get(rel, "")
        if target.startswith("/"):
            path = target.lstrip("/")
        else:
            path = str(PurePosixPath("xl") / target)
        # Reject traversal in archive paths.
        if ".." in PurePosixPath(path).parts or path not in names:
            raise SourceError("Invalid worksheet path")
        shared = []
        if "xl/sharedStrings.xml" in names:
            strings = ET.fromstring(z.read("xl/sharedStrings.xml"))
            shared = ["".join(t.text or "" for t in si.iter("{" + NS["m"] + "}t"))
                      for si in strings]
        root = ET.fromstring(z.read(path))
        sheetdata = root.find("m:sheetData", NS)
        if sheetdata is None:
            raise SourceError("Missing price data")
        rows: list[dict[int, str]] = []
        for row in sheetdata.findall("m:row", NS):
            cells = {}
            for c in row.findall("m:c", NS):
                ref = c.get("r", "")
                ci = _col_number(ref)
                if ci > 130:
                    raise SourceError("Excessive worksheet width")
                typ = c.get("t")
                v = c.find("m:v", NS)
                if typ == "inlineStr":
                    value = "".join(t.text or "" for t in c.iter("{" + NS["m"] + "}t"))
                elif v is None or v.text is None:
                    continue
                elif typ == "s":
                    try:
                        value = shared[int(v.text)]
                    except (ValueError, IndexError):
                        raise SourceError("Bad shared string") from None
                else:
                    value = v.text
                cells[ci] = value.strip()
            if cells:
                rows.append(cells)
        return rows


def parse_monthly(data: bytes, *, today: dt.date | None = None) -> dict:
    today = today or dt.datetime.now(dt.timezone.utc).date()
    rows = _sheet_rows(data)
    if len(rows) < 15:
        raise SourceError("Insufficient monthly observations")
    mapping = None
    for row in rows[:14]:
        columns = {}
        for col, value in row.items():
            canonical = re.sub(r"\s+", " ", value.strip()).upper()
            for asset, (names, unit) in HEADERS.items():
                if canonical in names:
                    if asset in columns:
                        raise SourceError("Duplicated commodity column")
                    columns[asset] = (col, unit)
        if len(columns) == 3:
            mapping = columns
            break
    if mapping is None:
        raise SourceError("Missing official Brent/WTI/U.S. natural gas headings")
    months = {}
    for row in rows:
        period = row.get(0, "")
        m = PERIOD.fullmatch(period)
        if not m:
            continue
        year, month = int(m.group(1)), int(m.group(2))
        if dt.date(year, month, 1) > dt.date(today.year, today.month, 1):
            raise SourceError("Future monthly price period")
        items = []
        for asset, (col, unit) in mapping.items():
            raw = row.get(col, "")
            try:
                price = float(raw)
            except (ValueError, TypeError):
                raise SourceError("Missing or nonnumeric monthly reference price") from None
            if not math.isfinite(price) or price <= 0:
                raise SourceError("Invalid monthly reference price")
            items.append({"asset": asset, "period": f"{year:04d}-{month:02d}",
                          "value": price, "unit": unit})
        period_key = (year, month)
        if period_key in months:
            raise SourceError("Duplicated month")
        months[period_key] = sorted(items, key=lambda x: x["asset"])
    if len(months) < 24:
        raise SourceError("Less than 24 complete months")
    last = max(months)
    lag = (today.year - last[0]) * 12 + today.month - last[1]
    if lag < 1 or lag > 3:
        raise SourceError("Workbook is too old or includes an incomplete month")
    latest = months[last]
    digest = hashlib.sha256(data).hexdigest()
    return {
        "status": "source_validated_no_write",
        "dataset": "World Bank Commodity Price Data (Pink Sheet)",
        "source_url": SOURCE_URL,
        "dataset_license": "CC BY 4.0 (subject to dataset metadata and third-party exceptions)",
        "license_url": LICENSE_URL,
        "frequency": "monthly",
        "period": f"{last[0]:04d}-{last[1]:02d}",
        "records": latest,
        "history_months": len(months),
        "file_sha256": digest,
        "applied": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-source", action="store_true")
    parser.add_argument("--fixture", type=str)
    args = parser.parse_args()
    if args.fixture:
        from pathlib import Path
        data = Path(args.fixture).read_bytes()
    elif args.check_source:
        data = fetch_bytes()
    else:
        parser.error("Specify --check-source or --fixture")
    print(json.dumps(parse_monthly(data), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
