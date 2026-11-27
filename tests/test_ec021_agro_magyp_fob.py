"""EC-021: deterministic offline regression tests for official daily FOB parser."""
import copy
import datetime as dt
import unittest
from scripts.ec021_agro_magyp_fob_reader import parse_official, AgroFOBError, CODES

DAY = dt.date(2026,11,27)
def rec(code,price,start=(2026,11),end=(2026,12),circular="2109"):
    return {"fecha":"2026-11-27 00:00:00.000","circular":circular,"posicion":code,
            "precio":price,"añoDesde":start[0],"mesDesde":start[1],
            "añoHasta":end[0],"mesHasta":end[1]}
GOOD={"posts":[
    rec("12019000190C",493,start=(2026,11),end=(2027,4)),
    rec("10059010120A",211),
    rec("10019900110W",220,end=(2026,11)),
    rec("12060090910Y",587,end=(2026,11)),
    rec("10059010120A",217,start=(2027,1),end=(2027,1)),
]}


class TestMAGYP(unittest.TestCase):
    def assert_bad(self, x):
        with self.assertRaises(AgroFOBError):
            parse_official(x, expected_date=DAY)

    def test_real_shape_and_classification(self):
        result=parse_official(copy.deepcopy(GOOD),expected_date=DAY)
        self.assertEqual(result["status"],"validated_read_only")
        self.assertFalse(result["applied"])
        self.assertEqual({x["serie"] for x in result["series"]},set(CODES))
        self.assertEqual(next(x for x in result["series"] if x["serie"]=="maiz_fob_granel")["precio_usd_tn"],211.0)
        self.assertEqual(result["circular"],"2109")
    def test_deterministic_hash(self):
        a=parse_official(copy.deepcopy(GOOD),expected_date=DAY)["sha256"]
        b=copy.deepcopy(GOOD); b["posts"].reverse()
        self.assertEqual(a,parse_official(b,expected_date=DAY)["sha256"])
    def test_wrong_date(self):
        x=copy.deepcopy(GOOD);x["posts"][0]["fecha"]="2026-11-26"
        self.assert_bad(x)
    def test_missing_price(self):
        x=copy.deepcopy(GOOD);x["posts"][0]["precio"]="--"
        self.assert_bad(x)
    def test_zero_price(self):
        x=copy.deepcopy(GOOD);x["posts"][0]["precio"]=0
        self.assert_bad(x)
    def test_partial_series(self):
        x=copy.deepcopy(GOOD);x["posts"].pop(2)
        self.assert_bad(x)
    def test_overlapping_windows(self):
        x=copy.deepcopy(GOOD);x["posts"].append(rec("12019000190C",494))
        self.assert_bad(x)
    def test_conflicting_circular(self):
        x=copy.deepcopy(GOOD);x["posts"][0]["circular"]="2108"
        self.assert_bad(x)
    def test_wrong_period(self):
        x=copy.deepcopy(GOOD);x["posts"][0]["mesHasta"]=10; x["posts"][0]["añoHasta"]=2026
        self.assert_bad(x)
    def test_reject_short_not_real_json(self):
        self.assert_bad({"posts":[]})
    def test_reject_invalid_date_of_window(self):
        x=copy.deepcopy(GOOD);x["posts"][0]["mesDesde"]=13
        self.assert_bad(x)
    def test_ignore_other_futures_and_seed_products(self):
        x=copy.deepcopy(GOOD);x["posts"].append(rec("ZS=F",490))
        r=parse_official(x,expected_date=DAY)
        self.assertEqual(len(r["series"]),4)


if __name__=="__main__":
    unittest.main()
