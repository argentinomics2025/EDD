"""EC-021.5: fail-closed IPC monthly planner tests (synthetic data)."""
import copy
import unittest

from scripts.ec0215_ipc_insert_plan import plan_increment

BASE = {
    "source": "INDEC", "status": "read_only_no_publication",
    "writes_to_supabase": False, "sha256": "a" * 64,
    "latest": [
        {"date": "2026-07-01", "monthly_pct": "2.1"},
        {"date": "2026-08-01", "monthly_pct": "1.7"},
        {"date": "2026-09-01", "monthly_pct": "1.9"},
        {"date": "2026-10-01", "monthly_pct": "2.2"},
    ],
}
STORED = [{"date": item["date"], "value": item["monthly_pct"]} for item in BASE["latest"]]


class IpcPlanTests(unittest.TestCase):
    def test_existing_latest_is_idempotent(self):
        self.assertEqual(plan_increment(BASE, STORED)["insert_only"], [])

    def test_one_month_approved_for_planning_only(self):
        source = copy.deepcopy(BASE)
        source["latest"] = source["latest"][1:] + [{"date": "2026-11-01", "monthly_pct": "2.5"}]
        self.assertEqual(plan_increment(source, STORED)["insert_only"],
                         [{"date": "2026-11-01", "value": "2.5"}])
        self.assertEqual(plan_increment(source, STORED + [{"date": "2026-11-01", "value": "2.5"}])["insert_only"], [])

    def test_revision_rejected(self):
        source = copy.deepcopy(BASE)
        source["latest"][-2]["monthly_pct"] = "2.1"
        with self.assertRaisesRegex(ValueError, "Historical revision"):
            plan_increment(source, STORED)

    def test_gap_rejected(self):
        source = copy.deepcopy(BASE)
        source["latest"][-1] = {"date": "2026-12-01", "monthly_pct": "2.5"}
        with self.assertRaises(ValueError):
            plan_increment(source, STORED)

    def test_duplicate_rejected(self):
        source = copy.deepcopy(BASE)
        source["latest"].append(source["latest"][-1])
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            plan_increment(source, STORED)

    def test_untrusted_source_rejected(self):
        source = copy.deepcopy(BASE)
        source["writes_to_supabase"] = True
        with self.assertRaisesRegex(ValueError, "read-only"):
            plan_increment(source, STORED)

    def test_noncanonical_date_rejected(self):
        source = copy.deepcopy(BASE)
        source["latest"][-1]["date"] = "2026-10-15"
        with self.assertRaises(ValueError):
            plan_increment(source, STORED)

    def test_extreme_and_nonfinite_rejected(self):
        for value in ("NaN", "Infinity", "999", None, True):
            source = copy.deepcopy(BASE)
            source["latest"][-1]["monthly_pct"] = value
            with self.assertRaises(ValueError):
                plan_increment(source, STORED)

    def test_stale_source_rejected(self):
        with self.assertRaises(ValueError):
            plan_increment(BASE, STORED + [{"date": "2026-11-01", "value": "2.5"}])


if __name__ == "__main__":
    unittest.main()
