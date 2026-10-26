"""Only the dependency tmpfs permits loading fixed binary extension wheels."""
import io
import json
import types
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from infra.ec016 import services
from infra.ec016.runner import safe_report
from infra.ec016.github_runner import validate_report_structure


class ImportEnvironment(unittest.TestCase):
    def test_native_runner_uses_noexec_temp_and_exec_dependency_mount(self):
        import ast
        source=Path(services.__file__).read_text()
        tree=ast.parse(source)
        function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='test_container')
        args=next(n.value for n in function.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='args' for t in n.targets))
        values=[n.value if isinstance(n,ast.Constant) else None for n in args.elts]
        mounts=[values[i+1] for i,v in enumerate(values) if v=='--tmpfs']
        self.assertEqual(mounts,['/tmp:rw,noexec,nosuid,nodev,size=512m,mode=1777',
                                 '/tmp/deps:rw,exec,nosuid,nodev,size=256m,mode=1777'])
        self.assertIn('--read-only',values);self.assertIn('10001:10001',values)
        self.assertIn('PYTHONPATH=/tmp/deps:/lab',values)
        self.assertIn('--require-hashes',ast.get_source_segment(source,function))

    def test_all_three_imports_before_loading_unittest_suite(self):
        psycopg=types.SimpleNamespace(pq=types.SimpleNamespace(__impl__='binary'))
        with patch.object(safe_report.importlib,'import_module',side_effect=[psycopg,object(),object()]) as load:
            self.assertIsNone(safe_report.check_dependencies())
        self.assertEqual([call.args[0] for call in load.call_args_list],['psycopg','httpx','postgrest'])

    def test_early_failure_emits_only_fixed_code_and_never_starts_tests(self):
        for code in ('SETUP_POSTGRES_IMPORT','SETUP_HTTPX_IMPORT','SETUP_POSTGREST_IMPORT'):
            with self.subTest(code=code),patch.object(safe_report,'check_dependencies',return_value=code), \
                 patch.object(safe_report.unittest.defaultTestLoader,'loadTestsFromTestCase') as load, \
                 patch.object(sys,'stdout',io.StringIO()) as output:
                with self.assertRaises(SystemExit) as caught:safe_report.main()
                self.assertEqual(caught.exception.code,1)
                load.assert_not_called()
                report=json.loads(output.getvalue());validate_report_structure(report)
                self.assertEqual(report['startup_code'],code)
                self.assertEqual(report['tests_run'],0)

    def test_loader_denial_is_caught_without_exporting_its_message(self):
        with patch.object(safe_report.importlib,'import_module',side_effect=ImportError('PRIVATE failed to map segment from shared object')), \
             patch.object(sys,'stdout',io.StringIO()) as output:
            self.assertEqual(safe_report.check_dependencies(),'SETUP_POSTGRES_IMPORT')
            self.assertEqual(output.getvalue(),'')

    def test_no_silent_fallback_to_unlocked_system_libpq(self):
        with patch.object(safe_report.importlib,'import_module',return_value=types.SimpleNamespace(pq=types.SimpleNamespace(__impl__='python'))):
            self.assertEqual(safe_report.check_dependencies(),'SETUP_POSTGRES_IMPORT')
