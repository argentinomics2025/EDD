"""EC-021: inventory official INDEC November 2026 XLS without writes or secrets."""
import hashlib
import json
import ssl
from urllib.request import Request, urlopen
from urllib.parse import urlsplit
import xlrd

URL = "https://www.indec.gob.ar/ftp/cuadros/economia/ica_cuadros_19_11_26.xls"
LIMIT = 20 * 1024 * 1024

def download(url=URL):
    if url != URL or urlsplit(url).scheme != "https":
        raise ValueError("Only approved official November INDEC XLS allowed")
    req = Request(url, headers={"User-Agent":"EconomiaCriolla-COMEX-XLSAudit/1.0"})
    with urlopen(req, timeout=40, context=ssl.create_default_context()) as response:
        if response.geturl() != url:
            raise ValueError("Redirect forbidden")
        data = response.read(LIMIT + 1)
    if not data or len(data) > LIMIT:
        raise ValueError("Unexpected XLS size")
    if not data.startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
        raise ValueError("Not a legacy binary XLS")
    return data

def preview(sheet, row):
    return [str(sheet.cell_value(row, c))[:90] for c in range(min(12, sheet.ncols))]

def main():
    data = download()
    book = xlrd.open_workbook(file_contents=data, on_demand=True)
    print(json.dumps({"source":URL,"sha256":hashlib.sha256(data).hexdigest(),"bytes":len(data),"sheet_count":book.nsheets,"writes_to_supabase":False}))
    for name in book.sheet_names():
        s = book.sheet_by_name(name)
        candidates = []
        for r in range(min(s.nrows, 2000)):
            row = preview(s, r)
            haystack = " ".join(row).lower()
            if "octubre" in haystack or "oct-26" in haystack or "2026-10" in haystack or "2026" in haystack and "oct" in haystack:
                candidates.append({"row_number":r+1,"values":row})
            if len(candidates) == 7:
                break
        print(json.dumps({"sheet":name,"rows":s.nrows,"cols":s.ncols,"header_preview":[{"row_number":r+1,"values":preview(s,r)} for r in range(min(7,s.nrows))],"october_candidates":candidates},ensure_ascii=False))
        book.unload_sheet(name)

if __name__=="__main__":
    main()
