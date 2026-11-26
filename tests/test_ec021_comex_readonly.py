import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from ec021_comex_readonly import allowed, parse

HTML = """<html><body>Fecha de publicación: 19 de noviembre de 2026
En octubre de 2026, las exportaciones alcanzaron 10.061 millones de dólares (26,4% v.ia.) y las importaciones, 6.668 millones de dólares (-6,7% v.ia.). El intercambio comercial aumentó. La balanza comercial registró un superávit de 3.394 millones de dólares.</body></html>"""

class Tests(unittest.TestCase):
    def test_official_headline(self):
        a = parse(HTML.encode())
        self.assertEqual((a["period"], a["balance_musd_rounded"], a["rounding_residual_musd"]), ("2026-10-01", "3394", "1"))
        self.assertFalse(a["writes_to_supabase"])
    def test_disagreement(self):
        with self.assertRaises(ValueError):
            parse(HTML.replace("3.394", "3.398").encode())
    def test_schema_change(self):
        with self.assertRaises(ValueError):
            parse(b"<html>status ok</html>")
    def test_hosts(self):
        self.assertTrue(allowed("https://www.indec.gob.ar/ftp/ica_digital/ica_d_11_262BEEC7410A/"))
        self.assertFalse(allowed("http://www.indec.gob.ar/ftp/ica_digital/ica_d_11_262BEEC7410A/"))
        self.assertFalse(allowed("https://evil.test/ftp/ica_digital/ica_d_11_262BEEC7410A/"))

if __name__ == "__main__":
    unittest.main()
