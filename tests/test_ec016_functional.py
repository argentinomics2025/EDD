"""Functional workflow is separate from security certification; offline tests."""
import hashlib
import ast
import json
import os
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import yaml
from infra.ec016 import services, github_runner

ROOT=Path(__file__).resolve().parents[1]


class FunctionalWorkflow(unittest.TestCase):
    def workflow(self):
        return yaml.safe_load((ROOT/'.github/workflows/ec016_functional.yml').read_text())

    def test_manual_minimal_synthetic_only(self):
        raw=(ROOT/'.github/workflows/ec016_functional.yml').read_text()
        w=self.workflow()
        trigger=w.get('on',w.get(True))
        self.assertEqual(set(trigger),{'workflow_dispatch'})
        self.assertEqual(w['permissions'],{'contents':'read'})
        self.assertEqual(set(w['jobs']),{'authorize','functional'})
        job=w['jobs']['functional']
        self.assertEqual(job['runs-on'],'ubuntu-24.04')
        self.assertEqual(set(job['services']),{'postgres'})
        self.assertNotIn('ports',job['services']['postgres'])
        self.assertNotIn('volumes',job['services']['postgres'])
        for forbidden in ('secrets.', 'continue-on-error', 'trivy-action', 'self-hosted', 'upload-artifact'):
            self.assertNotIn(forbidden,raw)
        self.assertIn('EC016_FUNCTIONAL_ONLY_ACCEPT_IMAGE_RISK',raw)
        authorization=w['jobs']['authorize']
        self.assertNotIn('services',authorization)
        self.assertNotIn('container',authorization)
        self.assertEqual(authorization['runs-on'],'ubuntu-24.04')
        self.assertEqual(job['needs'],'authorize')
        self.assertEqual(job['if'],"${{ needs.authorize.result == 'success' }}")
        self.assertEqual(job['steps'][0]['with']['ref'], '${{ needs.authorize.outputs.lab_sha }}')
        steps=authorization['steps']
        self.assertEqual(len(steps),1)
        self.assertEqual(steps[0]['id'],'authorization')
        self.assertIn('sha == approved',steps[0]['run'])
        self.assertIn("event.get('inputs', {}).get('image_risk')",steps[0]['run'])
        self.assertIn('services test',job['steps'][-2]['run'])

    def test_authorization_rejects_bad_sha_branch_context_and_risk_before_service_job(self):
        job=self.workflow()['jobs']['authorize']
        script=job['steps'][0]['run'].split("python3 - <<'PY'\n",1)[1].rsplit('\nPY',1)[0]
        sha='a'*40
        with tempfile.TemporaryDirectory() as directory:
            event=Path(directory)/'event.json';output=Path(directory)/'output'
            event.write_text(json.dumps({'repository':{'private':False,'full_name':'argentinomics2025/EDD'},
                'inputs':{'lab_sha':sha,'confirmation':'EC016_DISPOSABLE_ONLY:'+sha,
                          'image_risk':'EC016_FUNCTIONAL_ONLY_ACCEPT_IMAGE_RISK'}}))
            env={'GITHUB_ACTIONS':'true','GITHUB_EVENT_NAME':'workflow_dispatch',
                'GITHUB_REPOSITORY':'argentinomics2025/EDD','GITHUB_REF':'refs/heads/main',
                'GITHUB_WORKFLOW_REF':github_runner.FUNCTIONAL_WORKFLOW,
                'RUNNER_ENVIRONMENT':'github-hosted','RUNNER_OS':'Linux','RUNNER_ARCH':'X64','ImageOS':'ubuntu24',
                'GITHUB_RUN_ATTEMPT':'1','EC016_SOURCE_SHA':sha,'EC016_APPROVED_SHA':sha,
                'EC016_MANUAL_CONFIRMATION':'EC016_DISPOSABLE_ONLY:'+sha,
                'EC016_FUNCTIONAL_RISK':'EC016_FUNCTIONAL_ONLY_ACCEPT_IMAGE_RISK',
                'GITHUB_EVENT_PATH':str(event),'GITHUB_OUTPUT':str(output)}
            with patch.dict(os.environ,env,clear=True):exec(compile(script,'authorization','exec'),{})
            self.assertEqual(output.read_text(),'sha='+sha+'\n')
            for key,value in [('EC016_APPROVED_SHA','b'*40),('GITHUB_REF','refs/heads/test'),
                              ('RUNNER_ENVIRONMENT','self-hosted'),('EC016_FUNCTIONAL_RISK','')]:
                output.unlink(missing_ok=True)
                with self.subTest(key=key),patch.dict(os.environ,dict(env,**{key:value}),clear=True):
                    with self.assertRaises(SystemExit):exec(compile(script,'authorization','exec'),{})
                self.assertFalse(output.exists())

    def test_security_workflow_and_original_criteria_unchanged(self):
        for name,digest in [
            ('.github/workflows/ec016_integration.yml','0a1bde734bd6d9370dde0c288e535b75fb1a554aea6aefc2076a0a0a0f98ce46')]:
            self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),digest)
        body=(ROOT/'infra/ec016/schema.sql').read_text().partition(services.SCHEMA_MARKER)[2]
        self.assertEqual(hashlib.sha256(body.encode()).hexdigest(),'9cb38846a192b5171dc02213ee4ea38ff8382a98872f408523b2be1289e8fe7b')

    def test_functional_risk_acceptance_cannot_be_implicit(self):
        env={'GITHUB_WORKFLOW_REF':github_runner.FUNCTIONAL_WORKFLOW,'GITHUB_EVENT_PATH':'synthetic'}
        with patch.dict(os.environ,env,clear=True),patch.object(Path,'read_text',return_value='{"inputs":{}}'), \
             patch.object(github_runner,'validate_host_context') as validate:
            with self.assertRaises(RuntimeError):services.host_context()
            validate.assert_not_called()

    def test_only_two_fixed_workflow_identities_are_possible(self):
        with self.assertRaises(Exception):github_runner.validate_host_context({}, {}, workflow='untrusted')
        with patch.object(github_runner,'validate_host_context',side_effect=RuntimeError('stop')) as validate, \
             patch.dict(os.environ,{'GITHUB_WORKFLOW_REF':github_runner.FUNCTIONAL_WORKFLOW,
                                  'GITHUB_EVENT_PATH':'synthetic',
                                  'EC016_FUNCTIONAL_RISK':'EC016_FUNCTIONAL_ONLY_ACCEPT_IMAGE_RISK'},clear=True), \
             patch.object(Path,'read_text',return_value=json.dumps({'inputs':{'image_risk':'EC016_FUNCTIONAL_ONLY_ACCEPT_IMAGE_RISK'}})):
            with self.assertRaises(RuntimeError):services.host_context()
            validate.assert_called_once_with(workflow=github_runner.FUNCTIONAL_WORKFLOW)
