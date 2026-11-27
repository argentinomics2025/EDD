"""In-memory XLSX fixtures only: no real World Bank data or SQL operations."""
import datetime as dt
import io
import zipfile
import unittest
from xml.sax.saxutils import escape

from scripts.ec021_energy_worldbank import parse_monthly, SourceError, SOURCE_URL, LICENSE_URL

NOW = dt.date(2026, 11, 27)


def workbook(*, wrong_header=False, bad_price=False, incomplete=False, duplicate=False):
    months = []
    for i in range(24):
        yr = 2024 + (10 + i) // 12
        mon = (10 + i) % 12 + 1
        if incomplete and i == 23:
            continue
        price = "bad" if bad_price and i == 23 else str(75 + i)
        months.append((f"{yr}M{mon:02d}", price, str(70 + i), str(2.2 + i * 0.01)))
    if duplicate:
        months.append(months[-1])
    lines = [
        '<row r="6"><c r="A6" t="inlineStr"><is><t>Date</t></is></c>'
        '<c r="B6" t="inlineStr"><is><t>CRUDE_BRENT</t></is></c>'
        '<c r="C6" t="inlineStr"><is><t>CRUDE_WTI</t></is></c>'
        f'<c r="D6" t="inlineStr"><is><t>{"WRONG" if wrong_header else "NGAS_US"}</t></is></c></row>'
    ]
    for i, (date, brent, wti, gas) in enumerate(months, 7):
        lines.append(
            f'<row r="{i}"><c r="A{i}" t="inlineStr"><is><t>{escape(date)}</t></is></c>'
            f'<c r="B{i}"><v>{escape(brent)}</v></c>'
            f'<c r="C{i}"><v>{escape(wti)}</v></c>'
            f'<c r="D{i}"><v>{escape(gas)}</v></c></row>'
        )
    sheet = ('<?xml version="1.0" encoding="utf-8"?>'
             '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
             '<sheetData>' + "".join(lines) + '</sheetData></worksheet>')
    book = ('<?xml version="1.0"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Monthly Prices" sheetId="1" r:id="rId1"/></sheets></workbook>')
    rels = ('<?xml version="1.0"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Target="worksheets/sheet1.xml" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/>'
            '</Relationships>')
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/workbook.xml", book)
        z.writestr("xl/_rels/workbook.xml.rels", rels)
        z.writestr("xl/worksheets/sheet1.xml", sheet)
    return out.getvalue()


class WorldBankEnergyTests(unittest.TestCase):
    def test_valid_is_read_only_and_separate_from_yahoo(self):
        r = parse_monthly(workbook(), today=NOW)
        self.assertFalse(r["applied"])
        self.assertEqual(r["frequency"], "monthly")
        self.assertEqual(len(r["records"]), 3)
        self.assertEqual(r["history_months"], 24)
        self.assertEqual({x["asset"] for x in r["records"]},
                         {"brent_monthly_wb", "wti_monthly_wb", "gas_us_monthly_wb"})

    def test_licenses_are_explicit(self):
        r = parse_monthly(workbook(), today=NOW)
        self.assertIn("CC BY 4.0", r["dataset_license"])
        self.assertEqual(r["source_url"], SOURCE_URL)
        self.assertEqual(r["license_url"], LICENSE_URL)

    def test_stable_hash_for_identical_workbooks(self):
        self.assertEqual(parse_monthly(workbook(), today=NOW)["file_sha256"],
                         parse_monthly(workbook(), today=NOW)["file_sha256"])

    def test_reject_missing_gas(self):
        with self.assertRaises(SourceError):
            parse_monthly(workbook(wrong_header=True), today=NOW)

    def test_reject_nonnumeric(self):
        with self.assertRaises(SourceError):
            parse_monthly(workbook(bad_price=True), today=NOW)

    def test_reject_insufficient_history(self):
        with self.assertRaises(SourceError):
            parse_monthly(workbook(incomplete=True), today=NOW)

    def test_reject_duplicate_period(self):
        with self.assertRaises(SourceError):
            parse_monthly(workbook(duplicate=True), today=NOW)

    def test_reject_bogus_archive(self):
        with self.assertRaises(SourceError):
            parse_monthly(b"not xlsx", today=NOW)

    def test_reject_stale_workbook(self):
        with self.assertRaises(SourceError):
            parse_monthly(workbook(), today=dt.date(2027, 3, 27))

    def test_reject_incomplete_current_month(self):
        with self.assertRaises(SourceError):
            parse_monthly(workbook(), today=dt.date(2026, 10, 27))


if __name__ == "__main__":
    unittest.main()
