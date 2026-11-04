"""Synthetic offline snapshot tests; never access Rava, GitHub Actions, or Supabase."""
import unittest
from datetime import datetime, timedelta, timezone
from scripts.captura_rava_aislada import SnapshotError, diagnose, normalize_number, read_snapshot

AT = datetime(2026, 11, 4, 14, 0, tzinfo=timezone.utc)


def fixture(rows):
    return '<table><tr><th>Especie</th><th>Último</th><th>Var Día</th><th>Var Mes</th><th>Var Año</th></tr>' + ''.join(
        '<tr>' + ''.join(f'<td>{v}</td>' for v in r) + '</tr>' for r in rows) + '</table>'


class OfflineSnapshotTests(unittest.TestCase):
    def test_one_quote_is_quarantined(self):
        d = diagnose(fixture([('AL30D', '53,37', '-0,07%', '-0,41%', '18,37%')]),
                     source_asof=AT, captured_at=AT + timedelta(minutes=2))
        self.assertEqual(d['record_count'], 1)
        self.assertEqual(d['quality_status'], 'QUARANTINE')
        self.assertFalse(d['eligible_for_write'])
        self.assertIn('full_coverage_not_demonstrated', d['quality_reasons'])
        self.assertIn('permission_not_verified', d['quality_reasons'])
        self.assertIn('market_status_unverified', d['quality_reasons'])

    def test_price_normalization(self):
        self.assertEqual(normalize_number('1.234,50'), '1234.50')
        self.assertEqual(normalize_number('53,37'), '53.37')
        self.assertEqual(normalize_number('-0,07%'), '-0.07')

    def test_reject_ambiguous_numbers(self):
        for n in ('1.234', '1,234,56', '53,', 'N/A', '', '1e3', 'NaN'):
            with self.subTest(raw=n), self.assertRaises(SnapshotError):
                normalize_number(n)

    def test_reject_nonpositive_price(self):
        for n in ('0', '-1'):
            with self.subTest(n=n), self.assertRaises(SnapshotError):
                normalize_number(n, positive=True)

    def test_reject_unrecognized_table(self):
        with self.assertRaisesRegex(SnapshotError, 'fixture_table_header_not_verified'):
            read_snapshot('<table><tr><th>Precio</th></tr></table>', source_asof=AT)

    def test_reject_ambiguous_multiple_tables(self):
        with self.assertRaisesRegex(SnapshotError, 'fixture_table_header_not_verified'):
            read_snapshot(fixture([]) + fixture([]), source_asof=AT)

    def test_reject_short_row(self):
        with self.assertRaisesRegex(SnapshotError, 'incomplete_table_row'):
            read_snapshot(fixture([('AL30D', '53,37')]), source_asof=AT)

    def test_missing_source_timestamp(self):
        with self.assertRaisesRegex(SnapshotError, 'source_timestamp_required'):
            read_snapshot(fixture([]), source_asof=None)

    def test_ignore_other_symbols_not_in_inventory(self):
        rows = read_snapshot(fixture([('XYZ', '1', '1', '1', '1')]), source_asof=AT)
        self.assertEqual(rows, [])

    def test_duplicate_symbols_detected_by_gate(self):
        d = diagnose(fixture([('AL30D', '53,37', '1', '1', '1'),('AL30D', '53,38', '1', '1', '1')]),
                     source_asof=AT, captured_at=AT)
        self.assertIn('duplicate_ticker', d['quality_reasons'])

    def test_timestamp_must_be_timezone_aware(self):
        with self.assertRaises(SnapshotError):
            diagnose(fixture([]), source_asof=AT, captured_at=AT.replace(tzinfo=None))

    def test_record_identity_stable(self):
        html = fixture([('AL30D', '53,37', '1', '2', '3')])
        rows = read_snapshot(html, source_asof=AT)
        self.assertEqual(rows[0]['source_record_id'], read_snapshot(html, source_asof=AT)[0]['source_record_id'])

    def test_no_market_timestamp_inferred(self):
        with self.assertRaises(SnapshotError):
            read_snapshot(fixture([]), source_asof=AT.replace(tzinfo=None))

    def test_nontrading_cannot_be_guessed_from_empty_page(self):
        d = diagnose(fixture([]), source_asof=AT, captured_at=AT)
        self.assertEqual(d['quality_status'], 'QUARANTINE')
        self.assertIn('empty_not_evidence_of_holiday', d['quality_reasons'])


if __name__ == '__main__':
    unittest.main()
