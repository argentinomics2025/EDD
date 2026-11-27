import unittest
from scripts.ec022_ripte_historico import parse

class RipteTests(unittest.TestCase):
    def test_valid(self):
        out = parse(b"indice_tiempo,ripte\n1994-07-01,874.87\n1994-08-01,893\n")
        self.assertEqual(out["observations"][0]["value"], "874.87")
    def test_missing_month_rejected(self):
        with self.assertRaises(ValueError):
            parse(b"indice_tiempo,ripte\n1994-07-01,874\n1994-09-01,893\n")
