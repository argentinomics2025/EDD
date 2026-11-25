"""EC-021 DollarApi read-only comparison tests."""
import unittest
from scripts.ec021_dollar_readonly_audit import assess,HOUSES

def sample():
    source=[{"casa":h,"venta":1000+i,"compra":900+i,"fechaActualizacion":"2026-11-25T14:00:00-03:00"}
            for i,h in enumerate(HOUSES)]
    db=[{"id":t,"sell_value":1000+i,"buy_value":900+i,
         "last_updated":"2026-11-25T18:00:00+00:00"} for i,t in enumerate(HOUSES.values())]
    return source,db

class Tests(unittest.TestCase):
    def test_valid_same_quotes_no_writes(self):
        s,db=sample()
        result=assess(s,db)
        self.assertFalse(result["writes_to_supabase"])
        self.assertTrue(all(r["status"]=="matched" for r in result["quotes"].values()))
    def test_changed_quote_reported_not_written(self):
        s,db=sample()
        db[0]["sell_value"]=9999
        self.assertEqual(assess(s,db)["quotes"][db[0]["id"]]["status"],"dashboard_differs_from_current_quote")
    def test_legacy_stale_ticker_reported(self):
        s,db=sample()
        db.append({"id":"dolar-bolsa","sell_value":100,"buy_value":90})
        self.assertEqual(assess(s,db)["stale_extra_tickers"],["dolar-bolsa"])
    def test_source_duplicate_fails(self):
        s,db=sample()
        s.append(dict(s[0]))
        with self.assertRaises(ValueError):assess(s,db)
    def test_missing_dashboard_fails(self):
        s,db=sample()
        db.pop()
        with self.assertRaises(ValueError):assess(s,db)
    def test_absurd_quote_fails(self):
        s,db=sample()
        s[0]["venta"]=-2
        with self.assertRaises(ValueError):assess(s,db)
    def test_timezone_required(self):
        s,db=sample()
        s[0]["fechaActualizacion"]="2026-11-25T14:00:00"
        with self.assertRaises(ValueError):assess(s,db)

if __name__=="__main__":unittest.main()
