"""No-write validation, planning, and replay tests for BCRA v4.0 writer."""
import unittest
from datetime import date
from decimal import Decimal
from scripts.ec021_bcra_safe_writer import IDS, validate, plan


def data():
    official = {
        "status": 200,
        "results": [
            {"idVariable": i, "descripcion": "official_" + str(i),
             "ultFechaInformada": "2026-11-27", "ultValorInformado": str(1000 + i)}
            for i in IDS
        ] + [
            {"idVariable": i, "descripcion": "other",
             "ultFechaInformada": "2026-11-27", "ultValorInformado": 100}
            for i in range(100, 125)
        ],
    }
    return official


def stored(day=date(2026, 11, 26)):
    return {i: (day, Decimal(1000 + i)) for i in IDS}


class TestBCRASource(unittest.TestCase):
    def test_source_complete(self):
        self.assertEqual(set(validate(data(), today=date(2026, 11, 27))), set(IDS))

    def test_duplicate_rejected(self):
        p = data()
        p["results"].append(dict(p["results"][0]))
        with self.assertRaises(ValueError):
            validate(p, today=date(2026, 11, 27))

    def test_missing_series_rejected(self):
        p = data()
        p["results"] = [x for x in p["results"] if x["idVariable"] != 31]
        with self.assertRaises(ValueError):
            validate(p, today=date(2026, 11, 27))

    def test_future_date_rejected(self):
        p = data()
        p["results"][0]["ultFechaInformada"] = "2026-11-28"
        with self.assertRaises(ValueError):
            validate(p, today=date(2026, 11, 27))

    def test_nonfinite_rejected(self):
        p = data()
        p["results"][0]["ultValorInformado"] = "Infinity"
        with self.assertRaises(ValueError):
            validate(p, today=date(2026, 11, 27))

    def test_boolean_rejected(self):
        p = data()
        p["results"][0]["ultValorInformado"] = True
        with self.assertRaises(ValueError):
            validate(p, today=date(2026, 11, 27))

    def test_negative_rejected(self):
        p = data()
        p["results"][0]["ultValorInformado"] = -5
        with self.assertRaises(ValueError):
            validate(p, today=date(2026, 11, 27))

    def test_status_rejected(self):
        p = data()
        p["status"] = 500
        with self.assertRaises(ValueError):
            validate(p, today=date(2026, 11, 27))


class TestAtomicPlanner(unittest.TestCase):
    def setUp(self):
        self.official = validate(data(), today=date(2026, 11, 27))

    def test_all_five_new_dates_append(self):
        board = stored()
        updates, inserts, anomalies = plan(
            self.official, board, board, today=date(2026, 11, 27))
        self.assertEqual(len(updates), 5)
        self.assertEqual(len(inserts), 5)
        self.assertEqual(anomalies, {})

    def test_second_run_no_change(self):
        board = stored(date(2026, 11, 27))
        u, ins, issues = plan(
            self.official, board, board, today=date(2026, 11, 27))
        self.assertEqual((len(u), len(ins), len(issues)), (0, 0, 0))

    def test_same_date_revision_not_applied(self):
        board = stored(date(2026, 11, 27))
        board[1] = (board[1][0], Decimal("33333"))
        _, ins, issues = plan(
            self.official, board, board, today=date(2026, 11, 27))
        self.assertEqual(ins, {})
        self.assertEqual(issues[1], "same_date_revision_requires_review")

    def test_source_behind_not_applied(self):
        board = stored(date(2026, 11, 28))
        with self.assertRaises(ValueError):
            plan(self.official, board, board, today=date(2026, 11, 27))

    def test_source_behind_prior_day_reported(self):
        from copy import deepcopy
        other = deepcopy(self.official)
        other[1]["date"] = date(2026, 11, 25)
        board = stored()
        _, _, issues = plan(other, board, board, today=date(2026, 11, 27))
        self.assertEqual(issues[1], "official_behind_database")

    def test_board_history_mismatch_rejected(self):
        board = stored()
        hist = stored()
        hist[7] = (date(2026, 11, 25), Decimal(1007))
        with self.assertRaises(ValueError):
            plan(self.official, board, hist, today=date(2026, 11, 27))

    def test_missing_history_rejected(self):
        board = stored()
        hist = stored()
        del hist[7]
        with self.assertRaises(ValueError):
            plan(self.official, board, hist, today=date(2026, 11, 27))


if __name__ == "__main__":
    unittest.main()
