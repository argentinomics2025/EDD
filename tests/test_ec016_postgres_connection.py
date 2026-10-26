"""Driver/DNS/TCP/authentication separation, with no sockets or SQL."""
from contextlib import ExitStack
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock,patch
import yaml
from infra.ec016.runner import lab_guard as guard, safe_report
from infra.ec016.runner.startup import StartupError
from infra.ec016.github_runner import validate_report_structure


class PostgresConnection(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.driver=types.SimpleNamespace(connect=Mock())
        self.connection=self.driver.connect.return_value
        self.connection.execute.return_value.fetchone.return_value=('ec016_disposable','ec016_admin',{})
        self.stack.enter_context(patch.dict(sys.modules,{'psycopg':self.driver}))
        self.stack.enter_context(patch.object(guard,'runtime_context',return_value={'postgres_ip':'172.20.0.2'}))
        self.stack.enter_context(patch.object(guard,'validate_marker'))
        self.dns=self.stack.enter_context(patch.object(guard.socket,'gethostbyname',return_value='172.20.0.2'))
        self.tcp=self.stack.enter_context(patch.object(guard.socket,'create_connection'))

    def assert_code(self,code):
        with self.assertRaises(StartupError) as caught:guard.admin_connection()
        self.assertEqual(caught.exception.code,code)
        self.assertEqual(str(caught.exception),code)

    def test_import_failure_never_reaches_dns_or_tcp(self):
        with patch.dict(sys.modules,{'psycopg':None}):self.assert_code('SETUP_POSTGRES_IMPORT')
        self.dns.assert_not_called();self.tcp.assert_not_called()

    def test_dns_failure_and_wrong_identity_never_open_socket(self):
        self.dns.side_effect=OSError('PRIVATE')
        self.assert_code('SETUP_POSTGRES_DNS')
        self.dns.side_effect=None;self.dns.return_value='8.8.8.8'
        self.assert_code('SETUP_IDENTITY')
        self.tcp.assert_not_called();self.driver.connect.assert_not_called()

    def test_tcp_failure_never_attempts_credentials(self):
        self.tcp.side_effect=TimeoutError('PRIVATE')
        self.assert_code('SETUP_POSTGRES_TCP')
        self.tcp.assert_called_once_with(('172.20.0.2',5432),timeout=3)
        self.driver.connect.assert_not_called()

    def test_auth_database_and_unknown_handshake_codes(self):
        for message,expected in [('password authentication failed for user "PRIVATE"','AUTH'),
                                 ('no pg_hba.conf entry for host PRIVATE','AUTH'),
                                 ('database "ec016_disposable" does not exist','DATABASE'),
                                 ('PRIVATE unknown failure','HANDSHAKE')]:
            with self.subTest(expected=expected):
                self.driver.connect.side_effect=RuntimeError(message)
                self.assert_code('SETUP_POSTGRES_'+expected)
        error=RuntimeError('PRIVATE');error.sqlstate='3D000'
        self.driver.connect.side_effect=error;self.assert_code('SETUP_POSTGRES_DATABASE')

    def test_success_pins_private_ip_and_matches_native_postgres_credentials(self):
        self.assertIs(guard.admin_connection(),self.connection)
        parameters=self.driver.connect.call_args.kwargs
        self.assertEqual(parameters['hostaddr'],'172.20.0.2')
        self.assertTrue(parameters['autocommit'])
        self.assertEqual(parameters['port'],5432)
        root=Path(__file__).resolve().parents[1]
        workflow=yaml.safe_load((root/'.github/workflows/ec016_functional.yml').read_text())
        pg=workflow['jobs']['functional']['services']['postgres']['env']
        for client,server in [('dbname','POSTGRES_DB'),('user','POSTGRES_USER'),('password','POSTGRES_PASSWORD')]:
            self.assertEqual(parameters[client],pg[server])
        self.tcp.return_value.__exit__.assert_called_once()
        guard.validate_marker.assert_called_once()

    def test_all_new_codes_survive_safe_report_without_private_details(self):
        for suffix in ('IMPORT','DNS','TCP','AUTH','DATABASE','HANDSHAKE'):
            code='SETUP_POSTGRES_'+suffix
            class Synthetic(unittest.TestCase):
                @classmethod
                def setUpClass(cls):
                    try:raise RuntimeError('PRIVATE_SENTINEL')
                    except Exception as error:raise StartupError(code) from error
                def runTest(self):raise AssertionError('must not execute')
            report=safe_report.run_suite(unittest.TestSuite([Synthetic()]))
            validate_report_structure(report)
            self.assertEqual(report['startup_code'],code)
            self.assertEqual(report['tests_run'],0)
            self.assertNotIn('PRIVATE',json.dumps(report))
