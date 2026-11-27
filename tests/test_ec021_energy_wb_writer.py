import unittest
from scripts.ec021_energy_wb_writer import decide, SourceError

PRICE = [
    {"asset":"brent_monthly_wb","period":"2026-11","unit":"USD/barrel","value":125.0},
    {"asset":"wti_monthly_wb","period":"2026-11","unit":"USD/barrel","value":97.7},
    {"asset":"gas_us_monthly_wb","period":"2026-11","unit":"USD/MMBtu","value":2.96},
]
STORED = [{"serie":r["asset"],"precio":str(r["value"]),"unidad":r["unit"]} for r in PRICE]


class DecisionTests(unittest.TestCase):
    def test_new_next_month(self):
        self.assertEqual(decide(PRICE, [], "2026-10-01", "2026-11"), "insert")
    def test_replay_no_change(self):
        self.assertEqual(decide(PRICE, STORED, "2026-11-01", "2026-11"), "no_change")
    def test_revision_fails_closed(self):
        rows=[dict(r) for r in STORED]; rows[0]["precio"]="130.0"
        with self.assertRaises(SourceError):
            decide(PRICE,rows,"2026-11-01","2026-11")
    def test_partial_stored_month_fails_closed(self):
        with self.assertRaises(SourceError):
            decide(PRICE,STORED[:2],"2026-11-01","2026-11")
    def test_reject_stale_source_after_new_database_month(self):
        with self.assertRaises(SourceError):
            decide(PRICE, STORED, "2026-12-01", "2026-11")

    def test_no_bootstrap_unapproved(self):
        with self.assertRaises(SourceError):
            decide(PRICE,[],None,"2026-11")
    def test_gap_fails_closed(self):
        with self.assertRaises(SourceError):
            decide(PRICE,[],"2026-09-01","2026-11")
    def test_duplicate_official_series_fails(self):
        bad=[dict(x) for x in PRICE];bad[1]["asset"]="brent_monthly_wb"
        with self.assertRaises(SourceError):
            decide(bad,[],"2026-10-01","2026-11")
    def test_bad_units_fails(self):
        bad=[dict(x) for x in PRICE];bad[2]["unit"]="USD/barrel"
        with self.assertRaises(SourceError):
            decide(bad,[],"2026-10-01","2026-11")
    def test_disallow_partial_source(self):
        with self.assertRaises(SourceError):
            decide(PRICE[:2],[],"2026-10-01","2026-11")
    def test_transition_december_january(self):
        jan=[{**x,"period":"2027-01"} for x in PRICE]
        self.assertEqual(decide(jan,[],"2026-12-01","2027-01"),"insert")
    def test_preserve_decimal_comparison(self):
        self.assertEqual(decide(PRICE,STORED,"2026-11-01","2026-11"),"no_change")


if __name__ == "__main__":
    unittest.main()
