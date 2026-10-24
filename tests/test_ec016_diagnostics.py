"""Regression for lost EC016_FAILED diagnostics; no assumption about the failed CI cause."""
from contextlib import ExitStack
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from infra.ec016 import github_runner as hosted,diagnostics,labctl,security_gate

SENTINEL='SENSITIVE_SYNTHETIC_SENTINEL/private/path?password=not-real'


def records(output):
    return [json.loads(line) for line in output.splitlines() if line.startswith('{')]


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        for target in ('socket.socket.connect','subprocess.run'):
            mock=patch(target,side_effect=AssertionError('No external operation during diagnostics tests'))
            mock.start();self.addCleanup(mock.stop)

    def invoke(self,runner):
        stream=io.StringIO()
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'RUNNER_TEMP':directory},clear=True), \
             patch.object(hosted,'validate_host_context',return_value={}), \
             patch.object(hosted,'run_lab',side_effect=runner),patch('sys.stdout',stream):
            with self.assertRaises(SystemExit) as failure:hosted.main()
        self.assertEqual(failure.exception.code,1)
        self.assertNotIn(SENTINEL,stream.getvalue())
        return stream.getvalue()

    def test_previously_indistinguishable_failures_now_identify_every_stage(self):
        for name in diagnostics.STAGES:
            def broken(parent):
                with diagnostics.stage(name):raise RuntimeError(SENTINEL)
            with self.subTest(stage=name):
                result=records(self.invoke(broken))
                self.assertEqual(result[-1],{'ec016_stage':name,'status':'FAILED','code':'CHECK_FAILED'})

    def test_subprocess_stdout_stderr_and_arguments_never_leak(self):
        def broken(parent):
            with diagnostics.stage('ENGINE'):
                raise subprocess.CalledProcessError(1,['docker',SENTINEL],output=SENTINEL,stderr=SENTINEL)
        result=records(self.invoke(broken))
        self.assertEqual(result[-1]['code'],'COMMAND_FAILED')
        self.assertEqual(result[-1]['ec016_stage'],'ENGINE')

    def test_timeout_is_distinct_and_safe(self):
        def broken(parent):
            with diagnostics.stage('SCAN'):raise subprocess.TimeoutExpired([SENTINEL],10,output=SENTINEL,stderr=SENTINEL)
        self.assertEqual(records(self.invoke(broken))[-1],{'ec016_stage':'SCAN','status':'FAILED','code':'COMMAND_TIMEOUT'})

    def test_context_rejection_precedes_state_and_docker(self):
        stream=io.StringIO()
        with patch.dict(os.environ,{},clear=True),patch('sys.stdout',stream), \
             patch.object(hosted.tempfile,'TemporaryDirectory') as directory, \
             patch.object(hosted,'_command') as command:
            with self.assertRaises(SystemExit):hosted.main()
        self.assertEqual(records(stream.getvalue())[-1],{'ec016_stage':'CONTEXT','status':'FAILED','code':'HOSTED_CONTEXT'})
        directory.assert_not_called();command.assert_not_called()

    def test_checkout_mismatch_does_not_contact_engine(self):
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'EC016_SOURCE_SHA':'a'*40},clear=True), \
             patch.object(hosted,'validate_host_context',return_value={}), \
             patch.object(hosted,'_command',return_value='b'*40), \
             patch.object(hosted,'inspect_fresh_engine') as inspect,patch('sys.stdout',io.StringIO()):
            with self.assertRaises(diagnostics.Failure) as failure:hosted.run_lab(Path(directory))
        self.assertEqual((failure.exception.stage,failure.exception.code),('CONTEXT','CHECKOUT_MISMATCH'))
        inspect.assert_not_called()

    def test_compose_version_rejection_has_exact_code_without_changing_policy(self):
        info=json.dumps({'ID':'synthetic-engine-12345','OSType':'linux','Architecture':'x86_64'})
        with patch.object(hosted,'validate_host_context',return_value={}), \
             patch.object(hosted,'_command',side_effect=[info,'','','','5.0.0']):
            with self.assertRaises(diagnostics.Failure) as failure:hosted.inspect_fresh_engine(Path('/tmp/synthetic'))
        self.assertEqual((failure.exception.stage,failure.exception.code),('ENGINE','COMPOSE_VERSION'))

    def test_engine_info_failure_is_identified_without_payload(self):
        with patch.object(hosted,'validate_host_context',return_value={}), \
             patch.object(hosted,'_command',side_effect=subprocess.CalledProcessError(1,[SENTINEL],stderr=SENTINEL)), \
             patch('sys.stdout',io.StringIO()),diagnostics.stage('ENGINE'):
            with self.assertRaises(diagnostics.Failure) as failure:hosted.inspect_fresh_engine(Path('/tmp/synthetic'))
        self.assertEqual((failure.exception.stage,failure.exception.code),('ENGINE','ENGINE_INFO'))

    def test_known_policy_failure_gets_fixed_compose_reason(self):
        def broken(parent):
            with diagnostics.stage('PREFLIGHT'):raise ValueError('Unreviewed effective service option')
        self.assertEqual(records(self.invoke(broken))[-1]['code'],'COMPOSE_SERVICE_OPTIONS')

    def test_unrecognized_exception_is_not_used_as_public_code(self):
        for name in ('CONTEXT','ENGINE','PREFLIGHT','SCAN','NETWORK','BOOTSTRAP','INTEGRATION','CLEANUP'):
            failure=diagnostics.classify(name,ValueError(SENTINEL))
            self.assertEqual(failure.code,'CHECK_FAILED')
            self.assertNotIn(SENTINEL,str(failure))
        with self.assertRaises(ValueError):diagnostics.emit('CONTEXT',SENTINEL,'FAILED')

    def test_cleanup_failure_does_not_mask_primary_integration_failure(self):
        output=io.StringIO();manifest={'run_id':'a'*32,'owner_token':'b'*64}
        containers=[{'Id':role,'Config':{'Labels':{'com.docker.compose.service':role}},'State':{'Running':False}}
                    for role in ('ec016-db','ec016-api','ec016-tests')]
        def docker(state,run,args):
            if args[:2]==['container','inspect']:
                if args[2]=='ec016-db':return json.dumps([{'State':{'Running':True,'Health':{'Status':'healthy'}}}])
                return json.dumps([{'State':{'Running':False,'ExitCode':1}}])
            if args[:2]==['container','logs']:
                return json.dumps({'tests_run':11,'failures':1,'errors':0,'skipped':0,'successful':False})
            return ''
        with tempfile.TemporaryDirectory() as directory,ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ,{'EC016_SOURCE_SHA':'e'*40},clear=True))
            stack.enter_context(patch('sys.stdout',output))
            for target,value in ((hosted,'validate_host_context'),(hosted,'configure_network_guard'),
                                  (hosted,'require_network_guard'),(labctl,'preflight'),(labctl,'attest'),
                                  (security_gate,'scan_before_bootstrap'),(security_gate,'verify_clearance'),
                                  (hosted,'compose'),(hosted.policy,'owned_resources')):
                stack.enter_context(patch.object(target,value))
            stack.enter_context(patch.object(hosted,'_command',return_value='e'*40))
            stack.enter_context(patch.object(hosted.Path,'read_text',return_value='ID=ubuntu\nVERSION_ID="24.04"\n'))
            stack.enter_context(patch.object(hosted,'inspect_fresh_engine',return_value={}))
            stack.enter_context(patch.object(labctl,'prepare',return_value=Path(directory)/'state'))
            stack.enter_context(patch.object(labctl,'load',return_value=(Path(directory)/'state',manifest,{})))
            stack.enter_context(patch.object(hosted.policy,'verify_images',return_value={}))
            stack.enter_context(patch.object(labctl,'inventory',return_value=(containers,[],[])))
            stack.enter_context(patch.object(labctl,'docker',side_effect=docker))
            stack.enter_context(patch.object(labctl,'cleanup',side_effect=RuntimeError(SENTINEL)))
            with self.assertRaises(diagnostics.Failure) as failure:hosted.run_lab(Path(directory))
        self.assertEqual((failure.exception.stage,failure.exception.code),('INTEGRATION','INTEGRATION_REPORT'))
        failed=[row for row in records(output.getvalue()) if row.get('status')=='FAILED']
        self.assertEqual(failed,[{'ec016_stage':'CLEANUP','status':'FAILED','code':'CLEANUP_FAILED'}])
        self.assertNotIn(SENTINEL,output.getvalue())


if __name__=='__main__':unittest.main()
