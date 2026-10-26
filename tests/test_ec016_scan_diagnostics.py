"""Offline regressions for failed Trivy steps; no Docker, SQL or network."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import yaml
from infra.ec016 import scan_diagnostics as scan

ROOT = Path(__file__).resolve().parents[1]


class ScanDiagnostics(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.image = 'sha256:' + 'a' * 64
        env = patch.dict(os.environ, {'EC016_SCANNED_POSTGRES_ID': self.image})
        env.start(); self.addCleanup(env.stop)

    def report(self, vulnerabilities=None):
        data = {'SchemaVersion': 2, 'Metadata': {'ImageID': self.image},
                'Results': [{'Packages': [{'Name': 'libssl3'}],
                             'Vulnerabilities': vulnerabilities or []}]}
        (self.root / 'postgresql.json').write_text(json.dumps(data))

    def finish(self, outcome):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = scan.finish(self.root, {'postgresql': outcome})
        return code, output.getvalue()

    def test_exit_one_with_json_counts_vulnerabilities_without_leaks(self):
        self.report([{'Severity': 'HIGH', 'PkgName': 'libssl3', 'Target': '/private/path'},
                     {'Severity': 'CRITICAL', 'PkgName': 'secret://password'},
                     {'Severity': 'LOW', 'PkgName': 'irrelevant'}])
        code, output = self.finish('failure')
        self.assertEqual(code, 1)
        data = json.loads(output)
        self.assertEqual(data['code'], 'SCAN_VULNERABILITIES_BLOCKED')
        self.assertEqual((data['HIGH'], data['CRITICAL']), (1, 1))
        self.assertEqual(data['packages'], ['libssl3'])
        self.assertNotIn('private', output); self.assertNotIn('password', output)

    def test_database_error_private_log_is_classified_without_dumping(self):
        (self.root / 'postgresql.private.log').write_text(
            'db error: failed to download vulnerability DB: https://secret:password@example.invalid/private')
        code, output = self.finish('failure')
        self.assertEqual(code, 1)
        self.assertIn('SCAN_DB_DOWNLOAD_FAILED', output)
        self.assertIn('SCAN_REPORT_MISSING', output)
        self.assertNotIn('password', output); self.assertNotIn('https', output)

    def test_image_error_without_report_is_not_claimed_as_vulnerability(self):
        (self.root / 'postgresql.private.log').write_text('unable to inspect the image: private information')
        code, output = self.finish('failure')
        self.assertEqual(code, 1)
        self.assertIn('SCAN_IMAGE_ERROR', output)
        self.assertNotIn('VULNERABILITIES_BLOCKED', output)

    def test_missing_invalid_or_wrong_image_report_never_passes(self):
        self.assertIn('SCAN_REPORT_MISSING', self.finish('failure')[1])
        for value in ('{', 'null', '{}', '{"SchemaVersion":1}',
                      json.dumps({'SchemaVersion': 2, 'Metadata': {'ImageID': 'sha256:'+'b'*64}})):
            (self.root / 'postgresql.json').write_text(value)
            code, output = self.finish('failure')
            self.assertEqual(code, 1)
            self.assertIn('SCAN_REPORT_INVALID', output)

    def test_failed_action_with_clean_report_still_fails(self):
        self.report()
        code, output = self.finish('failure')
        self.assertEqual(code, 1)
        self.assertIn('SCAN_TECHNICAL_FAILED', output)

    def test_success_outcome_cannot_override_blocking_findings(self):
        self.report([{'Severity': 'CRITICAL', 'PkgName': 'libssl3'}])
        code, output = self.finish('success')
        self.assertEqual(code, 1)
        self.assertIn('SCAN_VULNERABILITIES_BLOCKED', output)

    def test_unknown_artifact_error_does_not_invent_database_cause(self):
        (self.root / 'postgresql.private.log').write_text('failed to download artifact: unknown')
        code, output = self.finish('failure')
        self.assertEqual(code, 1)
        self.assertNotIn('SCAN_DB_DOWNLOAD_FAILED', output)
        self.assertIn('SCAN_REPORT_MISSING', output)

    def test_capture_keeps_both_streams_private_and_preserves_exit_code(self):
        def fake_run(args, **kwargs):
            self.assertEqual(args, [str(self.root/'trivy-real'), 'image', 'synthetic'])
            self.assertIs(kwargs['stdout'], kwargs['stderr'])
            kwargs['stderr'].write(b'private raw error')
            return subprocess.CompletedProcess(args, 1)
        with patch.object(scan.subprocess, 'run', side_effect=fake_run), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(scan.capture(self.root, 'postgresql', ['image', 'synthetic']), 1)
        self.assertEqual(output.getvalue(), '')
        self.assertEqual((self.root/'postgresql.private.log').stat().st_mode & 0o777, 0o600)

    def test_final_gate_validates_all_reports_and_rejects_skipped_scans(self):
        outcomes = {name: 'success' for name in scan.SUBJECTS}
        with patch.object(scan, 'diagnose', return_value=[]), patch.object(scan, 'validate_reports', return_value={}) as check:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(scan.finish(self.root, outcomes), 0)
                check.assert_called_once()
                outcomes['runner'] = 'skipped'
                self.assertEqual(scan.finish(self.root, outcomes), 1)
                check.assert_called_once()

    def test_workflow_runs_diagnostics_after_failure_but_never_integration(self):
        workflow = yaml.safe_load((ROOT/'.github/workflows/ec016_integration.yml').read_text())
        jobs = workflow['jobs']; steps = jobs['scan']['steps']
        scans = [step for step in steps if step.get('id', '').startswith('scan_')]
        self.assertEqual(len(scans), 4)
        for step in scans:
            self.assertNotIn('continue-on-error', step)
            self.assertEqual(step['with']['exit-code'], '1')
            self.assertEqual(step['with']['severity'], 'HIGH,CRITICAL')
            self.assertNotIn('if', step)  # Default success(): stop subsequent scans on failure.
        final = steps[-1]
        self.assertIn('always()', final['if'])
        self.assertIn('steps.source.outcome', final['if'])
        self.assertNotIn('continue-on-error', final)
        for step in scans:
            self.assertIn('steps.' + step['id'] + '.outcome', final['env']['EC016_SCAN_OUTCOMES'])
        self.assertEqual(jobs['integration']['needs'], 'scan')
        self.assertEqual(jobs['integration']['if'], "${{ needs.scan.result == 'success' }}")
        for outcome in ('failure', 'cancelled', 'skipped'):
            self.assertFalse(outcome == 'success')


if __name__ == '__main__':
    unittest.main()
