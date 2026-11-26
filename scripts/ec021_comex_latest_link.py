"""EC-021 COMEX. Deterministic, bounded discovery of official monthly ICA XLS.

No credentials; no database writes. Only filenames whose release month was
explicitly requested, on the exact official INDEC host. Never infer a series
from the landing page or substitute rounded press-release values.
"""
import argparse
from datetime import date
import hashlib
import json
import re
import ssl
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPRedirectHandler, HTTPSHandler

import xlrd

HOST = "https://www.indec.gob.ar"
PREFIX = HOST + "/ftp/cuadros/economia/ica_cuadros_"
LIMIT = 20 * 1024 * 1024
MAGIC = bytes.fromhex("d0cf11e0a1b11ae1")
MONTHS = ("Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
          "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre")

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        raise ValueError("Redirect forbidden for source XLS")

def candidates(release_month):
    """Fixed, conservative publication-day window, plausible dates first."""
    if not re.fullmatch(r"20\d{2}-(0[1-9]|1[0-2])", release_month):
        raise ValueError("Invalid report release month")
    year, month = map(int, release_month.split("-"))
    days = (19, 18, 20, 21, 17, 22, 23, 16, 24, 25, 26)
    return [f"{PREFIX}{day:02d}_{month:02d}_{year % 100:02d}.xls" for day in days]

def download(url, opener=None):
    if not url.startswith(PREFIX) or not re.fullmatch(
        r"https://www\.indec\.gob\.ar/ftp/cuadros/economia/ica_cuadros_\d{2}_\d{2}_\d{2}\.xls", url
    ):
        raise ValueError("Unapproved source URL")
    opener = opener or build_opener(NoRedirect(), HTTPSHandler(context=ssl.create_default_context()))
    try:
        with opener.open(Request(url, headers={"User-Agent":"EconomiaCriolla-COMEX-Official/1.0"}), timeout=12) as response:
            if response.geturl() != url:
                raise ValueError("Unexpected source redirect")
            body = response.read(LIMIT + 1)
    except HTTPError as ex:
        if ex.code == 404:
            return None
        raise
    if not body or len(body) > LIMIT or not body.startswith(MAGIC):
        raise ValueError("Invalid or oversized official XLS")
    return body

def read_values(body, expected_period):
    if not re.fullmatch(r"20\d{2}-(0[1-9]|1[0-2])", expected_period):
        raise ValueError("Invalid expected period")
    yy, mm = map(int, expected_period.split("-"))
    book = xlrd.open_workbook(file_contents=body, on_demand=True)
    if not set(("Índice", "c1", "c3", "c4")).issubset(book.sheet_names()):
        raise ValueError("ICA workbook schema changed")
    index = str(book.sheet_by_name("Índice").cell_value(0, 0))
    if f"{MONTHS[mm-1]} de {yy}" not in index:
        raise ValueError("Wrong ICA edition")
    # INDEC standard layout: c1[2025 Jan-Dec, 2026 Jan-Oct],
    # with year header in column A of January and period month in column B.
    def find_row(s):
        year = None
        matches = []
        for r in range(5, min(s.nrows, 80)):
            a = str(s.cell_value(r, 0)).strip()
            match = re.match(r"^(20\d{2})(?:\.0)?\*?$", a)
            if match:
                year = int(match.group(1))
            month = str(s.cell_value(r, 1)).strip().casefold()
            if year == yy and month == MONTHS[mm-1].casefold():
                matches.append(r)
        if len(matches) != 1:
            raise ValueError("ICA edition period missing/duplicate")
        return matches[0]
    from decimal import Decimal
    def D(s, r, c):
        value = s.cell_value(r, c)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Non numeric source value")
        return Decimal(str(value))
    c1,c3,c4 = (book.sheet_by_name(n) for n in ("c1","c3","c4"))
    a,b,d = (find_row(s) for s in (c1,c3,c4))
    export,imports,balance = D(c1,a,2),D(c1,a,4),D(c1,a,6)
    exg = [D(c3,b,i) for i in (3,4,5,6)]
    img = [D(c4,d,i) for i in (3,4,5,6,7,8)]
    other = D(c4,d,9)
    if not (export>0 and imports>0 and other>=0 and all(x>=0 for x in exg+img)):
        raise ValueError("Negative or empty source")
    # Imported decimals are rounded by Excel storage; use sub-cent USD million tolerance.
    tol=Decimal("0.00001")
    if any(abs(x)>tol for x in
       (export-imports-balance, sum(exg)-export, sum(img)+other-imports,
        D(c3,b,2)-export,D(c4,d,2)-imports)):
        raise ValueError("ICA c1/c3/c4 reconciliation failed")
    fields=("exportaciones_usd_millions","importaciones_usd_millions","saldo_usd_millions",
            "expo_primarios","expo_moa","expo_moi","expo_energia",
            "impo_bienes_capital","impo_bienes_intermedios","impo_combustibles",
            "impo_piezas_accesorios","impo_bienes_consumo","impo_vehiculos")
    values=[export,imports,balance,*exg,*img]
    return {"fecha":expected_period+"-01",
            **dict(zip(fields,(str(v) for v in values))),
            "impo_resto_unstored":str(other)}

def inspect(release_month):
    year,month=map(int,release_month.split("-"))
    period=(f"{year-1}-12" if month==1 else f"{year}-{month-1:02d}")
    failures=[]
    for url in candidates(release_month):
        try:
            body=download(url)
        except HTTPError as exc:
            failures.append({"url":url,"http_status":exc.code})
            continue
        if body is None:
            continue
        values=read_values(body,period)
        return {"status":"found_official_validated","url":url,
                "sha256":hashlib.sha256(body).hexdigest(),
                "period":period,"values":values,"writes_to_supabase":False}
    raise ValueError(f"No validated official ICA XLS for {period}; probed {len(candidates(release_month))} possible dates; failures={failures}")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--release-month",required=True)
    args=parser.parse_args()
    print(json.dumps(inspect(args.release_month),ensure_ascii=False,sort_keys=True))

if __name__ == "__main__":
    main()
