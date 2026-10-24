"""EC-015 runner checks on synthetic local files, not official INDEC validation."""
import contextlib
import hashlib
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import pandas as pd
from scripts import bot_comex, validate_ica_fixture as runner


class FixtureRunnerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        data = {col: [1] for col in bot_comex.MAPPING}
        data['indice_tiempo'] = ['2026-01-01']
        data['ica_importaciones_totales'] = [3]
        data['ica_saldo_comercial'] = [1]
        self.file = self.root / 'synthetic.csv'
        pd.DataFrame(data).to_csv(self.file, index=False)
        self.sha = hashlib.sha256(self.file.read_bytes()).hexdigest()
        for target in ['socket.socket.connect', 'scripts.ica_common.download',
                       'scripts.ica_common.publish', 'scripts.ica_common.persist']:
            guard = patch(target, side_effect=AssertionError('No network or persistence allowed'))
            guard.start(); self.addCleanup(guard.stop)

    def reference(self, records=None, **changes):
        reference = {'kind': 'csv', 'period': None, 'source_sha256': self.sha,
                     'records': records if records is not None else bot_comex.parse_csv(self.file.read_bytes())}
        reference.update(changes)
        path = self.root / 'reviewed.json'
        path.write_text(json.dumps(reference), encoding='utf-8')
        return path

    def test_without_reference_is_pending(self):
        report = runner.validate_local(self.file, 'csv', self.sha)
        self.assertTrue(report['parser_pass'])
        self.assertIsNone(report['reference_match'])
        self.assertEqual(report['source_authenticity'], 'not_verified')
        self.assertFalse(report['writes_enabled'])

    def test_matching_reference_does_not_certify_production(self):
        report = runner.validate_local(self.file, 'csv', self.sha, reference_path=self.reference())
        self.assertTrue(report['reference_match'])
        self.assertFalse(report['schema_verified'])
        self.assertIn('pending', report['compatibility'])

    def test_bad_sha_rejected_before_parser(self):
        with patch.object(bot_comex, 'parse_csv') as parser, self.assertRaises(ValueError):
            runner.validate_local(self.file, 'csv', '0' * 64)
        parser.assert_not_called()

    def test_wrong_reference_metadata_rejected(self):
        for changes in [{'kind': 'rubros'}, {'period': '2026-02'}, {'source_sha256': '0' * 64}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                runner.validate_local(self.file, 'csv', self.sha, reference_path=self.reference(**changes))

    def test_mismatch_is_not_accepted_with_rounding(self):
        rows = bot_comex.parse_csv(self.file.read_bytes()); rows[0]['expo_primarios'] += 0.1
        with self.assertRaises(ValueError):
            runner.validate_local(self.file, 'csv', self.sha, reference_path=self.reference(rows))

    def test_csv_period_filter_not_silently_applied(self):
        with self.assertRaises(ValueError): runner.validate_local(self.file, 'csv', self.sha, '2026-01')

    def test_html_named_xls_rejected(self):
        path = self.root / 'fake.xls'; path.write_bytes(b'<html>error</html>')
        with self.assertRaises(ValueError):
            runner.validate_local(path, 'countries', hashlib.sha256(path.read_bytes()).hexdigest(), '2026-01')

    def test_missing_local_fixture_fails(self):
        with self.assertRaises(ValueError): runner.validate_local(self.root / 'absent.xls', 'countries', self.sha)

    def test_cli_pending_success_and_failure_codes(self):
        args = ['--file', str(self.file), '--kind', 'csv', '--sha256', self.sha]
        with contextlib.redirect_stdout(StringIO()):
            self.assertEqual(runner.main(args), 2)
            self.assertEqual(runner.main(args + ['--reference', str(self.reference())]), 0)
            self.assertEqual(runner.main(args[:-1] + ['0' * 64]), 1)

    def test_synthetic_workbook_reports_partial_countries(self):
        # Exercise runner plumbing only, not xlrd or official layout compatibility.
        frame = pd.DataFrame([
            ['Enero 2026 millones de dólares', 'Enero 2026', None, None, None, 'Enero 2026'],
            [None]*6, [None]*6, [None]*6, [None]*6,
            ['Brasil', 10, None, None, 'India', 7],
        ])
        workbook = Mock(); workbook.sheet_names = ['synthetic']
        with patch.object(runner.ica_xls_layout, 'workbook_provenance', return_value={}), patch.object(runner.common, 'read_workbook', return_value=workbook), \
             patch.object(runner.pd, 'read_excel', return_value=frame), \
             patch.object(runner.bot_ica, 'detectar_pestana_totales', return_value='synthetic'):
            report = runner.validate_local(self.file, 'countries', self.sha, '2026-01')
        self.assertEqual(report['partial_countries'], ['Brasil', 'India'])
        self.assertEqual(report['sheets'][0]['shape'], [6, 6])
        self.assertIsNone(report['reference_match'])
        workbook.close.assert_called_once()

    def test_workbook_closed_on_parser_failure(self):
        workbook = Mock(); workbook.sheet_names = []
        with patch.object(runner.ica_xls_layout, 'workbook_provenance', return_value={}), patch.object(runner.common, 'read_workbook', return_value=workbook), self.assertRaises(ValueError):
            runner.validate_local(self.file, 'rubros', self.sha, '2026-01')
        workbook.close.assert_called_once()
