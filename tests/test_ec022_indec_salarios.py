import unittest
from scripts.ec022_indec_salarios import parse

HEADER = "periodo;IS_sector_privado_registrado;IS_sector_publico;IS_total_registrado;IS_sector_no_registrado;IS_indice_total\n"

class IndecSalaryTests(unittest.TestCase):
    def test_na_and_decimal(self):
        result = parse((HEADER + "1/1/2020;1;1;1;NA;NA\n1/2/2020;1;1;1;1;102,50\n").encode())
        self.assertEqual(result["observations"], [{"date": "2020-02-01", "value": "102.50"}])

    def test_missing_month_fails_closed(self):
        with self.assertRaises(ValueError):
            parse((HEADER + "1/1/2020;1;1;1;1;100\n1/3/2020;1;1;1;1;102\n").encode())

    def test_wrong_schema_fails_closed(self):
        with self.assertRaises(ValueError):
            parse(b"periodo;valor\n1/1/2020;100\n")
