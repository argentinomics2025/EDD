import unittest
from scripts.ec022_bcra_hipotecarios import parse

class BcraMortgageTests(unittest.TestCase):
    def test_flow_and_rate_are_distinct(self):
        out = parse(b"3772;31/01/2020;12.5\n4291;31/01/2020;100\n", "tas2_ser.txt")
        self.assertEqual(out["series"]["tasa_hipotecaria"]["kind"], "weighted_rate")
        self.assertEqual(out["series"]["monto_otorgado_hipotecario"]["kind"], "monthly_flow")
        self.assertFalse(out["series"]["tasa_hipotecaria"]["uva_specific"])
        self.assertEqual(out["series"]["tasa_hipotecaria"]["uva_component"], "not_separately_identified")
    def test_duplicate_fails(self):
        with self.assertRaises(ValueError):
            parse(b"3772;31/01/2020;1\n3772;31/01/2020;2\n4291;31/01/2020;3\n", "tas2_ser.txt")
    def test_missing_month_is_reported_not_filled(self):
        out = parse(b"154;31/01/2020;1\n154;31/03/2020;2\n155;31/01/2020;3\n", "din1_ser.txt")
        self.assertEqual(out["series"]["saldo_hipotecario_total"]["missing_months"], 1)
