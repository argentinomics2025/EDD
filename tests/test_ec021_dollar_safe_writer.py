import unittest
from datetime import datetime, timezone, date
from decimal import Decimal
from scripts.ec021_dollar_safe_writer import validate, plan, TICKERS

NOW = datetime(2026, 11, 26, 16, 0, tzinfo=timezone.utc)
TODAY = date(2026, 11, 26)


def rows():
    return [
        {"casa": h, "compra": 100 + i, "venta": 105 + i,
         "fechaActualizacion": "2026-11-26T12:00:00-03:00"}
        for i, h in enumerate(TICKERS)
    ]


def board(quotes):
    return {t: (None, None, datetime(2026, 11, 25, 16, tzinfo=timezone.utc))
            for t in quotes}


class TestDollarValidation(unittest.TestCase):
    def test_canonical_seven(self):
        self.assertEqual(len(validate(rows(), NOW)), 7)

    def test_missing(self):
        with self.assertRaises(ValueError):
            validate(rows()[:-1], NOW)

    def test_duplicate(self):
        with self.assertRaises(ValueError):
            validate(rows() + rows()[:1], NOW)

    def test_nan(self):
        data = rows()
        data[0]["venta"] = "NaN"
        with self.assertRaises(ValueError):
            validate(data, NOW)

    def test_buy_exceeds_sell(self):
        data = rows()
        data[0]["compra"] = 1000
        with self.assertRaises(ValueError):
            validate(data, NOW)

    def test_bool_price(self):
        data = rows()
        data[0]["compra"] = True
        with self.assertRaises(ValueError):
            validate(data, NOW)

    def test_no_timezone(self):
        data = rows()
        data[0]["fechaActualizacion"] = "2026-11-26T12:00:00"
        with self.assertRaises(ValueError):
            validate(data, NOW)

    def test_future_timestamp(self):
        data = rows()
        data[0]["fechaActualizacion"] = "2026-11-27T12:00:00-03:00"
        with self.assertRaises(ValueError):
            validate(data, NOW)

    def test_stale_timestamp(self):
        data = rows()
        data[0]["fechaActualizacion"] = "2026-11-15T12:00:00-03:00"
        with self.assertRaises(ValueError):
            validate(data, NOW)

    def test_different_source_days_are_allowed(self):
        data = rows()
        data[0]["fechaActualizacion"] = "2026-11-25T12:00:00-03:00"
        parsed = validate(data, NOW)
        self.assertEqual(len({x["day"] for x in parsed.values()}), 2)

    def test_partial_source_is_not_permitted(self):
        with self.assertRaises(ValueError):
            validate([], NOW)


class TestImmutablePlan(unittest.TestCase):
    def setUp(self):
        self.quotes = validate(rows(), NOW)
        self.db = board(self.quotes)

    def test_new_daily_snapshots(self):
        updates, new, differences = plan(self.quotes, self.db, {}, TODAY)
        self.assertEqual(len(updates), 7)
        self.assertEqual(len(new), 7)
        self.assertEqual(differences, [])

    def test_rerun_does_not_insert(self):
        history = {(t, TODAY): (q["buy"], q["sell"])
                   for t, q in self.quotes.items()}
        updates, new, differences = plan(self.quotes, self.db, history, TODAY)
        self.assertEqual(len(new), 0)
        self.assertEqual(differences, [])
        self.assertEqual(len(updates), 7)

    def test_intraday_difference_not_overwritten(self):
        history = {("dolar-blue", TODAY): (Decimal("1"), Decimal("2"))}
        updates, new, differences = plan(self.quotes, self.db, history, TODAY)
        self.assertEqual(differences, ["dolar-blue"])
        self.assertNotIn("dolar-blue", new)
        self.assertIn("dolar-blue", updates)

    def test_old_source_day_never_added_to_history(self):
        self.quotes["dolar-blue"]["day"] = date(2026, 11, 25)
        _, new, _ = plan(self.quotes, self.db, {}, TODAY)
        self.assertNotIn("dolar-blue", new)

    def test_stale_board_update_disallowed(self):
        self.db["dolar-blue"] = (
            None, None, datetime(2026, 11, 26, 20, tzinfo=timezone.utc))
        updates, _, _ = plan(self.quotes, self.db, {}, TODAY)
        self.assertNotIn("dolar-blue", updates)

    def test_missing_db_ticker_fails(self):
        self.db.pop("dolar-blue")
        with self.assertRaises(ValueError):
            plan(self.quotes, self.db, {}, TODAY)


if __name__ == "__main__":
    unittest.main()
