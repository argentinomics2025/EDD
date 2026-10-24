"""Final authorization/security/orchestration checks. No services or SQL."""
import datetime
import io
import json
import os
from pathlib import Path
import re
import tempfile
import textwrap
import unittest
from unittest.mock import patch
from infra.ec016 import github_runner,security_gate,labctl

ROOT=Path(__file__).resolve().parents[1]
SHA='e'*40


def dispatch_script():
    text=(ROOT/'.github/workflows/ec016_integration.yml').read_text()
    start=text.index("          import json, os, re, sys")
    end=text.index('\n          PY',start)
    return textwrap.dedent(text[start:end])


def context():
    return {'GITHUB_ACTIONS':'true','GITHUB_EVENT_NAME':'workflow_dispatch',
            'GITHUB_REPOSITORY':'argentinomics2025/EDD','GITHUB_REF':'refs/heads/main',
            'GITHUB_WORKFLOW_REF':'argentinomics2025/EDD/.github/workflows/ec016_integration.yml@refs/heads/main',
            'GITHUB_RUN_ATTEMPT':'1','RUNNER_ENVIRONMENT':'github-hosted','RUNNER_OS':'Linux','RUNNER_ARCH':'X64','ImageOS':'ubuntu24',
            'EC016_SOURCE_SHA':SHA,'EC016_APPROVED_SHA':SHA,
            'EC016_MANUAL_CONFIRMATION':'EC016_DISPOSABLE_ONLY:'+SHA}


def report(issues=None):
    return {'SchemaVersion':2,'Results':[{'Packages':[{'Name':'synthetic-fixture'}],
                                        'Vulnerabilities':issues or []}]}


class CompletionTests(unittest.TestCase):
    def setUp(self):
        for target in ('socket.socket.connect','subprocess.run'):
            block=patch(target,side_effect=AssertionError('No services/processes allowed in unit tests'))
            block.start();self.addCleanup(block.stop)

    def authorize(self, environment=None, payload=None):
        env=context() if environment is None else environment
        event={'repository':{'full_name':'argentinomics2025/EDD','private':False},
               'inputs':{'lab_sha':SHA,'confirmation':'EC016_DISPOSABLE_ONLY:'+SHA}} if payload is None else payload
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory);(path/'event.json').write_text(json.dumps(event))
            env=dict(env,GITHUB_EVENT_PATH=str(path/'event.json'),GITHUB_OUTPUT=str(path/'output'))
            with patch.dict(os.environ,env,clear=True):exec(compile(dispatch_script(),'trusted-main-policy','exec'),{})
            return (path/'output').read_text()

    def test_stable_policy_accepts_exact_authorization(self):
        self.assertEqual(self.authorize(),'sha='+SHA+'\n')

    def test_missing_or_different_approval_never_downloads_experimental_code(self):
        for value in ('','main','e'*39,'f'*40,SHA+'\n'):
            e=context();e['EC016_APPROVED_SHA']=value
            with self.subTest(value=value),self.assertRaises(SystemExit):self.authorize(e)

    def test_ref_short_sha_and_shell_injection_rejected(self):
        for value in ('fix/ica-safe-ingestion','e'*7,'$(id)',"e'*40;echo nope",'E'*40,SHA+'\n'):
            e=context();e['EC016_SOURCE_SHA']=value;e['EC016_APPROVED_SHA']=value
            with self.subTest(value=value),self.assertRaises(SystemExit):self.authorize(e)

    def test_authorization_is_explicit_not_fake_dual_review(self):
        e=context();e['EC016_MANUAL_CONFIRMATION']='YES'
        with self.assertRaises(SystemExit):self.authorize(e)
        workflow=(ROOT/'.github/workflows/ec016_integration.yml').read_text()
        self.assertNotRegex(workflow,r'(?m)^    environment:')
        self.assertIn('${{ vars.EC016_APPROVED_SHA }}',workflow)
        self.assertLess(workflow.index('id: authorization'),workflow.index('uses: actions/checkout@'))

    def test_main_dispatch_and_public_repo_are_mandatory(self):
        for key,value in [('GITHUB_REF','refs/heads/fix/ica-safe-ingestion'),('GITHUB_EVENT_NAME','push'),('RUNNER_ENVIRONMENT','self-hosted')]:
            e=context();e[key]=value
            with self.assertRaises(SystemExit):self.authorize(e)
        with self.assertRaises(SystemExit):self.authorize(payload={'repository':{'private':True}})

    def test_rerun_does_not_replay_original_authorization(self):
        e=context();e['GITHUB_RUN_ATTEMPT']='2'
        with self.assertRaises(SystemExit):self.authorize(e)

    def test_scanner_digest_and_platform_have_registry_evidence(self):
        self.assertRegex(security_gate.scanner_reference(),r'^docker.io/aquasec/trivy:[0-9.]+@sha256:[a-f0-9]{64}$')

    def test_fresh_database_required(self):
        now=datetime.datetime(2026,10,24,tzinfo=datetime.timezone.utc)
        security_gate.validate_database({'Version':2,'UpdatedAt':now.isoformat(),'DownloadedAt':now.isoformat()},now)
        for stamp in (now-datetime.timedelta(days=4),now+datetime.timedelta(days=1)):
            with self.assertRaises(RuntimeError):security_gate.validate_database({'Version':2,'UpdatedAt':stamp.isoformat(),'DownloadedAt':now.isoformat()},now)
        with self.assertRaises(RuntimeError):security_gate.validate_database({'Version':1},now)

    def test_known_critical_or_fixable_high_blocks_sql(self):
        for severity,fixed in [('CRITICAL',''),('CRITICAL','2.0'),('HIGH','2.0')]:
            issue={'VulnerabilityID':'CVE-2099-0001','Severity':severity,'FixedVersion':fixed}
            with self.assertRaises(RuntimeError):security_gate.review_report(report([issue]))

    def test_cvss_cannot_hide_critical_under_unknown_severity(self):
        issue={'VulnerabilityID':'CVE-2099-0001','Severity':'UNKNOWN','CVSS':{'source':{'V3Score':9.8}}}
        with self.assertRaises(RuntimeError):security_gate.review_report(report([issue]))

    def test_cvss_v4_critical_and_invalid_scores_are_rejected(self):
        for score in (9.5,'unknown',float('nan')):
            issue={'VulnerabilityID':'CVE-2099-0001','Severity':'UNKNOWN','CVSS':{'source':{'V4Score':score}}}
            with self.assertRaises(RuntimeError):security_gate.review_report(report([issue]))

    def test_unfixed_high_has_explicit_lab_only_count(self):
        issue={'VulnerabilityID':'CVE-2099-0001','Severity':'HIGH','FixedVersion':''}
        counts=security_gate.review_report(report([issue]))
        self.assertEqual(counts['high_unfixed'],1);self.assertEqual(counts['critical'],0)

    def test_empty_inventory_is_not_claimed_clean(self):
        empty={'SchemaVersion':2,'Results':[]}
        with self.assertRaises(RuntimeError):security_gate.review_report(empty)
        result=security_gate.review_report(empty,allow_inventory_gap=True)
        self.assertTrue(result['inventory_unavailable']);self.assertEqual(result['packages'],0)
        with self.assertRaises(RuntimeError):security_gate.review_report({'SchemaVersion':1,'Results':[]},allow_inventory_gap=True)

    def test_scanner_has_no_socket_or_credentials(self):
        m={'scope':'EC016_DISPOSABLE_SYNTHETIC_ONLY','run_id':'a'*32,'owner_token':'b'*64,
           'project':'ec016-'+'a'*32,'network':'ec016-'+'a'*32+'-isolated','host_netns':'net:[123]'}
        args=security_gate.sandbox_args(m,'unit',Path('/tmp/synthetic-cache'))
        self.assertIn('--read-only',args);self.assertIn('--cap-drop',args)
        self.assertIn('--rm',args);self.assertNotIn('docker.sock',json.dumps(args))
        self.assertNotIn('--privileged',args)

    def test_scan_and_firewall_precede_bootstrap(self):
        code=(ROOT/'infra/ec016/github_runner.py').read_text()
        self.assertLess(code.index('scan_before_bootstrap(state'),code.index("'container','start',by_role['ec016-db']"))
        self.assertLess(code.index('verify_clearance(state'),code.index("'container','start',by_role['ec016-db']"))
        entry=(ROOT/'infra/ec016/db-entrypoint.sh').read_text()
        self.assertLess(entry.index('security.ok'),entry.index('exec /usr/local/bin/docker-entrypoint.sh'))

    def test_security_proof_from_another_run_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory);(state/'metadata').mkdir()
            (state/'metadata/security.json').write_text(json.dumps({'run_id':'foreign'}))
            m={'run_id':'expected','owner_token':'expected','engine_id':'expected','github_context':{'source_sha':SHA}}
            with self.assertRaises(RuntimeError):security_gate.verify_clearance(state,m)

    def test_public_security_metadata_has_verified_hashes_and_no_claimed_image_clearance(self):
        data=json.loads((ROOT/'infra/ec016/locks/security-review.json').read_text())
        self.assertEqual(len(data['dependencies']),19)
        self.assertTrue(all(x['hashes_verified'] for x in data['dependencies']))
        self.assertTrue(data['material_limits'])


if __name__=='__main__':unittest.main()
