"""Pure EC016 policy: no Docker, HTTP, SQL or import-time side effects."""
import hashlib
import json
from pathlib import Path
import re

SCOPE='EC016_DISPOSABLE_SYNTHETIC_ONLY'
IPS={'ec016-db':'172.30.216.2','ec016-api':'172.30.216.3','ec016-tests':'172.30.216.4'}
SUBNET='172.30.216.0/24'
LABEL='org.economiacriolla.ec016'


def validate_manifest(m):
    if (m.get('scope')!=SCOPE or not re.fullmatch('[a-f0-9]{32}',m.get('run_id',''))
            or not re.fullmatch('[a-f0-9]{64}',m.get('owner_token',''))
            or m.get('project')!='ec016-'+m['run_id']
            or m.get('network')!=m['project']+'-isolated'
            or not re.fullmatch(r'net:\[\d+\]',m.get('host_netns',''))):
        raise ValueError('Invalid run identity')
    return m


def labels(m):
    validate_manifest(m)
    return {LABEL+'.scope':SCOPE,LABEL+'.run':m['run_id'],LABEL+'.owner':m['owner_token']}


def verify_images(root):
    root=Path(root)
    lock=json.loads((root/'locks/images.json').read_text())
    if lock.get('platform')!='linux/amd64' or set(lock.get('images',{}))!={'postgres','postgrest','python'}:
        raise ValueError('Unexpected image lock')
    refs={}
    for name,entry in lock['images'].items():
        body=(root/'locks'/(name+'-manifest.json')).read_bytes()
        digest='sha256:'+hashlib.sha256(body).hexdigest()
        expected='docker.io/'+entry['repository']+':'+entry['tag']+'@'+digest
        if (entry.get('digest')!=digest or entry.get('reference')!=expected
                or entry.get('status')!='manifest_digest_verified' or not entry.get('verified_at')
                or entry.get('manifest_url')!='https://registry-1.docker.io/v2/'+entry['repository']+'/manifests/'+entry['tag']):
            raise ValueError('Image verification evidence inconsistent')
        if not any(x.get('platform',{}).get('os')=='linux' and x.get('platform',{}).get('architecture')=='amd64'
                   for x in json.loads(body).get('manifests',[])):
            raise ValueError('Required platform not in verified manifest')
        refs[name]=expected
    return refs


def verify_dependencies(root):
    root=Path(root);meta=json.loads((root/'locks/dependencies.json').read_text())
    data=(root/'requirements.lock').read_bytes()
    if (meta.get('target')!='cpython-3.12-linux-amd64' or meta.get('status')!='resolved_not_installed'
            or meta.get('sha256')!=hashlib.sha256(data).hexdigest()
            or meta.get('input_sha256')!=hashlib.sha256((root/'requirements.txt').read_bytes()).hexdigest()):
        raise ValueError('Dependency lock missing or changed')
    joined=data.decode().replace('\\\n',' ')
    packages=[line.strip() for line in joined.splitlines() if line.strip() and not line.lstrip().startswith('#')]
    if not packages or any(not re.match(r'^[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_,.-]+\])?==[^\s]+\s+--hash=sha256:[a-f0-9]{64}',line) for line in packages):
        raise ValueError('Every dependency must be version and hash locked')
    return meta


def make_config(root, metadata_dir, manifest):
    import copy
    root=Path(root).resolve();metadata_dir=Path(metadata_dir).resolve();validate_manifest(manifest)
    refs=verify_images(root);verify_dependencies(root)
    config=json.loads((root/'compose.template.json').read_text())
    config['name']=manifest['project']
    github=manifest.get('github_context') is not None
    network=config['networks']['isolated'];network['name']=manifest['network'];network['labels']=labels(manifest)
    for name,s in config['services'].items():
        if github:
            s['dns']=['127.0.0.1']  # No external DNS forwarding from the lab.
            s['sysctls']={'net.ipv6.conf.all.disable_ipv6':'1','net.ipv6.conf.default.disable_ipv6':'1'}
        s['hostname']=manifest['project']+'-'+name
        s['labels']=labels(manifest);s['labels'][LABEL+'.service']=name
        s['environment']['EC016_RUN_ID']=manifest['run_id']
        s['environment']['EC016_CONTAINER_ROLE']=name
        s.setdefault('volumes',[]).append({'type':'bind','source':str(metadata_dir),'target':'/run/ec016',
                                        'read_only':True,'bind':{'create_host_path':False}})
        for volume in s['volumes']:
            if volume['source'].startswith('./'):volume['source']=str(root/volume['source'][2:])
    config['services']['ec016-db']['image']=refs['postgres']
    config['services']['ec016-api']['image']=refs['postgrest']
    if github:
        config['services']['ec016-api']['environment']['PGRST_DB_URI']=('postgres://ec016_authenticator:'
            'EC016_SYNTHETIC_AUTH_ONLY@172.30.216.2:5432/ec016_disposable')
        config['services']['ec016-tests']['command']=['python','-m','infra.ec016.runner.safe_report']
    s=config['services']['ec016-tests'];s['image']='ec016-runner:'+manifest['run_id']
    s['build']={'context':str(root),'dockerfile':'Dockerfile','args':{'PYTHON_IMAGE':refs['python']}}
    return copy.deepcopy(config)


def canonical_service(service):
    """Only documented, semantics-preserving Compose representations."""
    import copy
    value=copy.deepcopy(service)
    # Compose renders image-inherited defaults as explicit null (not [] or '').
    for key in ('command','entrypoint'):
        if key in value and value[key] is None:value.pop(key)
    # Compose's normalized bind object omits the false boolean. Preserve every
    # other option and reject true; do not equate a missing bind object with {}.
    for mount in value.get('volumes',[]):
        if mount.get('type')=='bind' and isinstance(mount.get('bind'),dict):
            mount['bind'].setdefault('create_host_path',False)
    dependencies=value.get('depends_on',{})
    if isinstance(dependencies,list):
        dependencies={name:{'condition':'service_started'} for name in dependencies}
    for dependency in dependencies.values():
        if dependency.get('required') is True:dependency.pop('required')
        if dependency.get('restart') is False:dependency.pop('restart')
    if 'depends_on' in value:value['depends_on']=dependencies
    memory=value.get('mem_limit')
    if isinstance(memory,str) and re.fullmatch(r'[0-9]+m',memory):
        value['mem_limit']=int(memory[:-1])*1024*1024
    elif isinstance(memory,str) and re.fullmatch(r'[0-9]+',memory):
        # Compose JSON emits byte counts as decimal strings, not JSON numbers.
        value['mem_limit']=int(memory)
    return value


def validate_effective(actual, expected):
    """Accept only reviewed Compose normalization; unfamiliar expansion fails closed."""
    if actual.get('name')!=expected['name'] or set(actual.get('services',{}))!=set(IPS):
        raise ValueError('Unexpected project or services')
    if actual.get('volumes') or actual.get('secrets') or actual.get('configs'):
        raise ValueError('External data or secret resources are forbidden')
    if set(actual.get('networks',{}))!={'isolated'}:
        raise ValueError('Additional networks forbidden')
    net=actual['networks']['isolated'];wanted=expected['networks']['isolated']
    for key in ('name','internal','labels'):
        if net.get(key)!=wanted[key]:raise ValueError('Network policy mismatch')
    if (net.get('external') or net.get('driver')!='bridge' or net.get('driver_opts') or net.get('enable_ipv6')
            or net.get('attachable') or net.get('ipam')!=wanted['ipam']):
        raise ValueError('Unexpected network/IPAM')
    for name,wanted in expected['services'].items():
        service=canonical_service(actual['services'][name]);wanted=canonical_service(wanted)
        if set(service)-set(wanted):raise ValueError('Unreviewed effective service option')
        forbidden={'ports','env_file','network_mode','privileged','devices','volumes_from','extra_hosts',
                   'dns_search','external_links','links','pid','ipc','cgroup','cap_add','develop'}
        if forbidden & set(service):raise ValueError('Unsafe Compose option')
        if service.get('dns')!=wanted.get('dns') or (service.get('dns') is not None and service['dns']!=['127.0.0.1']):
            raise ValueError('Unapproved DNS destination')
        for key in ('image','platform','hostname','environment','labels','read_only','user','entrypoint','command','sysctls'):
            if service.get(key)!=wanted.get(key):raise ValueError('Service identity/environment/entrypoint changed')
        if service.get('cap_drop',[])!=wanted.get('cap_drop',[]) or service.get('security_opt',[])!=wanted.get('security_opt',[]):
            raise ValueError('Capabilities changed')
        if set(service.get('networks',{}))!={'isolated'} or service['networks']['isolated'].get('ipv4_address')!=IPS[name]:
            raise ValueError('Wrong service network or IP')
        if service.get('tmpfs',[])!=wanted.get('tmpfs',[]):raise ValueError('Wrong disposable storage')
        if service.get('volumes',[])!=wanted.get('volumes',[]):raise ValueError('Unapproved mount or writable bind')
        for key in ('healthcheck','depends_on','mem_limit'):
            if service.get(key)!=wanted.get(key):raise ValueError('Effective service behavior changed')
        if name=='ec016-tests' and service.get('build')!=wanted['build']:raise ValueError('Unapproved build context or base')
    return True


def validate_marker_payload(payload, manifest):
    if manifest.get('mode')=='GITHUB_SERVICES_SYNTHETIC_ONLY':
        from ..services import validate_context
        validate_context(manifest)
    else:validate_manifest(manifest)
    if payload!={'scope':SCOPE,'run_id':manifest['run_id'],'owner_token':manifest['owner_token']}:
        raise RuntimeError('Marker belongs to a different run')


def owned_resources(manifest, containers, networks, volumes):
    """All-or-nothing cleanup authorization. Never authorizes deleting volumes."""
    validate_manifest(manifest)
    if volumes:raise ValueError('Any volume prevents cleanup; manual investigation required')
    expected_labels=labels(manifest);services=set()
    if len(containers)!=3 or len(networks)!=1:raise ValueError('Unexpected resource inventory; no cleanup')
    ids=[]
    for c in containers:
        tags=c.get('Config',{}).get('Labels') or {}
        if (any(tags.get(k)!=v for k,v in expected_labels.items())
                or tags.get('com.docker.compose.project')!=manifest['project']
                or tags.get('com.docker.compose.service') not in IPS
                or tags.get(LABEL+'.service')!=tags.get('com.docker.compose.service')):
            raise ValueError('Container ownership mismatch')
        service=tags['com.docker.compose.service']
        if service in services:raise ValueError('Duplicate service resource')
        services.add(service)
        if not re.fullmatch('[a-f0-9]{64}',c.get('Id','')):raise ValueError('Invalid immutable container ID')
        ids.append(c['Id'])
    if len(set(ids))!=3:raise ValueError('Repeated immutable container ID')
    network=networks[0];tags=network.get('Labels') or {}
    if (network.get('Name')!=manifest['network'] or not network.get('Internal')
            or any(tags.get(k)!=v for k,v in expected_labels.items())
            or tags.get('com.docker.compose.project')!=manifest['project']
            or network.get('IPAM',{}).get('Config')!=[{'Subnet':SUBNET,'Gateway':'172.30.216.1'}]):
        raise ValueError('Network ownership/topology mismatch')
    if not re.fullmatch('[a-f0-9]{64}',network.get('Id','')):raise ValueError('Invalid immutable network ID')
    if set((network.get('Containers') or {}).keys())-set(ids):raise ValueError('Foreign network member; no cleanup')
    return {'container_ids':ids,'network_id':network['Id'],'volume_ids':[]}


def require_error_code(error, expected, category=None):
    """A network exception or unrelated SQL error cannot satisfy a negative test."""
    actual=getattr(error,'code',None)
    if actual!=expected:
        raise AssertionError('Expected PostgreSQL error '+expected+', received '+repr(actual))
    fragments={'rls':'row-level security policy','permission':'permission denied'}
    if category is not None:
        if category not in fragments or fragments[category] not in str(getattr(error,'message','')).lower():
            raise AssertionError('Expected error category '+str(category))
