"""Functional workflow is separate from security certification; offline tests."""
import hashlib
import json
import os
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
        self.assertEqual(set(w['jobs']),{'functional'})
        job=w['jobs']['functional']
        self.assertEqual(job['runs-on'],'ubuntu-24.04')
        self.assertEqual(set(job['services']),{'postgres'})
        self.assertNotIn('ports',job['services']['postgres'])
        self.assertNotIn('volumes',job['services']['postgres'])
        for forbidden in ('secrets.', 'continue-on-error', 'trivy-action', 'self-hosted', 'upload-artifact'):
            self.assertNotIn(forbidden,raw)
        self.assertIn('EC016_FUNCTIONAL_ONLY_ACCEPT_IMAGE_RISK',raw)
        steps=job['steps']
        self.assertEqual(steps[0]['id'],'authorization')
        self.assertIn('sha == approved',steps[0]['run'])
        self.assertIn("event.get('inputs', {}).get('image_risk')",steps[0]['run'])
        self.assertIn('services test',steps[-2]['run'])

    def test_security_workflow_and_original_criteria_unchanged(self):
        for name,digest in [
            ('.github/workflows/ec016_integration.yml','0a1bde734bd6d9370dde0c288e535b75fb1a554aea6aefc2076a0a0a0f98ce46'),
            ('infra/ec016/runner/integration_suite.py','2d69f93e0ec55358e942a17533a85d7672cb04cc4be476c5a06a5f1cdf86ef65')]:
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
