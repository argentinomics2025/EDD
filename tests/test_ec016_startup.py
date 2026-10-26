"""Simulate setUpClass without a real socket or SQL and preserve error privacy."""
import io
import json
import types
import sys
import unittest
from unittest.mock import Mock,patch
from infra.ec016.runner import integration_suite as suite, safe_report, lab_guard
from infra.ec016.runner.startup import StartupError
from infra.ec016.github_runner import validate_report_structure


class StartupTests(unittest.TestCase):
    def setup_patches(self):
        class TransportError(Exception):pass
        self.transport_error=TransportError
        p=patch.dict(sys.modules,{'httpx':types.SimpleNamespace(TransportError=TransportError)})
        p.start();self.addCleanup(p.stop)
        for name,target in [('runtime_context',{}),('admin_connection',Mock()),('api_client',(Mock(),Mock()))]:
            p=patch.object(suite,name,return_value=target);mock=p.start();self.addCleanup(p.stop)
            setattr(self,name,mock)
        p=patch.object(suite.time,'sleep');p.start();self.addCleanup(p.stop)
        self.client=self.api_client.return_value[0]
        self.client.from_.return_value.select.return_value.execute.return_value.data=[{'value':'scope','run_id':'r','owner_token':'o'}]
        p=patch.object(suite.policy,'validate_marker_payload');p.start();self.addCleanup(p.stop)

    def test_successful_setup_queries_metadata_and_closes_both_sessions(self):
        self.setup_patches();suite.DisposableIntegration.setUpClass()
        self.admin_connection.return_value.close.assert_called_once()
        self.client.session.close.assert_called_once()
        self.client.from_.assert_called_once_with('ec016_metadata')

    def test_each_initialization_failure_remains_zero_tests_with_safe_code(self):
        for phase in ['SETUP_POSTGRES_CONNECTION','SETUP_SDK','SETUP_METADATA_QUERY',
                      'SETUP_POSTGREST_UNAVAILABLE','SETUP_IDENTITY','SETUP_SESSION_CLOSE']:
            with self.subTest(phase=phase):
                self.setup_patches()
                secret='SENSITIVE_SENTINEL'
                if phase=='SETUP_POSTGRES_CONNECTION':self.admin_connection.side_effect=RuntimeError(secret)
                elif phase=='SETUP_SDK':self.api_client.side_effect=AttributeError(secret)
                elif phase=='SETUP_SESSION_CLOSE':self.admin_connection.return_value.close.side_effect=RuntimeError(secret)
                elif phase=='SETUP_IDENTITY':self.client.from_.return_value.select.return_value.execute.return_value.data=[]
                else:self.client.from_.return_value.select.return_value.execute.side_effect=(self.transport_error(secret) if phase=='SETUP_POSTGREST_UNAVAILABLE' else RuntimeError(secret))
                # Real unittest invokes the actual setUpClass and never starts test bodies.
                class Synthetic(unittest.TestCase):
                    setUpClass=classmethod(lambda cls:suite.DisposableIntegration.setUpClass())
                    def runTest(self):raise AssertionError('Test must not start')
                report=safe_report.run_suite(unittest.TestSuite([Synthetic()]))
                self.assertEqual(report['tests_run'],0)
                self.assertEqual(report['errors'],1)
                self.assertEqual(report['startup_code'],phase)
                validate_report_structure(report)
                self.assertNotIn(secret,json.dumps(report))
                self.doCleanups()

    def test_admin_query_identity_failure_closes_connection_without_real_sql(self):
        connection=Mock();connection.execute.side_effect=RuntimeError('SENSITIVE_SENTINEL')
        psycopg=types.SimpleNamespace(connect=Mock(return_value=connection))
        with patch.dict(sys.modules,{'psycopg':psycopg}),patch.object(lab_guard,'runtime_context',return_value={}), \
             patch.object(lab_guard.socket,'gethostbyname',return_value=lab_guard.DB_HOST), \
             patch.object(lab_guard.socket,'create_connection'):

            with self.assertRaises(StartupError) as caught:lab_guard.admin_connection()
        self.assertEqual(caught.exception.code,'SETUP_METADATA_QUERY')
        connection.close.assert_called_once()

    def test_report_cannot_export_arbitrary_startup_messages(self):
        report={'tests_run':0,'failures':0,'errors':1,'skipped':0,'successful':False,'startup_code':'PRIVATE'}
        with self.assertRaises(RuntimeError):validate_report_structure(report)
