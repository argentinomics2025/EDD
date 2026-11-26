import unittest
from datetime import datetime,timezone,timedelta
from scripts.ec021_dollar_health import evaluate
from scripts.ec021_dollar_safe_writer import TICKERS

BASE=datetime(2026,11,26,18,tzinfo=timezone.utc)
def mk():
    source={tick:{"updated":BASE,"buy":100,"sell":110} for tick in TICKERS.values()}
    db=[{"id":tick,"last_updated":(BASE-timedelta(hours=2)).isoformat(),"buy_value":100,"sell_value":110} for tick in TICKERS.values()]
    return source,db

class Tests(unittest.TestCase):
    def test_fresh_dashboard(self):
        s,d=mk()
        result=evaluate(s,d)
        self.assertEqual(result["status"],"healthy")
        self.assertEqual(result["checked_tickers"],7)
        self.assertFalse(result["writes_to_supabase"])
    def test_stale_dashboard(self):
        s,d=mk()
        d[0]["last_updated"]=(BASE-timedelta(hours=19)).isoformat()
        result=evaluate(s,d)
        self.assertEqual(result["status"],"stale_dashboard")
        self.assertEqual(len(result["stale_dashboard_tickers"]),1)
    def test_missing_ticker(self):
        s,d=mk()
        with self.assertRaises(ValueError):evaluate(s,d[:-1])
    def test_duplicate_ticker(self):
        s,d=mk()
        with self.assertRaises(ValueError):evaluate(s,d+d[:1])
    def test_naive_timestamp(self):
        s,d=mk()
        d[0]["last_updated"]="2026-11-26T14:00:00"
        with self.assertRaises(ValueError):evaluate(s,d)
    def test_normal_source_lag_not_stale(self):
        s,d=mk()
        d[0]["last_updated"]=(BASE+timedelta(hours=1)).isoformat()
        self.assertEqual(evaluate(s,d)["status"],"healthy")
