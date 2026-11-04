"""No network, database or market publication: synthetic fixture archive tests only."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.registro_capturas_bonos_ec0073 import archive_fixture, ArchiveError

T = datetime(2026, 11, 4, 14, 0, tzinfo=timezone.utc)
HTML = ('<table><tr><th>Especie</th><th>Último</th><th>Var Día</th>'
        '<th>Var Mes</th><th>Var Año</th></tr><tr><td>AL30D</td><td>53,37</td>'
        '<td>-0,07%</td><td>1,25%</td><td>12,35%</td></tr></table>')


class ArchiveTests(unittest.TestCase):
    def test_persist_fixture_in_quarantine(self):
        with tempfile.TemporaryDirectory() as d:
            path, created = archive_fixture(HTML, source_asof=T, captured_at=T,
                                             archive_dir=d, fixture_label='synthetic_al30d')
            x = json.loads(path.read_text())
            self.assertTrue(created)
            self.assertEqual(x['quality_status'], 'QUARANTINE')
            self.assertFalse(x['publication_authorized'])
            self.assertFalse(x['eligible_for_write'])
            self.assertFalse(x['license_verified'])
            self.assertFalse(x['source_timestamp_provider_verified'])
            self.assertFalse(x['source_html_stored'])
            self.assertEqual(x['observations'][0]['precio'], '53.37')

    def test_duplicate_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            a, x = archive_fixture(HTML, source_asof=T, captured_at=T, archive_dir=d, fixture_label='test')
            b, y = archive_fixture(HTML, source_asof=T, captured_at=T, archive_dir=d, fixture_label='test')
            self.assertEqual(a, b)
            self.assertTrue(x)
            self.assertFalse(y)
            self.assertEqual(len(list(Path(d).glob('*.json'))), 1)

    def test_changed_time_creates_new_version(self):
        with tempfile.TemporaryDirectory() as d:
            a, _ = archive_fixture(HTML, source_asof=T, captured_at=T, archive_dir=d, fixture_label='test')
            b, _ = archive_fixture(HTML, source_asof=T, captured_at=T + timedelta(minutes=1), archive_dir=d, fixture_label='test')
            self.assertNotEqual(a, b)
            self.assertEqual(len(list(Path(d).glob('*.json'))), 2)

    def test_original_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            a, _ = archive_fixture(HTML, source_asof=T, captured_at=T, archive_dir=d, fixture_label='test')
            a.write_text('tampered')
            with self.assertRaisesRegex(ArchiveError, 'immutable_snapshot_conflict'):
                archive_fixture(HTML, source_asof=T, captured_at=T, archive_dir=d, fixture_label='test')
            self.assertEqual(a.read_text(), 'tampered')

    def test_bad_html_never_creates_file(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                archive_fixture('<bad>', source_asof=T, captured_at=T, archive_dir=d, fixture_label='test')
            self.assertFalse(list(Path(d).iterdir()))

    def test_no_implicit_directory_creation(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ArchiveError, 'existing_nonsymlink'):
                archive_fixture(HTML, source_asof=T, captured_at=T, archive_dir=Path(d) / 'absent', fixture_label='test')

    def test_label_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ('../../x', '', 'a/b', '../', 'a b'):
                with self.subTest(name=name), self.assertRaisesRegex(ArchiveError, 'invalid_fixture_label'):
                    archive_fixture(HTML, source_asof=T, captured_at=T, archive_dir=d, fixture_label=name)

    def test_naive_and_inverted_timestamps(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ArchiveError):
                archive_fixture(HTML, source_asof=T.replace(tzinfo=None), captured_at=T, archive_dir=d, fixture_label='test')
            with self.assertRaises(ArchiveError):
                archive_fixture(HTML, source_asof=T, captured_at=T - timedelta(seconds=1), archive_dir=d, fixture_label='test')

    def test_duplicate_tickers_remain_quarantined(self):
        with tempfile.TemporaryDirectory() as d:
            html = HTML.replace('</table>', '<tr><td>AL30D</td><td>53,37</td><td>0</td><td>0</td><td>0</td></tr></table>')
            p, _ = archive_fixture(html, source_asof=T, captured_at=T, archive_dir=d, fixture_label='test')
            result = json.loads(p.read_text())
            self.assertIn('duplicate_ticker', result['quality_reasons'])
            self.assertFalse(result['eligible_for_write'])

    def test_content_addressed_name(self):
        with tempfile.TemporaryDirectory() as d:
            p, _ = archive_fixture(HTML, source_asof=T, captured_at=T, archive_dir=d, fixture_label='test')
            self.assertRegex(p.name, r'^ec0073-[0-9a-f]{64}\.json$')


if __name__ == '__main__':
    unittest.main()
