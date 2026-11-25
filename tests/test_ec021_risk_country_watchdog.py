"""EC-021: synthetic regression tests for the long-running risk-country watcher."""
import unittest
from datetime import date
from scripts.ec021_risk_country_watchdog import watch
from scripts.ec021_risk_country_readonly import RiskSourceError
from tests.test_ec021_risk_country_readonly import HTTP, rows

class WatchdogTests(unittest.TestCase):
    def test_long_backlog_stays_read_only(self):
        data=rows(30)
        result=watch(http=HTTP(data, data[:15]), today=date(2026, 11, 25))
        self.assertEqual(result["new_observations_count"], 15)
        self.assertEqual(result["status"], "source_ahead_publication_blocked")
        self.assertFalse(result["writes_to_supabase"])
        self.assertFalse(result["publishes_to_website"])

    def test_identical_series_does_not_alert(self):
        data=rows()
        result=watch(http=HTTP(data, data[-20:]), today=date(2026, 11, 25))
        self.assertEqual(result["status"], "no_change")
        self.assertEqual(result["new_observations_count"], 0)

    def test_historical_mismatch_blocks(self):
        data=rows()
        stored=[dict(row) for row in data[-20:]]
        stored[-1]["valor"]=2000
        with self.assertRaisesRegex(RiskSourceError, "Historical mismatch"):
            watch(http=HTTP(data, stored), today=date(2026, 11, 25))
if __name__ == "__main__":
    unittest.main()
