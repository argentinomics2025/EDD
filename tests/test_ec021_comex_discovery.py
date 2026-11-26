import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from ec021_comex_latest_link import candidates,download,read_values,NoRedirect

class DiscoveryTests(unittest.TestCase):
    def test_bounded_dates(self):
        a=candidates("2026-11")
        self.assertEqual(len(a),11)
        self.assertEqual(a[0],"https://www.indec.gob.ar/ftp/cuadros/economia/ica_cuadros_19_11_26.xls")
        self.assertEqual(len(set(a)),11)
    def test_invalid_release(self):
        for value in ["2026-13","2025-00","2026-11-11","foo"]:
            with self.assertRaises(ValueError):
                candidates(value)
    def test_reject_other_host(self):
        with self.assertRaises(ValueError):
            download("https://example.com/ica_cuadros_19_11_26.xls")
    def test_unexpected_workbook(self):
        with self.assertRaises(Exception):
            read_values(b"not an xls","2026-10")

if __name__=="__main__":unittest.main()
