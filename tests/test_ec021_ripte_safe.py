"""EC-021 etapa 3: isolated RIPTE fail-closed tests; zero network or database calls."""
import unittest
from scripts.bot_ripte import RipteValidationError, parse_official, validate_existing


def official_page(rows):
    body = "".join(
        f"<tr><td>{month}</td><td>$ 100</td><td>{pct}</td><td>100</td></tr>"
        for month, pct in rows
    )
    return ("<html><table><thead><tr><th>Mes</th><th>Monto</th>"
            "<th>Variación respecto mes anterior</th><th>Índice</th>"
            "</tr></thead><tbody>" + body + "</tbody></table></html>")


ROWS = [
    ("Enero/2026", "0,8%"),
    ("Febrero/2026", "5,3%"),
    ("Marzo/2026", "2,4%"),
    ("Abril/2026", "3,5%"),
    ("Mayo/2026", "0,7%"),
    ("Junio/2026", "3,6%"),
    ("Julio/2026", "1,6%"),
    ("Agosto/2026", "1,9%"),
    ("Setiembre/2026", "2,0%"),
    ("Octubre/2026", "1,1%"),
    ("Noviembre/2026", "1,2%"),
    ("Diciembre/2026", "1,3%"),
]


class SafeRipteTests(unittest.TestCase):
    def setUp(self):
        self.official = parse_official(official_page(ROWS))

    def test_month_alias_and_decimal(self):
        self.assertEqual(self.official[8], {"fecha": "2026-09-01", "var_ripte_mensual": "2.0"})
        self.assertEqual(self.official[0], {"fecha": "2026-01-01", "var_ripte_mensual": "0.8"})

    def test_missing_variation_fails(self):
        rows = ROWS.copy()
        rows[8] = ("Setiembre/2026", "")
        with self.assertRaises(RipteValidationError):
            parse_official(official_page(rows))

    def test_unknown_month_fails_not_default_january(self):
        rows = ROWS.copy()
        rows[8] = ("Seteimbre/2026", "2,0%")
        with self.assertRaises(RipteValidationError):
            parse_official(official_page(rows))

    def test_duplicate_source_month_fails(self):
        with self.assertRaises(RipteValidationError):
            parse_official(official_page(ROWS + [ROWS[0]]))

    def test_missing_table_fails(self):
        with self.assertRaises(RipteValidationError):
            parse_official("<html><body>Nothing</body></html>")

    def test_too_few_rows_fails(self):
        with self.assertRaises(RipteValidationError):
            parse_official(official_page(ROWS[:2]))

    def test_duplicate_production_january_fails(self):
        stored = self.official[:8] + [{"fecha": "2026-01-01", "var_ripte_mensual": "2.0"}]
        with self.assertRaisesRegex(RipteValidationError, "Duplicate stored"):
            validate_existing(self.official, stored)

    def test_historical_revision_fails(self):
        stored = [dict(x) for x in self.official[:8]]
        stored[0]["var_ripte_mensual"] = "2.0"
        with self.assertRaisesRegex(RipteValidationError, "revision"):
            validate_existing(self.official, stored)

    def test_new_month_plan_is_pure(self):
        old = self.official[:-1]
        result = validate_existing(self.official, old)
        self.assertEqual(result, [self.official[-1]])
        self.assertEqual(len(old), 11)

    def test_no_new_month_noop(self):
        self.assertEqual(validate_existing(self.official, self.official), [])

    def test_multi_month_backfill_blocked(self):
        with self.assertRaisesRegex(RipteValidationError, "Multiple months"):
            validate_existing(self.official, self.official[:-2])

    def test_gap_fails(self):
        stored = [x for x in self.official[:-1] if x["fecha"] != "2026-11-01"]
        with self.assertRaisesRegex(RipteValidationError, "Multiple months"):
            validate_existing(self.official, stored)


if __name__ == "__main__":
    unittest.main()
