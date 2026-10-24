"""GitHub adaptation unit checks: no Docker, SQL, network or firewall commands."""
import ast
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import re
from infra.ec016 import github_runner as hosted,labctl
from infra.ec016.runner import policy,safe_report

ROOT=Path(__file__).resolve().parents[1]


def environment():
    return {'GITHUB_ACTIONS':'true','GITHUB_EVENT_NAME':'workflow_dispatch',
            'GITHUB_REPOSITORY':hosted.REPOSITORY,'GITHUB_REF':hosted.REF,
            'GITHUB_WORKFLOW_REF':hosted.WORKFLOW,'RUNNER_ENVIRONMENT':'github-hosted',
            'RUNNER_OS':'Linux','RUNNER_ARCH':'X64','ImageOS':'ubuntu24',
            'EC016_GITHUB_DISPOSABLE':hosted.ACK,'EC016_SOURCE_SHA':'e'*40,'EC016_APPROVED_SHA':'e'*40,
            'EC016_MANUAL_CONFIRMATION':hosted.ACK+':'+'e'*40,'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1',
            'GITHUB_SHA':'d'*40,'GITHUB_WORKSPACE':'/home/runner/work/EDD/EDD','RUNNER_TEMP':'/home/runner/work/_temp'}


def event():
    return {'repository':{'full_name':hosted.REPOSITORY,'private':False},
            'inputs':{'lab_sha':'e'*40,'confirmation':hosted.ACK+':'+'e'*40}}


def binding():
    value=hosted.validate_host_context(environment(),event());value['engine_id']='synthetic-engine-12345'
    return value


class GithubPreparation(unittest.TestCase):
    def setUp(self):
        for name in ('socket.socket.connect','subprocess.run'):
            block=patch(name,side_effect=AssertionError('External operations forbidden in unit checks'))
            block.start();self.addCleanup(block.stop)

    def test_manual_only_workflow(self):
        # Dependency-free static checks; full YAML parsing is a separate local check.
        text=(ROOT/'.github/workflows/ec016_integration.yml').read_text()
        triggers=text.split('\non:\n',1)[1].split('\npermissions:',1)[0]
        self.assertEqual(re.findall(r'^  ([a-z_]+):',triggers,re.M),['workflow_dispatch'])
        self.assertIn('lab_sha:',triggers);self.assertIn('confirmation:',triggers)
        self.assertNotIn('default:',triggers)
        permissions=text.split('\npermissions:\n',1)[1].split('\nconcurrency:',1)[0]
        self.assertEqual(permissions.strip(),'contents: read')
        self.assertIn('cancel-in-progress: false',text)
        jobs=text.split('\njobs:\n',1)[1]
        self.assertEqual(re.findall(r'^  ([a-z-]+):',jobs,re.M),['disposable-integration'])
        self.assertEqual(re.findall(r'runs-on: ([^\n]+)',jobs),['ubuntu-24.04'])
        self.assertIn('timeout-minutes: 40',jobs)
        self.assertNotRegex(jobs,r'(?m)^    (services|environment):')
        for expression in ("github.event_name == 'workflow_dispatch'",'github.event.repository.private == false',
                           "github.ref == 'refs/heads/main'"):
            self.assertIn(expression,jobs)
        for forbidden in ('secrets.','self-hosted','ubuntu-slim','upload-artifact','actions/cache','pull_request','schedule:','push:'):
            self.assertNotIn(forbidden,text)
        self.assertIn('persist-credentials: false',text)
        actions=re.findall(r'uses: ([^\s]+)',text)
        self.assertEqual(len(actions),1)
        for action in actions:self.assertRegex(action,r'@[a-f0-9]{40}$')

    def test_hosted_context_accepted(self):
        self.assertEqual(hosted.validate_host_context(environment(),event())['provider'],'github-hosted')

    def test_every_hosted_claim_is_mandatory(self):
        for key in environment():
            wrong=environment();wrong[key]='wrong'
            with self.subTest(key=key),self.assertRaises(RuntimeError):hosted.validate_host_context(wrong,event())

    def test_no_prod_or_endpoint_environment(self):
        for key in ('SUPABASE_URL','SUPABASE_SERVICE_ROLE_KEY','DATABASE_URL','PGHOST','PGRST_DB_URI','DOCKER_HOST','DOCKER_CONTEXT'):
            wrong=environment();wrong[key]='synthetic-forbidden'
            with self.subTest(key=key),self.assertRaises(RuntimeError):hosted.validate_host_context(wrong,event())

    def test_private_repo_or_missing_ack_rejected(self):
        for change in ('private','repo','ack'):
            wrong=event()
            if change=='private':wrong['repository']['private']=True
            if change=='repo':wrong['repository']['full_name']='other/repository'
            if change=='ack':wrong['inputs']['confirmation']='NO'
            with self.assertRaises(RuntimeError):hosted.validate_host_context(environment(),wrong)

    def test_main_locally_fails_before_any_docker(self):
        output=io.StringIO()
        with patch.dict('os.environ',{},clear=True),patch('sys.stdout',output),self.assertRaises(SystemExit) as error:
            hosted.main()
        self.assertEqual(error.exception.code,1)
        self.assertIn('EC016_FAILED',output.getvalue())

    def test_per_job_approval_does_not_change_local_approval(self):
        raw=(labctl.ROOT/'engine-approval.json').read_bytes()
        b=binding()
        with tempfile.TemporaryDirectory() as directory,patch.object(hosted,'validate_host_context',return_value={k:v for k,v in b.items() if k!='engine_id'}):
            state=labctl.prepare(directory,execution_context=b)
            _,m,config=labctl.load(state)
            self.assertEqual(hosted.runtime_approval(m)['engine_id'],b['engine_id'])
            self.assertEqual(m['github_context']['run_id'],'123')
            self.assertTrue(policy.validate_effective(config,config))
        self.assertEqual((labctl.ROOT/'engine-approval.json').read_bytes(),raw)
        self.assertFalse(json.loads(raw)['nonproduction_reviewed'])

    def test_cross_job_or_engine_rejected(self):
        b=binding();expected={k:v for k,v in b.items() if k!='engine_id'}
        with patch.object(hosted,'validate_host_context',return_value=expected):
            for key in ('run_id','run_attempt','repository','workflow_ref'):
                wrong=dict(b);wrong[key]='different'
                with self.assertRaises(RuntimeError):hosted.validate_context_binding(wrong)
            with self.assertRaises(RuntimeError):hosted.runtime_approval({'github_context':b,'engine_id':'different'})

    def test_github_config_reuses_locks_and_disables_dns_forwarding(self):
        b=binding()
        with tempfile.TemporaryDirectory() as directory,patch.object(hosted,'validate_context_binding'):
            state=labctl.prepare(directory,execution_context=b);_,m,config=labctl.load(state)
            for role,service in config['services'].items():
                self.assertEqual(service['dns'],['127.0.0.1'])
                self.assertNotIn('ports',service)
                self.assertEqual(service['environment']['EC016_RUN_ID'],m['run_id'])
            self.assertIn('@172.30.216.2:',config['services']['ec016-api']['environment']['PGRST_DB_URI'])
            self.assertEqual(config['services']['ec016-tests']['command'][-1],'infra.ec016.runner.safe_report')
            unsafe=copy.deepcopy(config);unsafe['services']['ec016-tests']['dns']=['8.8.8.8']
            with self.assertRaises(ValueError):policy.validate_effective(unsafe,config)

    def test_fresh_engine_inspection_is_read_only(self):
        context=hosted.validate_host_context(environment(),event())
        info=json.dumps({'ID':'synthetic-engine-12345','OSType':'linux','Architecture':'x86_64'})
        with patch.object(hosted,'validate_host_context',return_value=context),patch.object(hosted,'_command',side_effect=[info,'','','','2.40.3']) as command:
            b=hosted.inspect_fresh_engine(Path('/tmp/synthetic-docker-config'))
        self.assertEqual(b['engine_id'],'synthetic-engine-12345')
        for invocation in command.call_args_list:
            args=invocation.args[0]
            for unsafe in ('start','run','rm','create','build','pull','prune'):
                self.assertNotIn(unsafe,args)

    def test_existing_resources_abort_without_cleanup(self):
        context=hosted.validate_host_context(environment(),event())
        info=json.dumps({'ID':'synthetic-engine-12345','OSType':'linux','Architecture':'x86_64'})
        with patch.object(hosted,'validate_host_context',return_value=context),patch.object(hosted,'_command',side_effect=[info,'foreign-id']) as command:
            with self.assertRaisesRegex(RuntimeError,'Fresh job daemon'):
                hosted.inspect_fresh_engine(Path('/tmp/synthetic-docker-config'))
        self.assertEqual(command.call_count,2)

    def test_subprocess_does_not_inherit_tokens_or_proxies(self):
        with patch('subprocess.run') as run:
            run.return_value.stdout='synthetic-output'
            with patch.dict('os.environ',{'GITHUB_TOKEN':'synthetic','HTTPS_PROXY':'synthetic','DOCKER_HOST':'synthetic'},clear=True):
                self.assertEqual(hosted._command(['synthetic-program']),'synthetic-output')
        options=run.call_args.kwargs
        self.assertEqual(set(options['env']),{'PATH'})
        self.assertTrue(options['capture_output']);self.assertTrue(options['check'])
        self.assertNotIn('shell',options)

    def test_firewall_plan_is_scoped_and_default_deny(self):
        m={'scope':policy.SCOPE,'run_id':'a'*32,'owner_token':'b'*64,
           'project':'ec016-'+'a'*32,'network':'ec016-'+'a'*32+'-isolated','host_netns':'net:[123]'}
        commands=hosted.firewall_commands(m,'c'*64)
        self.assertEqual(len(commands),5)
        text=json.dumps(commands)
        self.assertIn('br-'+'c'*12,text);self.assertIn('DROP',text);self.assertIn('DOCKER-USER',text)
        self.assertIn('INPUT',text)
        for bad in ('-F','-X','--flush','--policy'):
            self.assertFalse(any(bad in command for command in commands))
        self.assertNotIn('OUTPUT',text)  # Cannot block the GitHub agent globally.
        with self.assertRaises(ValueError):hosted.firewall_commands(m,'foreign-network-name')

    def test_network_guard_requires_run_and_network(self):
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory)
            (state/'network-guard.json').write_text(json.dumps({'run_id':'foreign','owner_token':'wrong','policy':'bridge-default-deny-v1'}))
            with patch.object(hosted,'runtime_approval'),self.assertRaises(RuntimeError):
                hosted.require_network_guard(state,{'run_id':'expected','owner_token':'expected'})

    def test_raw_failure_messages_are_not_in_report(self):
        class SyntheticFailure(unittest.TestCase):
            def runTest(self):raise AssertionError('SENSITIVE_SYNTHETIC_SENTINEL')
        output=io.StringIO()
        with patch('sys.stdout',output):report=safe_report.run_suite(unittest.TestSuite([SyntheticFailure()]))
        self.assertEqual(report['failures'],1);self.assertFalse(report['successful'])
        self.assertNotIn('SENSITIVE_SYNTHETIC_SENTINEL',json.dumps(report)+output.getvalue())

    def test_report_fields_cannot_exfiltrate_strings(self):
        report={'tests_run':11,'failures':0,'errors':0,'skipped':0,'successful':True}
        for key in report:
            bad=dict(report);bad[key]='SENSITIVE_SYNTHETIC_SENTINEL'
            with self.assertRaises(RuntimeError):hosted.validate_report_structure(bad)

    def test_hosted_binding_cannot_enable_current_local_daemon(self):
        m={'engine_id':binding()['engine_id'],'github_context':binding()}
        with patch.dict('os.environ',{},clear=True),self.assertRaises(RuntimeError):hosted.runtime_approval(m)

    def test_incomplete_or_failed_integration_never_passes(self):
        ok={'tests_run':11,'failures':0,'errors':0,'skipped':0,'successful':True}
        hosted.validate_report(ok)
        for key,value in [('tests_run',10),('failures',1),('errors',1),('skipped',1),('successful',False)]:
            wrong=dict(ok);wrong[key]=value
            with self.assertRaises(RuntimeError):hosted.validate_report(wrong)

    def test_harness_never_imports_publication_code(self):
        for file in ('github_runner.py','runner/integration_suite.py','runner/safe_report.py'):
            tree=ast.parse((labctl.ROOT/file).read_text())
            modules=[n.module or '' for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
            self.assertFalse(any(module.startswith('scripts') for module in modules))
        text=(labctl.ROOT/'github_runner.py').read_text()
        for forbidden in ('system prune','volume rm','--remove-orphans','docker.sock:/','--privileged'):
            self.assertNotIn(forbidden,text)


if __name__=='__main__':unittest.main()
