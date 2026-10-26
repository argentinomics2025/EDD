"""SCAN command regression using captured-failure injection, never Docker or SQL."""
import datetime
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from infra.ec016 import diagnostics,github_runner,labctl,security_gate

SENTINEL='SENSITIVE_SYNTHETIC_SENTINEL/private/path?password=not-real'
CODES={'pull':'SCAN_SCANNER_PULL','database':'SCAN_DB_DOWNLOAD','inspect':'SCAN_IMAGE_INSPECT',
       'export':'SCAN_IMAGE_EXPORT','scan':'SCAN_IMAGE_RUN'}


class ScanOperations(unittest.TestCase):
    def setUp(self):
        for target in ('socket.socket.connect','subprocess.run'):
            block=patch(target,side_effect=AssertionError('No services or processes in SCAN unit tests'))
            block.start();self.addCleanup(block.stop)

    def run_gate(self,fail_at=None,stderr=SENTINEL,returncode=1,critical=False):
        output=io.StringIO();calls=[];caught=None
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory);(state/'metadata').mkdir()
            manifest={'scope':'EC016_DISPOSABLE_SYNTHETIC_ONLY','run_id':'a'*32,'owner_token':'b'*64,
                'project':'ec016-'+'a'*32,'network':'ec016-'+'a'*32+'-isolated','host_netns':'net:[123]',
                'engine_id':'synthetic-engine-12345','github_context':{'source_sha':'c'*40}}
            refs=security_gate.policy.verify_images(labctl.ROOT)
            config={'services':{'ec016-db':{'image':refs['postgres']},'ec016-api':{'image':refs['postgrest']},
                               'ec016-tests':{'image':'synthetic-runner:unit'}}}
            latest={}
            def docker(state,run,args):
                calls.append(args)
                if args[0]=='pull':operation='pull'
                elif args[:2]==['image','inspect']:operation='inspect'
                elif args[:2]==['image','save']:operation='export'
                elif '--download-db-only' in args:operation='database'
                else:operation='scan'
                if operation==fail_at:
                    raise subprocess.CalledProcessError(returncode,['synthetic',SENTINEL],
                                                        output=SENTINEL,stderr=stderr)
                if operation=='database':
                    folder=state/'security/cache/db';folder.mkdir()
                    now=datetime.datetime.now(datetime.timezone.utc).isoformat()
                    (folder/'metadata.json').write_text(json.dumps({'Version':2,'UpdatedAt':now,'DownloadedAt':now}))
                if operation=='inspect':
                    latest['id']='sha256:'+hashlib.sha256(args[-1].encode()).hexdigest()
                    return json.dumps([{'Id':latest['id']}])
                if operation=='export':
                    archive=Path(args[args.index('--output')+1]);archive.write_bytes(b'synthetic archive, not executed')
                    latest['report']=archive.parent.parent/'output/report.json'
                if operation=='scan':
                    issues=[{'VulnerabilityID':'CVE-2099-0001','Severity':'CRITICAL'}] if critical else []
                    report={'SchemaVersion':2,'Metadata':{'ImageID':latest['id']},
                            'Results':[{'Packages':[{'Name':'synthetic'}],'Vulnerabilities':issues}]}
                    latest['report'].write_text(json.dumps(report))
                return ''
            with patch.object(github_runner,'runtime_approval'),patch.object(labctl,'docker',side_effect=docker), \
                 patch('sys.stdout',output):
                try:security_gate.scan_before_bootstrap(state,manifest,config)
                except diagnostics.Failure as failure:
                    caught=failure
                    diagnostics.emit(failure.stage,failure.code,'FAILED',subject=failure.subject,reason=failure.reason)
            proof=(state/'metadata/security.ok').exists()
        self.assertNotIn(SENTINEL,output.getvalue())
        return caught,proof,calls,[json.loads(line) for line in output.getvalue().splitlines()]

    def test_every_previously_generic_command_failure_has_exact_operation(self):
        for command,code in CODES.items():
            with self.subTest(command=command):
                failure,proof,calls,records=self.run_gate(command)
                self.assertEqual((failure.stage,failure.code,failure.reason),('SCAN',code,'COMMAND_FAILED'))
                self.assertFalse(proof)
                self.assertEqual(records[-1]['code'],code)
                self.assertEqual(records[-1]['reason'],'COMMAND_FAILED')
                self.assertTrue(any(r.get('code')==code and r.get('status')=='START' for r in records))

    def test_known_cli_permission_registry_and_network_failures_are_safe_labels(self):
        for message,reason in [('permission denied '+SENTINEL,'PERMISSION_DENIED'),
                              ('read-only file system '+SENTINEL,'READ_ONLY_FS'),
                              ('unknown flag '+SENTINEL,'CLI_OPTION'),
                              ('TOOMANYREQUESTS '+SENTINEL,'RATE_LIMIT'),
                              ('unauthorized '+SENTINEL,'REGISTRY_AUTH'),
                              ('no such host '+SENTINEL,'NETWORK'),('x509: '+SENTINEL,'TLS')]:
            with self.subTest(reason=reason):
                failure,proof,_,records=self.run_gate('database',stderr=message)
                self.assertEqual((failure.code,failure.reason),('SCAN_DB_DOWNLOAD',reason))
                self.assertEqual(failure.subject,'VULN_DATABASE');self.assertFalse(proof)
                self.assertEqual(records[-1]['reason'],reason)

    def test_signal_137_is_not_claimed_to_be_oom(self):
        failure,proof,_,_=self.run_gate('scan',returncode=137)
        self.assertEqual(failure.reason,'KILLED_137');self.assertFalse(proof)

    def test_all_five_images_must_be_scanned_before_clearance(self):
        failure,proof,calls,records=self.run_gate()
        self.assertIsNone(failure);self.assertTrue(proof)
        for code in ('SCAN_IMAGE_INSPECT','SCAN_IMAGE_EXPORT','SCAN_IMAGE_RUN','SCAN_REPORT_CHECK'):
            self.assertEqual(sum(r.get('code')==code and r.get('status')=='OK' for r in records),5)
        self.assertEqual(sum('--download-db-only' in c for c in calls),1)
        scans=[c for c in calls if c[0]=='run' and '--download-db-only' not in c]
        self.assertEqual(len(scans),5)
        for args in scans:
            self.assertEqual(args[args.index('--network')+1],'none')
            self.assertIn('--skip-db-update',args);self.assertIn('--offline-scan',args)
            self.assertIn('--read-only',args);self.assertIn('--cap-drop',args)
            self.assertEqual(args[args.index('--user')+1],str(security_gate.os.getuid())+':'+str(security_gate.os.getgid()))
            mounts=[args[i+1] for i,arg in enumerate(args[:-1]) if arg=='--mount']
            self.assertTrue(any('dst=/input/image.tar,readonly' in mount for mount in mounts))
            self.assertFalse(any('docker.sock' in mount for mount in mounts))

    def test_critical_vulnerability_still_blocks_clearance(self):
        failure,proof,_,_=self.run_gate(critical=True)
        self.assertEqual((failure.stage,failure.code),('SCAN','SCAN_REJECTED'))
        self.assertEqual(failure.subject,'POSTGRES');self.assertFalse(proof)

    def test_timeout_keeps_operation_and_does_not_leak_arguments(self):
        output=io.StringIO()
        def timeout():raise subprocess.TimeoutExpired([SENTINEL],10,output=SENTINEL,stderr=SENTINEL)
        with patch('sys.stdout',output),self.assertRaises(diagnostics.Failure) as failure:
            security_gate.scan_operation('SCAN_DB_DOWNLOAD','VULN_DATABASE',timeout)
        self.assertEqual((failure.exception.code,failure.exception.reason),('SCAN_DB_DOWNLOAD','COMMAND_TIMEOUT'))
        self.assertNotIn(SENTINEL,output.getvalue())

    def test_top_level_preserves_scan_operation_subject_and_reason(self):
        output=io.StringIO()
        failure=diagnostics.Failure('SCAN','SCAN_DB_DOWNLOAD',subject='VULN_DATABASE',reason='REGISTRY_AUTH')
        with tempfile.TemporaryDirectory() as directory,patch.dict(security_gate.os.environ,{'RUNNER_TEMP':directory},clear=True), \
             patch.object(github_runner,'validate_host_context',return_value={}), \
             patch.object(github_runner,'run_lab',side_effect=failure),patch('sys.stdout',output):
            with self.assertRaises(SystemExit) as exit:github_runner.legacy_main()
        self.assertEqual(exit.exception.code,1)
        rows=[json.loads(line) for line in output.getvalue().splitlines() if line.startswith('{')]
        self.assertEqual(rows[-1],{'ec016_stage':'SCAN','status':'FAILED','code':'SCAN_DB_DOWNLOAD',
                                  'subject':'VULN_DATABASE','reason':'REGISTRY_AUTH'})

    def test_subject_and_reason_are_whitelisted_before_output(self):
        for kwargs in ({'subject':SENTINEL},{'reason':SENTINEL}):
            with self.assertRaises(ValueError):diagnostics.emit('SCAN','SCAN_IMAGE_RUN','FAILED',**kwargs)

    def test_numeric_uid_can_read_input_and_write_cache_report_without_root_permissions(self):
        # Native filesystem test, not a Docker/user-namespace or real-runner assertion.
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);cache=root/'cache';cache.mkdir(mode=0o700)
            source=root/'archive';source.write_bytes(b'synthetic');source.chmod(0o400)
            self.assertEqual(cache.stat().st_uid,security_gate.os.getuid())
            self.assertEqual(source.read_bytes(),b'synthetic')
            (cache/'report').write_text('{}')
            self.assertEqual((cache/'report').read_text(),'{}')


if __name__=='__main__':unittest.main()
