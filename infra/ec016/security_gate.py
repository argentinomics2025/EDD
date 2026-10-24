"""Mandatory image vulnerability gate. No side effects on import.

Runs only inside the authorized GitHub job. The scanner never receives a Docker
socket, production credentials or the repository. Offline scans use image archives.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
from . import labctl
from .runner import policy

MAX_DB_AGE_HOURS=72


def scanner_reference(root=None):
    root=Path(root or labctl.ROOT)
    lock=json.loads((root/'locks/scanner.json').read_text());entry=lock['image']
    body=(root/'locks/scanner-manifest.json').read_bytes()
    digest='sha256:'+hashlib.sha256(body).hexdigest()
    reference='docker.io/'+entry['repository']+':'+entry['tag']+'@'+digest
    if (lock.get('platform')!='linux/amd64' or entry['digest']!=digest or entry['reference']!=reference
            or entry['status']!='manifest_digest_verified'
            or entry['repository']!='aquasec/trivy' or not entry.get('verified_at')
            or not re.fullmatch(r'[0-9]+[.][0-9]+[.][0-9]+',entry['tag'])):
        raise RuntimeError('Scanner provenance verification failed')
    matches=[m for m in json.loads(body)['manifests'] if m.get('platform',{}).get('os')=='linux'
             and m.get('platform',{}).get('architecture')=='amd64']
    if len(matches)!=1 or matches[0]['digest']!=entry['amd64_manifest_digest']:
        raise RuntimeError('Scanner platform mismatch')
    return reference


def validate_database(metadata, now=None):
    now=now or datetime.datetime.now(datetime.timezone.utc)
    if metadata.get('Version')!=2:raise RuntimeError('Unsupported vulnerability database format')
    for key in ('UpdatedAt','DownloadedAt'):
        stamp=datetime.datetime.fromisoformat(metadata[key].replace('Z','+00:00'))
        if stamp.tzinfo is None:raise RuntimeError('Unversioned vulnerability database time')
        age=(now-stamp).total_seconds()
        if age < -600 or age > MAX_DB_AGE_HOURS*3600:
            raise RuntimeError('Vulnerability database missing or stale')


def review_report(report, *, allow_inventory_gap=False):
    results=report.get('Results')
    if results is None and allow_inventory_gap:results=[]
    if report.get('SchemaVersion')!=2 or not isinstance(results,list):
        raise RuntimeError('Missing/incomplete scanner report')
    packages=sum(len(r.get('Packages') or []) for r in results)
    if packages==0 and not allow_inventory_gap:raise RuntimeError('No package inventory; empty scan is not clearance')
    counts={'inventory_unavailable':packages==0,'packages':packages,'critical':0,'high_fixable':0,'high_unfixed':0,'other':0}
    for result in results:
        for issue in result.get('Vulnerabilities') or []:
            severity=issue.get('Severity')
            if severity not in ('UNKNOWN','LOW','MEDIUM','HIGH','CRITICAL'):
                raise RuntimeError('Unrecognized vulnerability severity')
            if not re.fullmatch(r'[A-Za-z0-9_.:-]{3,160}',issue.get('VulnerabilityID','')):
                raise RuntimeError('Malformed advisory identity')
            # Fall back to CVSS if a source leaves severity UNKNOWN.
            scores=[score.get(key,0) for score in (issue.get('CVSS') or {}).values()
                    for key in ('V2Score','V3Score','V4Score')]
            if any(type(score) not in (int,float) or not 0<=score<=10 for score in scores):
                raise RuntimeError('Malformed CVSS score')
            max_score=max(scores,default=0)
            if max_score>=9:severity='CRITICAL'
            elif severity=='UNKNOWN' and max_score>=7:severity='HIGH'
            if severity=='CRITICAL':counts['critical']+=1
            elif severity=='HIGH':counts['high_fixable' if issue.get('FixedVersion') else 'high_unfixed']+=1
            else:counts['other']+=1
    if counts['critical'] or counts['high_fixable']:
        raise RuntimeError('Blocking image vulnerability; no SQL permitted')
    # Unfixed HIGH is accepted ONLY for this short-lived synthetic lab, without
    # credentials, ingress or test-container egress. Never a production waiver.
    return counts


def sandbox_args(manifest, purpose, cache):
    args=['run','--rm','--platform','linux/amd64','--name',manifest['project']+'-security-'+purpose,
          '--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true',
          '--user',str(os.getuid())+':'+str(os.getgid()),'--memory','2g','--cpus','2',
          '--tmpfs','/tmp:rw,nosuid,nodev,size=256m','--env','HOME=/tmp',
          '--mount','type=bind,src='+str(cache)+',dst=/cache']
    for key,value in policy.labels(manifest).items():args+=['--label',key+'='+value]
    return args


def scan_before_bootstrap(state, manifest, config):
    from .github_runner import runtime_approval
    runtime_approval(manifest)
    scanner=scanner_reference()
    labctl.docker(state,manifest,['pull','--platform','linux/amd64',scanner])
    root=state/'security';root.mkdir(mode=0o700)
    cache=root/'cache';cache.mkdir(mode=0o700)
    args=sandbox_args(manifest,'db',cache)+['--network','bridge',scanner,'image',
        '--cache-dir','/cache','--download-db-only','--no-progress',
        '--db-repository','ghcr.io/aquasecurity/trivy-db:2']
    labctl.docker(state,manifest,args)
    metadata=json.loads((cache/'db/metadata.json').read_text());validate_database(metadata)
    targets={name:service['image'] for name,service in config['services'].items()}
    targets['python-base']=policy.verify_images(labctl.ROOT)['python'];targets['security-scanner']=scanner
    reviewed={}
    for index,(name,reference) in enumerate(targets.items()):
        image=json.loads(labctl.docker(state,manifest,['image','inspect',reference]))[0]
        image_id=image['Id']
        if not re.fullmatch('sha256:[a-f0-9]{64}',image_id):raise RuntimeError('Unversioned image content')
        folder=root/name;folder.mkdir(mode=0o700)
        source=folder/'input';source.mkdir(mode=0o700)
        output=folder/'output';output.mkdir(mode=0o700)
        archive=source/'image.tar'
        labctl.docker(state,manifest,['image','save','--output',str(archive),reference])
        args=sandbox_args(manifest,str(index),cache)+['--network','none',
            '--mount','type=bind,src='+str(archive)+',dst=/input/image.tar,readonly',
            '--mount','type=bind,src='+str(output)+',dst=/output',scanner,'image',
            '--cache-dir','/cache','--input','/input/image.tar','--skip-db-update',
            '--skip-java-db-update','--offline-scan','--scanners','vuln','--list-all-pkgs',
            '--format','json','--output','/output/report.json','--quiet']
        labctl.docker(state,manifest,args)
        report=json.loads((output/'report.json').read_text())
        if report.get('Metadata',{}).get('ImageID')!=image_id:
            raise RuntimeError('Scan belongs to a different image')
        reviewed[name]={'image_id':image_id,'counts':review_report(report,allow_inventory_gap=(name=='ec016-api' and reference==policy.verify_images(labctl.ROOT)['postgrest'])),
                        'report_sha256':hashlib.sha256((output/'report.json').read_bytes()).hexdigest()}
        archive.unlink()  # Own newly generated archive only, never an image or foreign volume.
    proof={'run_id':manifest['run_id'],'owner_token':manifest['owner_token'],
           'engine_id':manifest['engine_id'],'source_sha':manifest['github_context']['source_sha'],
           'database_updated_at':metadata['UpdatedAt'],'scanner':scanner,'images':reviewed}
    for name,content in [('security.json',json.dumps(proof)),
                         ('security.ok',manifest['run_id']+':'+manifest['owner_token'])]:
        path=state/'metadata'/name;path.write_text(content+'\n');path.chmod(0o444)
    print(json.dumps({'ec016_security':{name:data['counts'] for name,data in reviewed.items()}},sort_keys=True))
    return proof


def verify_clearance(state,manifest):
    proof=json.loads((state/'metadata/security.json').read_text())
    if (proof.get('run_id')!=manifest['run_id'] or proof.get('owner_token')!=manifest['owner_token']
            or proof.get('engine_id')!=manifest['engine_id']
            or proof.get('source_sha')!=manifest['github_context']['source_sha']):
        raise RuntimeError('Cross-run vulnerability clearance')
    attestation=json.loads((state/'metadata/preflight.json').read_text())
    for name,image_id in attestation['image_ids'].items():
        if proof['images'][name]['image_id']!=image_id:raise RuntimeError('Unscanned runtime image')
    if (state/'metadata/security.ok').read_text().strip()!=manifest['run_id']+':'+manifest['owner_token']:
        raise RuntimeError('Missing vulnerability clearance')
