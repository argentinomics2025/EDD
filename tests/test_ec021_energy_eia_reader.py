import datetime as dt
import unittest

from scripts.ec021_energy_eia_reader import (
    EnergyValidationError, ROUTES, make_url, parse_eia_response, read_eia,
)

TODAY = dt.date(2026, 11, 27)
PET = {"response": {"data": [
    {"series": "RWTC", "period": "2026-11-25", "value": "84.50"},
    {"series": "RBRTE", "period": "2026-11-25", "value": "90.20"},
    {"series": "RWTC", "period": "2026-11-24", "value": "83.00"},
]}}
GAS = {"response": {"data": [
    {"series": "RNGWHHD", "period": "2026-11-24", "value": "3.4"},
]}}
def fake_fetch(url):
    if "petroleum/pri/spt" in url:
        return PET
    if "natural-gas/pri/fut" in url:
        return GAS
    raise AssertionError("unexpected endpoint")


class EIAReaderTests(unittest.TestCase):
    def test_mock_source_read_only(self):
        result = read_eia(api_key="fixture-only", today=TODAY, fetch=fake_fetch)
        self.assertEqual(result["status"], "validated_read_only")
        self.assertEqual(len(result["records"]), 3)
        self.assertFalse(result["applied"])

    def test_read_is_repeatable(self):
        first = read_eia(api_key="fixture-only", today=TODAY, fetch=fake_fetch)
        second = read_eia(api_key="fixture-only", today=TODAY, fetch=fake_fetch)
        self.assertEqual(first["sha256"], second["sha256"])

    def test_later_observation_selected(self):
        rows = parse_eia_response(PET, ROUTES[0][1])
        self.assertEqual(next(row for row in rows if row["asset"] == "wti_spot_eia")["price"], 84.5)

    def test_correct_eia_hosts_and_series(self):
        for route, series in ROUTES:
            url = make_url(route, series, "not-a-real-secret")
            self.assertTrue(url.startswith("https://api.eia.gov/v2/"))
            for code in series:
                self.assertIn(code, url)
            self.assertIn("frequency=daily", url)

    def test_reject_missing_key(self):
        with self.assertRaises(EnergyValidationError):
            read_eia(api_key="", today=TODAY, fetch=fake_fetch)

    def test_reject_partial_response(self):
        def partial(url):
            if "petroleum/" in url:
                return {"response": {"data": PET["response"]["data"][:1]}}
            return GAS
        with self.assertRaises(EnergyValidationError):
            read_eia(api_key="fixture-only", today=TODAY, fetch=partial)

    def test_reject_non_numeric(self):
        bad = {"response": {"data": [{"series": "RWTC", "period": "2026-11-25", "value": "NA"}]}}
        with self.assertRaises(EnergyValidationError):
            parse_eia_response(bad, ROUTES[0][1])

    def test_reject_unexpected_series(self):
        bad = {"response": {"data": [{"series": "CL=F", "period": "2026-11-25", "value": "90"}]}}
        with self.assertRaises(EnergyValidationError):
            parse_eia_response(bad, ROUTES[0][1])

    def test_reject_future_observation(self):
        def future(url):
            body = fake_fetch(url)
            return {"response": {"data": [{**r, "period": "2026-11-28"} for r in body["response"]["data"]]}}
        with self.assertRaises(EnergyValidationError):
            read_eia(api_key="fixture-only", today=TODAY, fetch=future)


if __name__ == "__main__":
    unittest.main()
