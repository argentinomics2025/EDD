"""Read both official INDEC daily CVS series from the published XLS workbook.

The registered and total salary series are distinct and must not be spliced.
No data is written to a database.
"""
import calendar
import hashlib
import re
from datetime import date, timedelta
from decimal import Decimal

import xlrd

SOURCE = "https://www.indec.gob.ar/ftp/cuadros/sociedad/sh_cvs_diarios_2026.xls"
SHEETS = {"publicacion_IS": "cvs_total", "publicacion_SR": "cvs_registrado"}
MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre")

def parse(raw, source=SOURCE):
    book = xlrd.open_workbook(file_contents=raw)
    if set(book.sheet_names()) != set(SHEETS):
        raise ValueError("Unexpected CVS sheets")
    output = {}
    for sheet_name, series in SHEETS.items():
        sheet = book.sheet_by_name(sheet_name)
        if "31 de octubre de 2016" not in str(sheet.cell_value(1, 0)):
            raise ValueError("Unexpected CVS base")
        rows = {}
        years = set()
        for i in range(sheet.nrows):
            head = str(sheet.cell_value(i, 1))
            match = re.fullmatch(r"A.o\s+(\d{4})", head)
            if not match:
                continue
            year = int(match.group(1))
            if year in years or i + 32 >= sheet.nrows:
                raise ValueError("Invalid CVS year block")
            years.add(year)
            for month, expected in enumerate(MONTHS, 1):
                cell = sheet.cell(i + 1, month)
                if cell.value == "":
                    if any(sheet.cell_value(i + 1 + d, month) != "" for d in range(1, 32)):
                        raise ValueError("Values under an empty month header")
                elif cell.ctype == xlrd.XL_CELL_DATE:
                    y, m, *_ = xlrd.xldate_as_tuple(cell.value, book.datemode)
                    if (y, m) != (year, month):
                        raise ValueError("Wrong CVS month date")
                elif str(cell.value).strip().lower() != expected:
                    raise ValueError("Unexpected CVS month headers")
            for day in range(1, 32):
                row = i + 1 + day
                if sheet.cell_value(row, 0) != day:
                    raise ValueError("Unexpected CVS day row")
                for month in range(1, 13):
                    cell = sheet.cell(row, month)
                    if cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK) or cell.value == "":
                        continue
                    if cell.ctype != xlrd.XL_CELL_NUMBER or day > calendar.monthrange(year, month)[1]:
                        raise ValueError("Invalid CVS cell")
                    d = date(year, month, day)
                    v = Decimal(str(cell.value))
                    if d in rows or not v.is_finite() or v <= 0:
                        raise ValueError("Invalid CVS observation")
                    rows[d] = v
        dates = sorted(rows)
        if not dates or any(b-a != timedelta(days=1) for a, b in zip(dates, dates[1:])):
            raise ValueError("CVS daily history has gaps")
        output[series] = [{"date": d.isoformat(), "value": str(rows[d])} for d in dates]
    return {"source": source, "sha256": hashlib.sha256(raw).hexdigest(),
            "frequency": "daily", "unit": "index", "base": "2016-10-31=100",
            "series": output, "writes_to_supabase": False}
