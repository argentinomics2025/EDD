"""EC016 host controller. No start/up command; no Docker calls on import/prepare.

Attestation and cleanup require a separately reviewed local engine approval.
Cleanup removes only re-inspected immutable IDs recorded by this run; never volumes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import uuid
from .runner import policy

ROOT=Path(__file__).resolve().parent


def source_hashes():
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(ROOT.rglob('*')) if p.is_file()
            and '.runtime' not in p.parts and '__pycache__' not in p.parts}


def prepare(parent=None, *, execution_context=None):
    policy.verify_images(ROOT);policy.verify_dependencies(ROOT)
    run_id=uuid.uuid4().hex
    state=Path(parent or ROOT/'.runtime')/run_id
    state.mkdir(parents=True,mode=0o700,exist_ok=False)
    metadata=state/'metadata';metadata.mkdir(mode=0o755)
    approval=json.loads((ROOT/'engine-approval.json').read_text())
    manifest={'scope':policy.SCOPE,'run_id':run_id,'owner_token':secrets.token_hex(32),
              'project':'ec016-'+run_id,'network':'ec016-'+run_id+'-isolated',
              'host_netns':os.readlink('/proc/self/ns/net'),'engine_id':approval['engine_id']}
    if execution_context is not None:
        from .github_runner import validate_context_binding
        validate_context_binding(execution_context)
        manifest['github_context']=execution_context
        manifest['engine_id']=execution_context['engine_id']
    manifest['source_hashes']=source_hashes()
    for name,content in [('manifest.json',json.dumps(manifest,sort_keys=True,indent=2)),
                         ('run-id',run_id),('scope',policy.SCOPE),('owner-token',manifest['owner_token']),
                         ('host-netns',manifest['host_netns']),
                         ('execution-provider','github-hosted' if execution_context is not None else 'approved-local')]:
        path=metadata/name;path.write_text(content+'\n');path.chmod(0o444)
    config=policy.make_config(ROOT,metadata,manifest)
    (state/'compose.json').write_text(json.dumps(config,indent=2))
    return state


def load(state):
    state=Path(state)
    if state.is_symlink():raise ValueError('Symlinked state rejected')
    state=state.resolve()
    if state.is_symlink() or (state/'metadata/manifest.json').is_symlink():raise ValueError('Symlinked state rejected')
    manifest=policy.validate_manifest(json.loads((state/'metadata/manifest.json').read_text()))
    if manifest.get('source_hashes')!=source_hashes():
        raise ValueError('Prepared sources changed, added or removed; create a fresh run')
    for name,digest in manifest['source_hashes'].items():
        path=(ROOT/name).resolve()
        if ROOT not in path.parents or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise ValueError('Prepared source changed; create a fresh run')
    expected=policy.make_config(ROOT,state/'metadata',manifest)
    if json.loads((state/'compose.json').read_text())!=expected:raise ValueError('Compose plan tampered')
    return state,manifest,expected


def docker(state, manifest, args):
    if manifest.get('github_context') is not None:
        from .github_runner import runtime_approval
        approval=runtime_approval(manifest)
    else:
        approval=json.loads((ROOT/'engine-approval.json').read_text())
    if (not approval.get('nonproduction_reviewed') or not approval.get('engine_id')
            or manifest.get('engine_id')!=approval['engine_id']
            or approval.get('socket')!='unix:///var/run/docker.sock'):
        raise RuntimeError('No approved dedicated local engine; Docker invocation blocked')
    config_dir=state/'empty-docker-config';config_dir.mkdir(exist_ok=True,mode=0o700)
    prefix=['docker','--host',approval['socket'],'--config',str(config_dir)]
    environment={'PATH':'/usr/local/bin:/usr/bin:/bin'}
    info=subprocess.run(prefix+['info','--format','{{.ID}}'],env=environment,check=True,capture_output=True,text=True,timeout=900)
    if info.stdout.strip()!=approval['engine_id']:raise RuntimeError('Wrong Docker engine')
    return subprocess.run(prefix+args,env=environment,check=True,capture_output=True,text=True,timeout=900).stdout


def inventory(state, manifest):
    container_ids=docker(state,manifest,['ps','-aq','--filter','label=com.docker.compose.project='+manifest['project']]).split()
    # Network/volume list are obtained with explicit ID formatting, never parsed display names.
    network_ids=docker(state,manifest,['network','ls','-q','--no-trunc','--filter','label=com.docker.compose.project='+manifest['project']]).split()
    volume_ids=docker(state,manifest,['volume','ls','-q','--filter','label=com.docker.compose.project='+manifest['project']]).split()
    containers=json.loads(docker(state,manifest,['container','inspect',*container_ids])) if container_ids else []
    networks=json.loads(docker(state,manifest,['network','inspect',*network_ids])) if network_ids else []
    return containers,networks,volume_ids


def preflight(state):
    state,manifest,expected=load(state)
    actual=json.loads(docker(state,manifest,['compose','-p',manifest['project'],'-f',str(state/'compose.json'),'config','--format','json']))
    policy.validate_effective(actual,expected)
    if any(inventory(state,manifest)):
        raise RuntimeError('Fresh project required before creating resources')
    # Inspect every network to reject CIDR overlap before creating a bridge.
    ids=docker(state,manifest,['network','ls','-q','--no-trunc']).split()
    if ids:
        import ipaddress
        for network in json.loads(docker(state,manifest,['network','inspect',*ids])):
            for ipam in network.get('IPAM',{}).get('Config') or []:
                if ipam.get('Subnet') and ipaddress.ip_network(ipam['Subnet']).overlaps(ipaddress.ip_network(policy.SUBNET)):
                    raise RuntimeError('Disposable subnet overlaps an existing network')
    (state/'effective.json').write_text(json.dumps(actual,sort_keys=True,indent=2))


def attest(state):
    state,manifest,expected=load(state)
    actual=json.loads(docker(state,manifest,['compose','-p',manifest['project'],'-f',str(state/'compose.json'),'config','--format','json']))
    policy.validate_effective(actual,expected)
    if not (state/'effective.json').is_file() or json.loads((state/'effective.json').read_text())!=actual:
        raise RuntimeError('Pre-creation effective configuration approval missing or changed')
    containers,networks,volumes=inventory(state,manifest)
    owned=policy.owned_resources(manifest,containers,networks,volumes)
    for c in containers:
        role=c['Config']['Labels']['com.docker.compose.service'];wanted=expected['services'][role]
        if c.get('State',{}).get('Running'):raise ValueError('Attestation requires stopped, freshly created containers')
        if (c['Config'].get('Hostname')!=wanted['hostname'] or c['Config'].get('Image')!=wanted['image']
                or c.get('HostConfig',{}).get('Privileged') or c.get('HostConfig',{}).get('PortBindings')
                or c.get('HostConfig',{}).get('NetworkMode')!=manifest['network']):raise ValueError('Container runtime identity differs')
        expected_mounts={(v['target'],v['source']) for v in wanted['volumes']}
        binds={(m['Destination'],m['Source']) for m in c.get('Mounts',[]) if m['Type']=='bind'}
        if binds!=expected_mounts or any(m.get('RW') for m in c.get('Mounts',[]) if m['Type']=='bind'):
            raise ValueError('Unapproved or writable bind')
        if any(m['Type'] not in ('bind','tmpfs') for m in c.get('Mounts',[])):
            raise ValueError('Persistent/unapproved mount')
        declared={p for p in wanted.get('tmpfs',[])}
        actual_tmpfs=set(c.get('HostConfig',{}).get('Tmpfs') or {})
        if any(m['Destination'] not in declared for m in c.get('Mounts',[]) if m['Type']=='tmpfs'):
            raise ValueError('Unapproved mounted tmpfs')
        if declared!=actual_tmpfs:raise ValueError('Disposable storage mismatch')
        image=json.loads(docker(state,manifest,['image','inspect',wanted['image']]))[0]
        if c.get('Image')!=image.get('Id'):raise ValueError('Image content mismatch')
        base=image.get('Config') or {}
        explicit=dict(item.split('=',1) for item in c['Config'].get('Env',[]) if '=' in item)
        allowed=dict(item.split('=',1) for item in base.get('Env',[]) if '=' in item)
        allowed.update({k:str(v) for k,v in wanted['environment'].items()})
        if explicit!=allowed:raise ValueError('Unapproved environment binding')
        for field,key in [('Entrypoint','entrypoint'),('Cmd','command'),('User','user')]:
            if c['Config'].get(field)!=wanted.get(key,base.get(field)):
                raise ValueError('Image execution configuration changed')
        host=c['HostConfig']
        if (bool(host.get('ReadonlyRootfs'))!=bool(wanted.get('read_only'))
                or host.get('CapAdd') or (host.get('CapDrop') or [])!=wanted.get('cap_drop',[])
                or (host.get('SecurityOpt') or [])!=wanted.get('security_opt',[])
                or (host.get('Dns') or [])!=wanted.get('dns',[])
                or (host.get('Sysctls') or {})!=wanted.get('sysctls',{})
                or host.get('Memory')!=policy.canonical_service(wanted)['mem_limit']
                or set(c.get('NetworkSettings',{}).get('Networks',{}))!={manifest['network']}):
            raise ValueError('Runtime confinement changed')
    data={'run_id':manifest['run_id'],'owner_token':manifest['owner_token'],'scope':policy.SCOPE,
          'engine_id':manifest['engine_id'],'resources':owned,
          'image_ids':{c['Config']['Labels']['com.docker.compose.service']:c['Image'] for c in containers},
          'effective_sha256':hashlib.sha256(json.dumps(actual,sort_keys=True).encode()).hexdigest()}
    (state/'resources.json').write_text(json.dumps(owned,indent=2))
    for name,content in [('preflight.json',json.dumps(data,sort_keys=True,indent=2)),
                         ('preflight.ok',manifest['run_id']+':'+manifest['owner_token'])]:
        path=state/'metadata'/name;path.write_text(content+'\n');path.chmod(0o444)


def cleanup(state, authorized=False):
    if not authorized:raise RuntimeError('Explicit disposable cleanup authorization required')
    state,manifest,_=load(state)
    if not (state/'resources.json').is_file():raise RuntimeError('No recorded ownership; nothing may be removed')
    recorded=json.loads((state/'resources.json').read_text())
    containers,networks,volumes=inventory(state,manifest)
    current=policy.owned_resources(manifest,containers,networks,volumes)
    if set(current['container_ids'])!=set(recorded['container_ids']) or current['network_id']!=recorded['network_id']:
        raise RuntimeError('Inventory changed; no resources removed')
    for container in containers:
        fresh=json.loads(docker(state,manifest,['container','inspect',container['Id']]))[0]
        remaining=[fresh if c['Id']==fresh['Id'] else c for c in containers]
        policy.owned_resources(manifest,remaining,networks,volumes)
        docker(state,manifest,['container','rm','--force',container['Id']])
    # Recheck network membership after container removal; refuse a newly attached outsider.
    fresh_network=json.loads(docker(state,manifest,['network','inspect',recorded['network_id']]))[0]
    policy.owned_resources(manifest,containers,[fresh_network],volumes)
    if fresh_network.get('Containers'):raise RuntimeError('Network still in use; do not remove it')
    docker(state,manifest,['network','rm',recorded['network_id']])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','preflight','attest','cleanup'])
    parser.add_argument('--state',type=Path)
    parser.add_argument('--authorize-disposable-cleanup',action='store_true')
    args=parser.parse_args()
    if args.action=='prepare':print(prepare());return
    if not args.state:parser.error('--state is required')
    if args.action=='preflight':preflight(args.state)
    elif args.action=='attest':attest(args.state)
    else:cleanup(args.state,args.authorize_disposable_cleanup)


if __name__=='__main__':main()
