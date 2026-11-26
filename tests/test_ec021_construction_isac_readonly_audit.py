"""Synthetic ISAC read-only audit tests."""
import unittest
from scripts.ec021_construction_isac_readonly_audit import assess,SERIES

def fixtures():
    source={"data":[[f"2025-{i:02d}-01",100+i] for i in range(1,13)]}
    stored=[{"fecha":f"2025-{i:02d}-01","indice":100+i} for i in range(10,13)]
    return source,stored

class TestConstruction(unittest.TestCase):
    def test_intended_desestacionalizada_series(self):
        self.assertEqual(SERIES,"33.2_ISAC_SIN_EDAD_0_M_23_56")
    def test_exact_match(self):
        a,b=fixtures()
        result=assess(a,b)
        self.assertTrue(all(x["status"]=="matched" for x in result["overlap"]))
        self.assertFalse(result["writes_to_supabase"])
    def test_source_mismatch_reported(self):
        a,b=fixtures();b[-1]["indice"]=10
        self.assertIn("differs",assess(a,b)["overlap"][0]["status"]+assess(a,b)["overlap"][-1]["status"])
    def test_duplicate_fails(self):
        a,b=fixtures();a["data"].append(list(a["data"][0]))
        with self.assertRaises(ValueError):assess(a,b)
    def test_invalid_source_fails(self):
        a,b=fixtures();a["data"]=[["2026-01-01",1]]
        with self.assertRaises(ValueError):assess(a,b)
    def test_empty_db_fails(self):
        a,b=fixtures()
        with self.assertRaises(ValueError):assess(a,[])

if __name__=="__main__":unittest.main()
