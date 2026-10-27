"""Offline regressions for Trixie inspection; no container, network or SQL."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from infra.ec017 import collect_reports as reports, dependency_probe

ROOT=Path(__file__).resolve().parents[1]


def inventory():
    return {'psycopg':'3.2.6','psycopg_binary':'3.2.6','implementation':'binary',
            'libpq_version':170004,'openssl_version':'OpenSSL 3.4.1 11 Feb 2025',
            'private_libraries':[{'name':'libpq-test.so.5','sha256':'a'*64}],
            'extensions':[],'transitive_advisory_coverage':'not_established'}


class NativeInventory(unittest.TestCase):
    def test_gosu_and_go_versions_are_separate_from_os_packages(self):
        report={'Results':[{'Type':'gobinary','Target':'usr/local/bin/gosu',
                           'Packages':[{'Name':'github.com/tianon/gosu','Version':'v1.19.0'},
                                       {'Name':'stdlib','Version':'v1.24.6'}]},
                          {'Type':'debian','Packages':[{'Name':'libpq5','Version':'17.11'},
                                                      {'Name':'libssl3t64','Version':'3.5.4'}]}]}
        data=reports.assets(report)
        self.assertTrue(data['gosu_found'])
        self.assertEqual(len(data['observed']),4)
        self.assertEqual(data['observed'][1]['package'],'stdlib')
        self.assertTrue(reports.assets({})['empty_inventory'])
        self.assertFalse(reports.assets({})['gosu_found'])

    def test_native_probe_uses_isolated_nonroot_readonly_no_network_container(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence=Path(directory)
            with patch.object(reports,'docker',return_value=json.dumps(inventory())) as docker, \
                 patch('sys.stdout',io.StringIO()) as output:
                receipt=reports.native_inventory(ROOT,evidence,'candidate','fixed-runner')
            args=docker.call_args.args[0]
            for flag,value in [('--network','none'),('--user','10001:10001'),('--cap-drop','ALL')]:
                self.assertEqual(args[args.index(flag)+1],value)
            self.assertIn('--read-only',args);self.assertIn('--rm',args)
            self.assertNotIn('/var/run/docker.sock',' '.join(args))
            self.assertNotIn('secrets',' '.join(args));self.assertIn('readonly',args[args.index('--mount')+1])
            self.assertEqual(args[-3:],['fixed-runner','python','/ec017-probe.py'])
            data=json.loads((evidence/receipt['file']).read_text())
            self.assertEqual(data['libpq_version'],170004)
            self.assertEqual(data['transitive_advisory_coverage'],'not_established')
            self.assertEqual(output.getvalue(),'')

    def test_invalid_probe_data_cannot_be_written_as_evidence(self):
        for raw in ['PRIVATE_RAW_ERROR','{}',json.dumps(dict(inventory(),implementation='python')),
                    json.dumps(dict(inventory(),extra_environment='PRIVATE'))]:
            with self.subTest(raw=raw),tempfile.TemporaryDirectory() as directory,patch.object(reports,'docker',return_value=raw):
                with self.assertRaises((ValueError,TypeError)):
                    reports.native_inventory(ROOT,Path(directory),'candidate','fixed-runner')
                self.assertEqual(list(Path(directory).iterdir()),[])

    def test_probe_source_has_no_database_or_network_operations(self):
        source=Path(dependency_probe.__file__).read_text()
        self.assertNotIn('psycopg.connect',source)
        self.assertNotIn('import socket',source)
        self.assertNotIn('os.environ',source)
        self.assertIn('PQlibVersion',source);self.assertIn('OpenSSL_version',source)
        self.assertIn('not_established',source)

    def test_native_probe_does_not_accept_python_fallback(self):
        import sys,types
        fake=types.SimpleNamespace(pq=types.SimpleNamespace(__impl__='python'))
        with patch.dict(sys.modules,{'psycopg':fake,'psycopg_binary':types.SimpleNamespace()}):
            with self.assertRaises(RuntimeError):dependency_probe.inventory()
