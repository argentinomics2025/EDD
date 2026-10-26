"""Plan B: native Actions PostgreSQL, then one PostgREST container, then tests.

Host commands require the authorized GitHub context. Never used against a DSN
provided by a caller. SQL runs only via exec into GitHub's own service ID.
"""
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import uuid
from .runner import policy

ROOT=Path(__file__).resolve().parent
SCHEMA_MARKER='-- EC016_SHARED_FIXTURE_BODY\n'
MODE='GITHUB_SERVICES_SYNTHETIC_ONLY'


def validate_context(data):
    if (data.get('mode')!=MODE or data.get('scope')!=policy.SCOPE
            or not re.fullmatch('[a-f0-9]{32}',data.get('run_id',''))
            or not re.fullmatch('[a-f0-9]{64}',data.get('owner_token',''))
            or not re.fullmatch('[a-f0-9]{40}',data.get('source_sha',''))
            or not re.fullmatch('[a-f0-9]{64}',data.get('postgres_id',''))
            or not re.fullmatch(r'(?:github_network_[a-f0-9]+|[a-f0-9]{64})',data.get('docker_network',''))):
        raise RuntimeError('Invalid native-service context')
    ip=ipaddress.ip_address(data['postgres_ip'])
    if not ip.is_private or ip.is_loopback or ip.is_unspecified:raise RuntimeError('Nonprivate service')
    if 'postgrest_ip' in data:
        addr=ipaddress.ip_address(data['postgrest_ip'])
        if (not addr.is_private or addr.is_loopback or addr.is_unspecified
                or not re.fullmatch('[a-f0-9]{64}',data.get('postgrest_id',''))):
            raise RuntimeError('Invalid private PostgREST service')
    return data


def host_context():
    from .github_runner import validate_host_context, WORKFLOW, FUNCTIONAL_WORKFLOW
    workflow=os.environ.get('GITHUB_WORKFLOW_REF')
    if workflow==FUNCTIONAL_WORKFLOW:
        # Explicit risk acceptance is limited to this functional workflow/run/SHA.
        event=json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
        acknowledgement='EC016_FUNCTIONAL_ONLY_ACCEPT_IMAGE_RISK'
        if (os.environ.get('EC016_FUNCTIONAL_RISK')!=acknowledgement
                or event.get('inputs',{}).get('image_risk')!=acknowledgement):
            raise RuntimeError('Image risk not accepted')
        result=validate_host_context(workflow=FUNCTIONAL_WORKFLOW)
    else:
        result=validate_host_context(workflow=WORKFLOW)
    expected=policy.verify_images(ROOT)
    for key,name in [('EC016_POSTGRES_IMAGE','postgres'),('EC016_POSTGREST_IMAGE','postgrest'),('EC016_PYTHON_IMAGE','python')]:
        if os.environ.get(key)!=expected[name]:raise RuntimeError('Workflow image differs from reviewed lock')
    head=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,env={'PATH':'/usr/local/bin:/usr/bin:/bin'},
                        capture_output=True,text=True,check=True,timeout=10).stdout.strip()
    if head!=result['source_sha']:raise RuntimeError('Checkout differs from approved source')
    return result


def state_path():
    host_context()
    return Path(os.environ['RUNNER_TEMP'])/'ec016-native-services'


def docker(args, input=None):
    host_context()
    # No registry credentials, proxies, agents or arbitrary endpoint inheritance.
    return subprocess.run(['docker','--host','unix:///var/run/docker.sock',*args],
        input=input,env={'PATH':'/usr/local/bin:/usr/bin:/bin','DOCKER_CONFIG':str(Path(os.environ['RUNNER_TEMP'])/'ec016-empty-docker')},
        capture_output=True,text=True,check=True,timeout=600).stdout


def inspect_owned(container_id,network,image):
    if not re.fullmatch('[a-f0-9]{64}',container_id):raise RuntimeError('Invalid service ID')
    if not re.fullmatch(r'(?:github_network_[a-f0-9]+|[a-f0-9]{64})',network):raise RuntimeError('Invalid job network')
    item=json.loads(docker(['inspect',container_id]))[0]
    expected_id=json.loads(docker(['image','inspect',image]))[0]['Id']
    networks=item['NetworkSettings']['Networks']
    matches=[n for name,n in networks.items() if name==network or n.get('NetworkID')==network]
    if (item['Image']!=expected_id or not re.fullmatch('sha256:[a-f0-9]{64}',expected_id)
            or len(networks)!=1 or len(matches)!=1):
        raise RuntimeError('Wrong service image/network')
    ip=matches[0]['IPAddress']
    addr=ipaddress.ip_address(ip)
    if not addr.is_private or addr.is_loopback or addr.is_unspecified:raise RuntimeError('Nonprivate service')
    return item,ip


def bootstrap_sql(context):
    validate_context(context)
    source=(ROOT/'schema.sql').read_text()
    if source.count(SCHEMA_MARKER)!=1:raise RuntimeError('Ambiguous shared fixture')
    body=source.partition(SCHEMA_MARKER)[2]
    # All original table/UNIQUE/CHECK/RLS/trigger definitions are reused verbatim.
    return ("\\set ON_ERROR_STOP on\nDO $$ BEGIN\n"
        "IF current_database()<>'ec016_disposable' OR current_user<>'ec016_admin' "
        "OR to_regnamespace('api') IS NOT NULL "
        "OR current_setting('ec016.run_id',true) IS DISTINCT FROM '"+context['run_id']+"' "
        "OR current_setting('ec016.owner_token',true) IS DISTINCT FROM '"+context['owner_token']+"' "
        "THEN RAISE EXCEPTION 'Invalid disposable bootstrap'; END IF; END $$;\n"+body)


def save_context(state,context):
    path=state/'context.tmp';path.write_text(json.dumps(context));path.chmod(0o444)
    path.replace(state/'context.json')


def bootstrap():
    binding=host_context();state=state_path();state.mkdir(mode=0o755,exist_ok=False)
    pg=os.environ['EC016_POSTGRES_ID'];network=os.environ['EC016_NETWORK']
    item,ip=inspect_owned(pg,network,os.environ['EC016_POSTGRES_IMAGE'])
    env=dict(v.split('=',1) for v in item['Config']['Env'] if '=' in v)
    if any(env.get(k)!=v for k,v in {'POSTGRES_USER':'ec016_admin','POSTGRES_DB':'ec016_disposable',
                                   'POSTGRES_PASSWORD':'EC016_SYNTHETIC_ADMIN_ONLY'}.items()):
        raise RuntimeError('Wrong synthetic PostgreSQL')
    context={'mode':MODE,'scope':policy.SCOPE,'run_id':uuid.uuid4().hex,'owner_token':secrets.token_hex(32),
             'source_sha':binding['source_sha'],'workflow_run':binding['run_id'],
             'postgres_id':pg,'postgres_ip':ip,'docker_network':network}
    validate_context(context)
    # The actual selected service, not DNS or an environment DSN, receives bootstrap.
    docker(['exec','-i','--env','PGOPTIONS=-c ec016.run_id='+context['run_id']+' -c ec016.owner_token='+context['owner_token'],
            pg,'psql','--no-psqlrc','--host=/var/run/postgresql','--port=5432',
            '--username=ec016_admin','--dbname=ec016_disposable','--set=ON_ERROR_STOP=1'],input=bootstrap_sql(context))
    save_context(state,context)
    print('EC016_SERVICES_BOOTSTRAP_OK')


def load_context():
    state=state_path();context=validate_context(json.loads((state/'context.json').read_text()))
    binding=host_context()
    if context['source_sha']!=binding['source_sha'] or context['workflow_run']!=binding['run_id']:
        raise RuntimeError('Cross-job service context')
    return state,context


def start_postgrest():
    state,context=load_context()
    args=['run','--detach','--network',context['docker_network'],'--network-alias','postgrest',
          '--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--memory','256m',
          '--label','org.economiacriolla.ec016.run='+context['run_id'],
          '--env','PGRST_DB_URI=postgres://ec016_authenticator:EC016_SYNTHETIC_AUTH_ONLY@postgres:5432/ec016_disposable',
          '--env','PGRST_DB_SCHEMAS=api','--env','PGRST_DB_ANON_ROLE=ec016_reader',
          '--env','PGRST_JWT_SECRET=EC016_PUBLIC_SYNTHETIC_JWT_KEY_NOT_A_REAL_SECRET_0123456789',
          os.environ['EC016_POSTGREST_IMAGE']]
    container_id=docker(args).strip()
    if not re.fullmatch('[a-f0-9]{64}',container_id):raise RuntimeError('No owned PostgREST ID')
    (state/'postgrest-id').write_text(container_id)
    _,ip=inspect_owned(container_id,context['docker_network'],os.environ['EC016_POSTGREST_IMAGE'])
    context.update({'postgrest_id':container_id,'postgrest_ip':ip})
    save_context(state,context)
    print('EC016_SERVICES_POSTGREST_OK')


def test_container():
    state,context=load_context()
    inspect_owned(context['postgres_id'],context['docker_network'],os.environ['EC016_POSTGRES_IMAGE'])
    inspect_owned(context['postgrest_id'],context['docker_network'],os.environ['EC016_POSTGREST_IMAGE'])
    args=['run','--rm','--network',context['docker_network'],'--read-only','--cap-drop','ALL',
          '--security-opt','no-new-privileges:true','--user','10001:10001',
          '--tmpfs','/tmp:rw,nosuid,nodev,size=512m,mode=1777','--memory','768m',
          '--mount','type=bind,src='+str(ROOT)+',dst=/lab/infra/ec016,readonly',
          '--mount','type=bind,src='+str(state)+',dst=/run/ec016,readonly',
          '--workdir','/lab','--env','PYTHONDONTWRITEBYTECODE=1','--env','PYTHONPATH=/tmp/deps:/lab',
          '--env','EC016_ACTIONS_SERVICES='+MODE,'--env','EC016_EXECUTE_DISPOSABLE=YES_SYNTHETIC_ONLY',
          '--env','EC016_SOURCE_SHA='+context['source_sha'],'--env','EC016_WORKFLOW_RUN='+context['workflow_run'],
          os.environ['EC016_PYTHON_IMAGE'],'sh','-ec',
          'python -m pip install --disable-pip-version-check --no-cache-dir --only-binary=:all: --require-hashes '
          '--target /tmp/deps -r infra/ec016/requirements.lock >/tmp/pip.log 2>&1; '
          'python -m infra.ec016.runner.safe_report']
    command_failed=False
    try:output=docker(args)
    except subprocess.CalledProcessError as error:
        output=error.stdout;command_failed=True
    from .github_runner import validate_report,validate_report_structure
    report=json.loads(output.strip());validate_report_structure(report)
    print(json.dumps(report,sort_keys=True))
    validate_report(report)
    if command_failed:raise RuntimeError('Test container failed')


def cleanup():
    state=state_path();path=state/'postgrest-id'
    if not path.exists():return
    _,context=load_context();container_id=path.read_text().strip()
    item,_=inspect_owned(container_id,context['docker_network'],os.environ['EC016_POSTGREST_IMAGE'])
    if item['Config']['Labels'].get('org.economiacriolla.ec016.run')!=context['run_id']:
        raise RuntimeError('Cleanup ownership mismatch')
    docker(['rm','--force',container_id])
    print('EC016_SERVICES_CLEANUP_OK')


def runtime_context():
    from .runner.lab_guard import assert_opt_in
    assert_opt_in()
    if not Path('/.dockerenv').is_file() or os.environ.get('EC016_ACTIONS_SERVICES')!=MODE:
        raise RuntimeError('Containerized native-service fixture required')
    context=validate_context(json.loads(Path('/run/ec016/context.json').read_text()))
    if (context['source_sha']!=os.environ.get('EC016_SOURCE_SHA')
            or context['workflow_run']!=os.environ.get('EC016_WORKFLOW_RUN')):
        raise RuntimeError('Wrong selected fixture')
    import socket
    for name,key in [('postgres','postgres_ip'),('postgrest','postgrest_ip')]:
        if not context.get(key) or socket.gethostbyname(name)!=context[key]:
            raise RuntimeError('Service DNS differs from native job service')
    return context


def main():
    import sys
    action=sys.argv[1] if len(sys.argv)==2 else ''
    try:
        host_context()
        if action not in ('bootstrap','postgrest','test','cleanup'):raise RuntimeError('Invalid service action')
        {'bootstrap':bootstrap,'postgrest':start_postgrest,'test':test_container,'cleanup':cleanup}[action]()
    except Exception:
        print('EC016_SERVICES_FAILED_'+(action.upper() if action in ('bootstrap','postgrest','test','cleanup') else 'CONTEXT'))
        raise SystemExit(1) from None


if __name__=='__main__':main()
