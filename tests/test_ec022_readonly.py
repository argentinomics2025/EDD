import unittest
from datetime import date
from scripts.ec022_hipotecarios_readonly import BASE, collect
from scripts.ec022_salarios_readonly import parse_ripte, probe_indec

class BcraTests(unittest.TestCase):
    def reader(self, duplicate=False, missing=False, negative=False):
        def read(url,p):
            if url==BASE:
                return {"status":200,"results":[{"idVariable":31,"descripcion":"Unidad de valor adquisitivo"}]},"a"
            d="2026-01-01" if duplicate else "2026-01-02"
            rows=[{"fecha":"2026-01-01","valor":100},{"fecha":d,"valor":-101 if negative else 101}]
            if missing: rows=rows[:1]
            return {"status":200,"results":[{"idVariable":31,"detalle":rows}]},"b"
        return read
    def test_valid(self):
        r=collect(31,date(2026,1,1),date(2026,1,2),self.reader())
        self.assertEqual(len(r["observations"]),2)
        self.assertFalse(r["writes_to_supabase"])
    def test_duplicate(self):
        with self.assertRaises(ValueError): collect(31,date(2026,1,1),date(2026,1,2),self.reader(duplicate=True))
    def test_missing(self):
        with self.assertRaises(ValueError): collect(31,date(2026,1,1),date(2026,1,2),self.reader(missing=True))
    def test_negative(self):
        with self.assertRaises(ValueError): collect(31,date(2026,1,1),date(2026,1,2),self.reader(negative=True))

class SalaryTests(unittest.TestCase):
    def test_nominal(self):
        raw='<table><tr><th>Mes</th><th>Monto en pesos</th><th>Variación</th></tr><tr><td>Enero / 2026</td><td>1.000,00</td><td>1,0</td></tr><tr><td>Febrero / 2026</td><td>1.020,00</td><td>2,0</td></tr></table>'.encode()
        out=parse_ripte(raw,date(2026,3,1))
        self.assertEqual(out["observations"][-1]["value"],"1020.00")
        self.assertFalse(out["writes_to_supabase"])
    def test_reject_html(self):
        with self.assertRaises(ValueError): probe_indec(2025,lambda url:b"<html>error</html>")

if __name__=="__main__": unittest.main()
