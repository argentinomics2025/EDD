"""EC021 ISAC monthly: fail-closed parser and guardrails, synthetic fixtures."""
import csv
import io
import json
import unittest
from datetime import date
from decimal import Decimal

from scripts.ec021_isac_monthly import (
    FIELDS, SOURCE_COLUMNS, START, compare_published, dec, month_after,
    month_before, target_month, parse_index, parse_inputs, source_report
)

class TestISACMonthly(unittest.TestCase):
    def test_publication_lag_two_months(self):
        self.assertEqual(target_month("2026-12"),date(2026,10,1))
        self.assertEqual(target_month("2027-01"),date(2026,11,1))
        self.assertEqual(target_month("2026-11"),date(2026,9,1))
    def test_month_math(self):
        self.assertEqual(month_before("2027-01"),date(2026,12,1))
        self.assertEqual(month_after(date(2026,12,1)),date(2027,1,1))
    def test_incorrect_or_nonfinite_values_rejected(self):
        for x in ["NaN", "Infinity", "-1", "0"]:
            with self.assertRaises(ValueError):dec(x)
    def test_adjusted_source_with_duplicate_month_rejected(self):
        rows=[["2024-01-01",100+i] for i in range(25)]
        with self.assertRaises(ValueError):parse_index(json.dumps({"data":rows}).encode())
    def test_input_source_maps_all_columns(self):
        buf=io.StringIO()
        columns=["indice_tiempo"]+[SOURCE_COLUMNS.get(f,"isac_"+f) for f in FIELDS]
        writer=csv.DictWriter(buf,fieldnames=columns)
        writer.writeheader()
        for i in range(1,25):
            row={k:"100.2" for k in columns[1:]}
            row["indice_tiempo"]=f"{2024+(i-1)//12}-{(i-1)%12+1:02d}-01"
            writer.writerow(row)
        d=parse_inputs(buf.getvalue().encode())
        self.assertEqual(len(d),24)
        self.assertEqual(set(d[date(2025,12,1)]),set(FIELDS))
    def test_missing_input_column_is_error(self):
        with self.assertRaises(ValueError):parse_inputs(b"indice_tiempo,isac_asfalto\n2026-09-01,100\n")
    def test_existing_period_mismatch_fails(self):
        with self.assertRaises(ValueError):
            compare_published({"fecha":"2026-10-01","indice":"150","variacion_mensual":"2"},
                              {"fecha":"2026-10-01","indice":"140","variacion_mensual":"2"},
                              ("fecha","indice","variacion_mensual"))
    def test_tolerance_for_precision_preserved(self):
        self.assertTrue(compare_published({"fecha":"2026-10-01","indice":Decimal("153.0001")},
                                          {"fecha":"2026-10-01","indice":"153"},
                                          ("fecha","indice")))
    def test_release_input_rejects_invalid_dates(self):
        with self.assertRaises(ValueError):source_report("2026-13")
    def test_start_cutoff(self):
        self.assertEqual(START,date(2026,10,1))
if __name__=="__main__":unittest.main()
