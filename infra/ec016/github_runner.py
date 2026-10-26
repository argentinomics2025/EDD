"""Future manual GitHub-hosted lab orchestration. Never runs anything on import.

Only this module may orchestrate starts after hosted-context validation. The local
engine approval stays disabled. This is a workflow boundary, not cryptographic
attestation against a malicious administrator forging a complete runner host.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from . import labctl
from .runner import policy
from .diagnostics import Failure, classify, emit, fail, operation, stage

REPOSITORY='argentinomics2025/EDD'
REF='refs/heads/main'
WORKFLOW=REPOSITORY+'/.github/workflows/ec016_integration.yml@'+REF
SOCKET='unix:///var/run/docker.sock'
ACK='EC016_DISPOSABLE_ONLY'


def validate_host_context(environment=None, event=None):
    e=os.environ if environment is None else environment
    fixed={'GITHUB_ACTIONS':'true','GITHUB_EVENT_NAME':'workflow_dispatch',
           'GITHUB_REPOSITORY':REPOSITORY,'GITHUB_REF':REF,'GITHUB_WORKFLOW_REF':WORKFLOW,
           'RUNNER_ENVIRONMENT':'github-hosted','RUNNER_OS':'Linux','RUNNER_ARCH':'X64',
           'ImageOS':'ubuntu24','EC016_GITHUB_DISPOSABLE':ACK}
    if any(e.get(k)!=v for k,v in fixed.items()):fail('CONTEXT','HOSTED_CONTEXT')
    if any(e.get(k) for k in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH')):
        fail('CONTEXT','ENDPOINT_OVERRIDE')
    if any(k.upper().startswith(('SUPABASE_','PG')) or k.upper() in ('DATABASE_URL','PGRST_DB_URI') for k in e):
        fail('CONTEXT','CONNECTION_OVERRIDE')
    for k in ('GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT'):
        if not re.fullmatch('[1-9][0-9]*',e.get(k,'')):fail('CONTEXT','RUN_IDENTITY')
    if e.get('GITHUB_RUN_ATTEMPT')!='1':fail('CONTEXT','REPLAY_DENIED')
    if not re.fullmatch('[a-f0-9]{40}',e.get('GITHUB_SHA','')):fail('CONTEXT','WORKFLOW_SHA')
    if e.get('GITHUB_WORKSPACE')!='/home/runner/work/EDD/EDD':fail('CONTEXT','WORKSPACE')
    if e.get('RUNNER_TEMP')!='/home/runner/work/_temp':
        fail('CONTEXT','TEMP_STORAGE')
    if event is None:
        event=operation('EVENT_READ',lambda:json.loads(Path(e['GITHUB_EVENT_PATH']).read_text()))
    repo=event.get('repository',{})
    if (repo.get('full_name')!=REPOSITORY or repo.get('private') is not False
            or event.get('inputs',{}).get('lab_sha')!=e.get('EC016_SOURCE_SHA')
            or event.get('inputs',{}).get('confirmation')!=ACK+':'+e.get('EC016_SOURCE_SHA','')):
        fail('CONTEXT','MANUAL_EVENT')
    source=e.get('EC016_SOURCE_SHA','')
    if (not re.fullmatch('[a-f0-9]{40}',source) or source!=e.get('EC016_APPROVED_SHA')
            or e.get('EC016_MANUAL_CONFIRMATION')!=ACK+':'+source):
        fail('CONTEXT','AUTHORIZED_SHA')
    return {'provider':'github-hosted','repository':REPOSITORY,'workflow_ref':WORKFLOW,
            'run_id':e['GITHUB_RUN_ID'],'run_attempt':e['GITHUB_RUN_ATTEMPT'],
            'workspace':e['GITHUB_WORKSPACE'],'workflow_sha':e['GITHUB_SHA'],'source_sha':source}


def validate_context_binding(binding):
    expected=validate_host_context()
    if {k:binding.get(k) for k in expected}!=expected or set(binding)!=set(expected)|{'engine_id'}:
        fail('CONTEXT','CONTEXT_BINDING')
    if not isinstance(binding.get('engine_id'),str) or not re.fullmatch('[A-Za-z0-9:-]{12,128}',binding['engine_id']):
        fail('ENGINE','ENGINE_ID')
    return binding


def runtime_approval(manifest):
    if not isinstance(manifest.get('github_context'),dict):fail('CONTEXT','BINDING_MISSING')
    context=validate_context_binding(manifest['github_context'])
    if manifest.get('engine_id')!=context['engine_id']:fail('ENGINE','ENGINE_BINDING')
    return {'engine_id':context['engine_id'],'nonproduction_reviewed':True,'socket':SOCKET}


def _command(args, timeout=900):
    """No inherited Docker credentials, proxies, SSH agent, endpoint or SQL env."""
    return subprocess.run(args,env={'PATH':'/usr/local/bin:/usr/bin:/bin'},
                          check=True,capture_output=True,text=True,timeout=timeout).stdout


def inspect_fresh_engine(config_dir):
    validate_host_context()  # Must precede EVERY invocation of this bootstrap path.
    prefix=['docker','--host',SOCKET,'--config',str(config_dir)]
    data=json.loads(operation('ENGINE_INFO',_command,prefix+['info','--format','{{json .}}']))
    if data.get('OSType')!='linux' or data.get('Architecture') not in ('x86_64','amd64'):
        fail('ENGINE','ENGINE_PLATFORM')
    for command in (['container','ls','-aq'],['volume','ls','-q'],
                    ['network','ls','-q','--filter','type=custom']):
        if operation('ENGINE_INVENTORY',_command,prefix+command).strip():fail('ENGINE','ENGINE_NOT_EMPTY')
    version=operation('COMPOSE_QUERY',_command,prefix+['compose','version','--short']).strip()
    if not re.fullmatch(r'v?2\.[0-9]+\.[0-9]+(?:[-+].*)?',version):fail('ENGINE','COMPOSE_VERSION')
    binding=validate_host_context();binding['engine_id']=data['ID'];validate_context_binding(binding)
    return binding


def firewall_commands(manifest, network_id):
    policy.validate_manifest(manifest)
    if not re.fullmatch('[a-f0-9]{64}',network_id):raise ValueError('Invalid owned network ID')
    bridge='br-'+network_id[:12]
    chain='EC016_'+manifest['run_id'][:16]
    prefix=['sudo','-n','iptables','-w','10']
    # Chain collision is an error, not a reason to flush an existing chain.
    return [prefix+['-N',chain],
            prefix+['-A',chain,'-s',policy.SUBNET,'-d',policy.SUBNET,'-j','RETURN'],
            prefix+['-A',chain,'-j','DROP'],
            prefix+['-I','DOCKER-USER','1','-i',bridge,'-m','comment','--comment',manifest['project'],'-j',chain],
            prefix+['-I','INPUT','1','-i',bridge,'-m','comment','--comment',manifest['project'],'-j','DROP']]


def configure_network_guard(state, manifest):
    runtime_approval(manifest)
    # No container may be running while firewall and ownership are inspected.
    containers,networks,volumes=labctl.inventory(state,manifest)
    owned=policy.owned_resources(manifest,containers,networks,volumes)
    if any(c.get('State',{}).get('Running') for c in containers):raise RuntimeError('Premature container start')
    if (networks[0].get('Driver')!='bridge' or networks[0].get('EnableIPv6')
            or networks[0].get('Options')):
        raise RuntimeError('Unreviewed bridge implementation or IPv6')
    if not Path('/sys/class/net/br-'+owned['network_id'][:12]).is_dir():
        raise RuntimeError('Owned bridge interface absent')
    if Path('/proc/sys/net/bridge/bridge-nf-call-iptables').read_text().strip()!='1':
        raise RuntimeError('Bridge firewall filtering required')
    for command in firewall_commands(manifest,owned['network_id']):_command(command,30)
    proof={'run_id':manifest['run_id'],'owner_token':manifest['owner_token'],
           'network_id':owned['network_id'],'policy':'bridge-default-deny-v1'}
    path=state/'network-guard.json';path.write_text(json.dumps(proof));path.chmod(0o400)
    for name,content in [('network-guard.json',json.dumps(proof)),
                         ('network-guard.ok',manifest['run_id']+':'+manifest['owner_token']+':bridge-default-deny-v1')]:
        path=state/'metadata'/name;path.write_text(content+'\n');path.chmod(0o444)
    return proof


def require_network_guard(state,manifest):
    runtime_approval(manifest)
    proof=json.loads((state/'network-guard.json').read_text())
    if (proof.get('run_id')!=manifest['run_id'] or proof.get('owner_token')!=manifest['owner_token']
            or proof.get('policy')!='bridge-default-deny-v1'):
        raise RuntimeError('Network guard from another execution')
    resources=json.loads((state/'resources.json').read_text())
    if proof.get('network_id')!=resources['network_id']:raise RuntimeError('Wrong bridge guard')
    # Verify all exact rules still exist immediately before start. No global flush.
    for command in firewall_commands(manifest,resources['network_id']):
        if '-N' in command:continue
        check=list(command)
        for operation in ('-A','-I'):
            if operation in check:
                index=check.index(operation);check[index]='-C'
                if operation=='-I':del check[index+2]  # insertion position is not part of -C
                break
        _command(check,30)


def compose(state, manifest, *args):
    return labctl.docker(state,manifest,['compose','-p',manifest['project'],
                                      '-f',str(state/'compose.json'),*args])


def run_lab(parent):
    with stage('CONTEXT'):
        validate_host_context()
        if operation('CHECKOUT_COMMAND',_command,['git','rev-parse','HEAD']).strip()!=os.environ['EC016_SOURCE_SHA']:
            fail('CONTEXT','CHECKOUT_MISMATCH')
        os_release=operation('HOST_OS_READ',Path('/etc/os-release').read_text)
        if 'ID=ubuntu\n' not in os_release or 'VERSION_ID="24.04"' not in os_release:
            fail('CONTEXT','HOST_OS')
        config=parent/'docker-config'
        operation('STATE_STORAGE',config.mkdir,mode=0o700)
    with stage('ENGINE'):
        binding=inspect_fresh_engine(config)
    with stage('PREFLIGHT'):
        state=labctl.prepare(parent/'runs',execution_context=binding)
        _,manifest,expected=labctl.load(state)
    attested=False
    primary_error=None
    try:
        with stage('PREFLIGHT'):
            labctl.preflight(state)
        with stage('SCAN'):
            refs=policy.verify_images(labctl.ROOT)
            for reference in refs.values():
                operation('IMAGE_PULL',labctl.docker,state,manifest,['pull','--platform','linux/amd64',reference])
            operation('IMAGE_BUILD',compose,state,manifest,'build','ec016-tests')
            from .security_gate import scan_before_bootstrap
            scan_before_bootstrap(state,manifest,expected)
        with stage('PREFLIGHT'):
            operation('COMPOSE_CREATE',compose,state,manifest,'create','--no-build','--pull','never')
        with stage('NETWORK'):
            operation('NETWORK_GUARD',configure_network_guard,state,manifest)
            operation('ATTESTATION',labctl.attest,state);attested=True
            from .security_gate import verify_clearance
            operation('SECURITY_BINDING',verify_clearance,state,manifest)
            operation('NETWORK_GUARD',require_network_guard,state,manifest)
            containers,networks,volumes=labctl.inventory(state,manifest)
            policy.owned_resources(manifest,containers,networks,volumes)
            if any(c.get('State',{}).get('Running') for c in containers):
                fail('NETWORK','SERVICE_INVENTORY')
            by_role={c['Config']['Labels']['com.docker.compose.service']:c['Id'] for c in containers}
        with stage('BOOTSTRAP'):
            labctl.docker(state,manifest,['container','start',by_role['ec016-db']])
            deadline=time.monotonic()+120
            while time.monotonic()<deadline:
                db=json.loads(labctl.docker(state,manifest,['container','inspect',by_role['ec016-db']]))[0]
                if not db['State'].get('Running'):fail('BOOTSTRAP','BOOTSTRAP_STOPPED')
                if db['State'].get('Health',{}).get('Status')=='healthy':break
                time.sleep(1)
            else:fail('BOOTSTRAP','BOOTSTRAP_TIMEOUT')
            labctl.docker(state,manifest,['container','start',by_role['ec016-api']])
        with stage('INTEGRATION'):
            labctl.docker(state,manifest,['container','start',by_role['ec016-tests']])
            deadline=time.monotonic()+360
            while time.monotonic()<deadline:
                test=json.loads(labctl.docker(state,manifest,['container','inspect',by_role['ec016-tests']]))[0]
                if not test['State'].get('Running'):
                    suite_exit=test['State'].get('ExitCode')
                    break
                time.sleep(1)
            else:fail('INTEGRATION','INTEGRATION_TIMEOUT')
            report_text=labctl.docker(state,manifest,['container','logs',by_role['ec016-tests']]).strip()
            report=json.loads(report_text)
            operation('INTEGRATION_REPORT',validate_report_structure,report)
            print(json.dumps(report,sort_keys=True))
            operation('INTEGRATION_REPORT',validate_report,report)
            if suite_exit!=0:fail('INTEGRATION','INTEGRATION_EXIT')
    except Exception as error:
        primary_error=error
        raise
    finally:
        if attested:
            try:
                with stage('CLEANUP'):
                    operation('CLEANUP_FAILED',labctl.cleanup,state,authorized=True)
            except Failure as cleanup_error:
                if primary_error is None:raise
                emit(cleanup_error.stage,cleanup_error.code,'FAILED')
        # Never mask the primary failure with cleanup failure. Partial resources
        # and rules still disappear with the disposable GitHub job VM.


def validate_report_structure(report):
    if not isinstance(report,dict) or set(report)!={'tests_run','failures','errors','skipped','successful'}:
        raise RuntimeError('Unreviewed public report schema')
    if type(report['successful']) is not bool or any(type(report[k]) is not int or not 0<=report[k]<=11
            for k in ('tests_run','failures','errors','skipped')):
        raise RuntimeError('Unsafe public report fields')


def validate_report(report):
    validate_report_structure(report)
    if (report['tests_run']!=11 or report['successful'] is not True
            or report['failures'] or report['errors'] or report['skipped']):
        raise RuntimeError('Missing, incomplete or unsuccessful integration report')


def main():
    try:
        with stage('CONTEXT'):
            validate_host_context()  # Before filesystem state or any daemon contact.
        with tempfile.TemporaryDirectory(prefix='ec016-',dir=os.environ['RUNNER_TEMP']) as directory:
            run_lab(Path(directory))
    except Exception as error:
        failure=classify('CONTEXT',error)
        emit(failure.stage,failure.code,'FAILED',subject=failure.subject,reason=failure.reason)
        print('EC016_FAILED: fixed diagnostics above; raw diagnostics withheld.',flush=True)
        raise SystemExit(1) from None


if __name__=='__main__':main()
