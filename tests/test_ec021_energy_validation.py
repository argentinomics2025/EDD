import copy
import datetime as dt
import unittest

from scripts.ec021_energy_validation import EnergyValidationError, validate_snapshot

TODAY = dt.date(2026, 11, 27)
GOOD = {
    "source": "EIA",
    "basis": "spot",
    "rows": [
        {"asset": "wti_spot_eia", "unit": "USD/barrel", "date": "2026-11-25", "price": 84.5},
        {"asset": "brent_spot_eia", "unit": "USD/barrel", "date": "2026-11-25", "price": 90.2},
        {"asset": "henry_hub_spot_eia", "unit": "USD/MMBtu", "date": "2026-11-24", "price": 3.4},
    ],
}


class EnergyValidationTests(unittest.TestCase):
    def assert_rejected(self, payload):
        with self.assertRaises(EnergyValidationError):
            validate_snapshot(payload, today=TODAY)

    def test_valid_snapshot_is_read_only(self):
        result = validate_snapshot(copy.deepcopy(GOOD), today=TODAY)
        self.assertEqual(result["status"], "validated_read_only")
        self.assertFalse(result["applied"])
        self.assertEqual(len(result["records"]), 3)

    def test_order_independent_determinism(self):
        a = validate_snapshot(copy.deepcopy(GOOD), today=TODAY)["sha256"]
        b = copy.deepcopy(GOOD)
        b["rows"].reverse()
        self.assertEqual(a, validate_snapshot(b, today=TODAY)["sha256"])

    def test_reject_yahoo_futures(self):
        x = copy.deepcopy(GOOD)
        x["source"], x["basis"] = "Yahoo", "futures"
        self.assert_rejected(x)

    def test_reject_partial_batch(self):
        x = copy.deepcopy(GOOD)
        x["rows"].pop()
        self.assert_rejected(x)

    def test_reject_duplicate_asset(self):
        x = copy.deepcopy(GOOD)
        x["rows"][1]["asset"] = "wti_spot_eia"
        self.assert_rejected(x)

    def test_reject_bad_unit(self):
        x = copy.deepcopy(GOOD)
        x["rows"][2]["unit"] = "USD/barrel"
        self.assert_rejected(x)

    def test_reject_invalid_price(self):
        for price in [0, -1, float("nan"), float("inf"), True, "3.4"]:
            x = copy.deepcopy(GOOD)
            x["rows"][0]["price"] = price
            self.assert_rejected(x)

    def test_reject_future_date(self):
        x = copy.deepcopy(GOOD)
        x["rows"][0]["date"] = "2026-11-28"
        self.assert_rejected(x)

    def test_reject_stale_date(self):
        x = copy.deepcopy(GOOD)
        x["rows"][0]["date"] = "2026-11-18"
        self.assert_rejected(x)

    def test_reject_impossible_date(self):
        x = copy.deepcopy(GOOD)
        x["rows"][0]["date"] = "2026-02-30"
        self.assert_rejected(x)


if __name__ == "__main__":
    unittest.main()
