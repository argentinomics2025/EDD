"""Offline risk-country safety tests; never connect to production."""
import json
import unittest
from datetime import date
from unittest.mock import patch
from scripts.ec021_risk_country_readonly import (
    RiskSourceError, monitor, parse_rows, ATTRIBUTION
)

def rows(n=30):
    from datetime import timedelta
    return [{"fecha": (date(2026,10,1)+timedelta(days=i)).isoformat(), "valor": 800+i} for i in range(n)]

class Response:
    def __init__(self, data):
        self.content=json.dumps(data).encode()
        self.data=data
    def raise_for_status(self): pass
    def json(self): return self.data

class HTTP:
    def __init__(self, src, db):
        self.datasets=[src, db]
        self.calls=[]
    def get(self,url,**kwargs):
        self.calls.append((url,kwargs))
        return Response(self.datasets[len(self.calls)-1])

class RiskCountryTests(unittest.TestCase):
    def test_consistent_snapshots_without_writes(self):
        data=rows()
        http=HTTP(data,data[-20:])
        result=monitor(http=http,today=date(2026,11,25))
        self.assertEqual(result["status"],"no_change")
        self.assertFalse(result["writes_to_supabase"])
        self.assertFalse(result["publishes_to_website"])
        self.assertIn("ArgentinaDatos",result["attribution"])
        self.assertIn("Ámbito",ATTRIBUTION)
        self.assertEqual(len(http.calls),2)
        self.assertEqual(http.calls[1][1]["params"]["limit"],"30")

    def test_source_new_day_detected_but_not_published(self):
        data=rows()
        http=HTTP(data,data[:-1])
        result=monitor(http=http,today=date(2026,11,25))
        self.assertEqual(result["status"],"source_ahead_publication_blocked")
        self.assertEqual(result["new_observations_count"],1)
        self.assertFalse(result["writes_to_supabase"])

    def test_discrepancy_fails_closed(self):
        data=rows()
        stored=[dict(x) for x in data[-20:]]
        stored[-1]["valor"]=4321
        with self.assertRaisesRegex(RiskSourceError,"Historical discrepancy"):
            monitor(http=HTTP(data,stored),today=date(2026,11,25))

    def test_duplicate_invalid_and_future(self):
        with self.assertRaisesRegex(RiskSourceError,"Duplicate"):
            parse_rows(rows()[:5]+[rows()[0]])
        with self.assertRaisesRegex(RiskSourceError,"Out-of-bounds"):
            parse_rows([{"fecha":"2026-11-01","valor":100000}])
        with self.assertRaisesRegex(RiskSourceError,"Future"):
            monitor(http=HTTP([{"fecha":"2099-01-01","valor":1200}]+rows(),rows()[-20:]),
                    today=date(2026,11,25))

    def test_source_behind_database(self):
        data=rows()
        with self.assertRaisesRegex(RiskSourceError,"behind DB"):
            monitor(http=HTTP(data[:-1],data[-20:]),today=date(2026,11,25))

if __name__=="__main__":
    unittest.main()
