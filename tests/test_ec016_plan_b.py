"""Plan B regressions: no Docker, SQL, network or workflow execution."""
import ast
import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
from infra.ec016 import services,plan_b_reports,github_runner
from infra.ec016.runner import lab_guard,policy

ROOT=Path(__file__).resolve().parents[1]


def context():
    return {'mode':services.MODE,'scope':policy.SCOPE,'run_id':'a'*32,'owner_token':'b'*64,
            'source_sha':'c'*40,'workflow_run':'123','postgres_id':'d'*64,'postgres_ip':'172.20.0.2',
            'docker_network':'github_network_'+'e'*32,'postgrest_id':'f'*64,'postgrest_ip':'172.20.0.3'}


class PlanB(unittest.TestCase):
    def setUp(self):
        for name in ('socket.socket.connect','subprocess.run','sqlite3.connect'):
            block=patch(name,side_effect=AssertionError('No external services or SQL'))
            block.start();self.addCleanup(block.stop)

    def test_two_jobs_scan_precedes_native_postgres(self):
        text=(ROOT/'.github/workflows/ec016_integration.yml').read_text()
        scan,integration=text.split('  integration:\n',1)
        self.assertNotIn('    services:',scan)
        self.assertIn('    needs: scan',integration)
        self.assertIn("needs.scan.result == 'success'",integration)
        self.assertIn('    services:\n      postgres:',integration)
        self.assertNotRegex(integration,r'(?m)^\s+ports:')
        self.assertNotIn('continue-on-error',text)
        self.assertNotIn('github_runner',text);self.assertNotIn('compose',text)
        self.assertEqual(text.count('runs-on: ubuntu-24.04'),2)
        self.assertNotIn('secrets.',text);self.assertNotIn('upload-artifact',text)

    def test_official_action_pinned_native_binary_hashed_and_no_dynamic_setup(self):
        text=(ROOT/'.github/workflows/ec016_integration.yml').read_text()
        refs=re.findall(r'uses: ([^\s]+)',text)
        self.assertEqual(sum(r.startswith('aquasecurity/trivy-action@') for r in refs),4)
        for ref in refs:self.assertRegex(ref,r'@[a-f0-9]{40}$')
        for setting in ("skip-setup-trivy: 'true'","cache: 'false'","ignore-unfixed: 'false'","exit-code: '1'"):
            self.assertEqual(text.count(setting),4)
        self.assertEqual(text.count('severity: HIGH,CRITICAL'),4)
        self.assertIn('1816b632dfe529869c740c0913e36bd1629cb7688bd5634f4a858c1d57c88b75',text)
        self.assertIn('sha256sum --check --status',text)
        self.assertNotIn('--download-db-only',text)
        self.assertNotIn('db-repository',text)
        self.assertIn('empty.ignore',text);self.assertIn('config.yaml',text)

    def test_source_and_all_eleven_criteria_are_unchanged(self):
        file=ROOT/'infra/ec016/runner/integration_suite.py'
        self.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(),'2d69f93e0ec55358e942a17533a85d7672cb04cc4be476c5a06a5f1cdf86ef65')
        source=(ROOT/'infra/ec016/schema.sql').read_text().partition(services.SCHEMA_MARKER)[2]
        self.assertEqual(hashlib.sha256(source.encode()).hexdigest(),'9cb38846a192b5171dc02213ee4ea38ff8382a98872f408523b2be1289e8fe7b')

    def test_bootstrap_guard_is_before_shared_body(self):
        sql=services.bootstrap_sql(context())
        self.assertLess(sql.index('current_database()'),sql.index('CREATE ROLE'))
        self.assertIn("current_user<>'ec016_admin'",sql)
        self.assertIn("to_regnamespace('api') IS NOT NULL",sql)
        self.assertIn(context()['owner_token'],sql)
        self.assertIn('FORCE ROW LEVEL SECURITY',sql)
        with self.assertRaises(RuntimeError):services.bootstrap_sql(dict(context(),owner_token="'; unsafe"))

    def test_local_entrypoints_cannot_use_shared_daemon(self):
        with patch.dict(os.environ,{},clear=True),patch('sys.stdout',io.StringIO()):
            with self.assertRaises(SystemExit):services.main()
            with self.assertRaises(SystemExit):github_runner.main()

    def test_service_identity_rejects_public_ip_wrong_id_or_network(self):
        services.validate_context(context())
        for field,value in [('postgres_ip','8.8.8.8'),('postgrest_ip','8.8.8.8'),
                            ('postgres_id','untrusted'),('docker_network','bridge')]:
            with self.subTest(field=field),self.assertRaises(RuntimeError):services.validate_context(dict(context(),**{field:value}))

    def test_native_identity_uses_content_id_not_image_spelling(self):
        c=context();image_id='sha256:'+'1'*64
        container={'Image':image_id,'Config':{'Image':'normalized-image-name'},
                   'NetworkSettings':{'Networks':{c['docker_network']:{'NetworkID':'2'*64,'IPAddress':c['postgres_ip']}}}}
        with patch.object(services,'docker',side_effect=[json.dumps([container]),json.dumps([{'Id':image_id}])]):
            _,ip=services.inspect_owned(c['postgres_id'],c['docker_network'],'reviewed-image@digest')
            self.assertEqual(ip,c['postgres_ip'])
        with patch.object(services,'docker',side_effect=[json.dumps([container]),json.dumps([{'Id':'sha256:'+'3'*64}])]):
            with self.assertRaises(RuntimeError):services.inspect_owned(c['postgres_id'],c['docker_network'],'reviewed-image@digest')

    def test_readonly_context_is_replaced_not_written_in_place(self):
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory);services.save_context(state,context())
            first=(state/'context.json').stat().st_ino
            updated=dict(context(),postgrest_ip='172.20.0.4');services.save_context(state,updated)
            self.assertEqual(json.loads((state/'context.json').read_text())['postgrest_ip'],'172.20.0.4')
            self.assertEqual((state/'context.json').stat().st_mode&0o777,0o444)
            self.assertNotEqual(first,(state/'context.json').stat().st_ino)

    def test_native_markers_remain_bound_to_run(self):
        c=context();marker={'scope':policy.SCOPE,'run_id':c['run_id'],'owner_token':c['owner_token']}
        policy.validate_marker_payload(marker,c)
        with self.assertRaises(RuntimeError):policy.validate_marker_payload(dict(marker,run_id='f'*32),c)

    def test_native_runtime_checks_dns_before_opening_connection(self):
        e={'EC016_ACTIONS_SERVICES':services.MODE,'EC016_EXECUTE_DISPOSABLE':'YES_SYNTHETIC_ONLY',
           'EC016_SOURCE_SHA':context()['source_sha'],'EC016_WORKFLOW_RUN':'123'}
        with patch.dict(os.environ,e,clear=True),patch.object(services.Path,'is_file',return_value=True), \
             patch.object(services.Path,'read_text',return_value=json.dumps(context())), \
             patch('socket.gethostbyname',side_effect=['172.20.0.2','172.20.0.3']):
            self.assertEqual(services.runtime_context()['run_id'],context()['run_id'])
            lab_guard.validate_http_target('http://postgrest:3000/datos_comex')
            with self.assertRaises(ValueError):lab_guard.validate_http_target('https://example.supabase.co/rest/v1/datos_comex')
        with patch.dict(os.environ,e,clear=True),patch.object(services.Path,'is_file',return_value=True), \
             patch.object(services.Path,'read_text',return_value=json.dumps(context())), \
             patch('socket.gethostbyname',return_value='8.8.8.8'):
            with self.assertRaises(RuntimeError):services.runtime_context()

    def test_cleanup_never_deletes_foreign_container(self):
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory);(state/'postgrest-id').write_text('f'*64)
            with patch.object(services,'state_path',return_value=state),patch.object(services,'load_context',return_value=(state,context())), \
                 patch.object(services,'inspect_owned',return_value=({'Config':{'Labels':{'org.economiacriolla.ec016.run':'foreign'}}},'172.20.0.3')), \
                 patch.object(services,'docker') as docker,patch.dict(os.environ,{'EC016_POSTGREST_IMAGE':'synthetic'}):
                with self.assertRaises(RuntimeError):services.cleanup()
                docker.assert_not_called()

    def test_reports_missing_high_critical_or_stale_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'EC016_SCANNED_'+key+'_ID':'sha256:'+'a'*64 for key in ('RUNNER','POSTGRES','POSTGREST','PYTHON')}):
            root=Path(directory);(root/'cache/db').mkdir(parents=True)
            now=datetime.datetime.now(datetime.timezone.utc).isoformat()
            metadata={'Version':2,'UpdatedAt':now,'DownloadedAt':now}
            (root/'cache/db/metadata.json').write_text(json.dumps(metadata))
            report={'SchemaVersion':2,'Metadata':{'ImageID':'sha256:'+'a'*64},
                    'Results':[{'Packages':[{'Name':'synthetic'}],'Vulnerabilities':[]}]}
            for name in ('postgresql','postgrest','python','runner'):(root/(name+'.json')).write_text(json.dumps(report))
            self.assertEqual(len(plan_b_reports.validate_reports(root)),4)
            for severity in ('HIGH','CRITICAL'):
                bad=dict(report,Results=[{'Packages':[{}],'Vulnerabilities':[{'Severity':severity}]}])
                (root/'postgresql.json').write_text(json.dumps(bad))
                with self.assertRaises(RuntimeError):plan_b_reports.validate_reports(root)
            (root/'postgresql.json').unlink()
            with self.assertRaises(FileNotFoundError):plan_b_reports.validate_reports(root)
            (root/'postgresql.json').write_text(json.dumps(report))
            metadata['UpdatedAt']=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(days=4)).isoformat()
            (root/'cache/db/metadata.json').write_text(json.dumps(metadata))
            with self.assertRaises(RuntimeError):plan_b_reports.validate_reports(root)


if __name__=='__main__':unittest.main()
