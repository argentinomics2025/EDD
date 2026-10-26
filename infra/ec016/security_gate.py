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
import subprocess
from . import labctl
from .runner import policy
from .diagnostics import Failure, classify, emit, validate_public

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


def command_reason(error):
    """Classify captured errors internally; never return text, paths or arguments."""
    if isinstance(error,subprocess.TimeoutExpired):return 'COMMAND_TIMEOUT'
    if isinstance(error,subprocess.CalledProcessError):
        if error.returncode==137:return 'KILLED_137'  # Could be a signal, not proof of OOM.
        text=' '.join(value.lower() for value in (error.stderr,error.stdout) if isinstance(value,str))
        for marker,reason in (('permission denied','PERMISSION_DENIED'),
                              ('read-only file system','READ_ONLY_FS'),
                              ('unknown flag','CLI_OPTION'),('flag provided but not defined','CLI_OPTION'),
                              ('toomanyrequests','RATE_LIMIT'),('too many requests','RATE_LIMIT'),
                              ('unauthorized','REGISTRY_AUTH'),('authentication required','REGISTRY_AUTH'),
                              ('no such host','NETWORK'),('connection refused','NETWORK'),
                              ('network is unreachable','NETWORK'),('i/o timeout','NETWORK'),
                              ('x509:','TLS'),('tls handshake timeout','TLS')):
            if marker in text:return reason
        return 'COMMAND_FAILED'
    if isinstance(error,json.JSONDecodeError):return 'INVALID_JSON'
    if isinstance(error,FileNotFoundError):return 'REQUIRED_FILE'
    return 'CHECK_FAILED'


def scan_operation(code,subject,function,*args,**kwargs):
    validate_public('SCAN',code,subject)
    emit('SCAN',code,'START',subject=subject)
    try:result=function(*args,**kwargs)
    except Failure:raise
    except Exception as error:
        known=classify('SCAN',error)
        if known.code in ('SCAN_REJECTED','SCAN_DATABASE','SCAN_INVENTORY'):
            raise Failure('SCAN',known.code,subject=subject) from None
        raise Failure('SCAN',code,subject=subject,reason=command_reason(error)) from None
    emit('SCAN',code,'OK',subject=subject)
    return result


def read_database(cache):
    metadata=json.loads((cache/'db/metadata.json').read_text())
    validate_database(metadata)
    return metadata


def read_image(state,manifest,reference):
    image=json.loads(labctl.docker(state,manifest,['image','inspect',reference]))[0]
    if not re.fullmatch('sha256:[a-f0-9]{64}',image.get('Id','')):
        raise RuntimeError('Unversioned image content')
    return image['Id']


def read_report(path,image_id):
    report=json.loads(path.read_text())
    if report.get('Metadata',{}).get('ImageID')!=image_id:
        raise RuntimeError('Scan belongs to a different image')
    return report


def write_proof(state,manifest,proof):
    for name,content in [('security.json',json.dumps(proof)),
                         ('security.ok',manifest['run_id']+':'+manifest['owner_token'])]:
        path=state/'metadata'/name;path.write_text(content+'\n');path.chmod(0o444)


def scan_before_bootstrap(state, manifest, config):
    from .github_runner import runtime_approval
    runtime_approval(manifest)
    scanner=scanner_reference()
    scan_operation('SCAN_SCANNER_PULL','SCANNER',labctl.docker,state,manifest,
                   ['pull','--platform','linux/amd64',scanner])
    root=state/'security';root.mkdir(mode=0o700)
    cache=root/'cache';cache.mkdir(mode=0o700)
    args=sandbox_args(manifest,'db',cache)+['--network','bridge',scanner,'image',
        '--cache-dir','/cache','--download-db-only','--no-progress',
        '--db-repository','ghcr.io/aquasecurity/trivy-db:2']
    scan_operation('SCAN_DB_DOWNLOAD','VULN_DATABASE',labctl.docker,state,manifest,args)
    metadata=scan_operation('SCAN_DB_VALIDATE','VULN_DATABASE',read_database,cache)
    targets={name:service['image'] for name,service in config['services'].items()}
    targets['python-base']=policy.verify_images(labctl.ROOT)['python'];targets['security-scanner']=scanner
    reviewed={}
    subjects={'ec016-db':'POSTGRES','ec016-api':'POSTGREST','ec016-tests':'LAB_RUNNER',
              'python-base':'PYTHON_BASE','security-scanner':'SCANNER'}
    for index,(name,reference) in enumerate(targets.items()):
        subject=subjects[name]
        image_id=scan_operation('SCAN_IMAGE_INSPECT',subject,read_image,state,manifest,reference)
        folder=root/name;folder.mkdir(mode=0o700)
        source=folder/'input';source.mkdir(mode=0o700)
        output=folder/'output';output.mkdir(mode=0o700)
        archive=source/'image.tar'
        scan_operation('SCAN_IMAGE_EXPORT',subject,labctl.docker,state,manifest,
                       ['image','save','--output',str(archive),reference])
        args=sandbox_args(manifest,str(index),cache)+['--network','none',
            '--mount','type=bind,src='+str(archive)+',dst=/input/image.tar,readonly',
            '--mount','type=bind,src='+str(output)+',dst=/output',scanner,'image',
            '--cache-dir','/cache','--input','/input/image.tar','--skip-db-update',
            '--skip-java-db-update','--offline-scan','--scanners','vuln','--list-all-pkgs',
            '--format','json','--output','/output/report.json','--quiet']
        scan_operation('SCAN_IMAGE_RUN',subject,labctl.docker,state,manifest,args)
        report=scan_operation('SCAN_REPORT_READ',subject,read_report,output/'report.json',image_id)
        counts=scan_operation('SCAN_REPORT_CHECK',subject,review_report,report,
                allow_inventory_gap=(name=='ec016-api' and reference==policy.verify_images(labctl.ROOT)['postgrest']))
        reviewed[name]={'image_id':image_id,'counts':counts,
                        'report_sha256':hashlib.sha256((output/'report.json').read_bytes()).hexdigest()}
        archive.unlink()  # Own newly generated archive only, never an image or foreign volume.
    proof={'run_id':manifest['run_id'],'owner_token':manifest['owner_token'],
           'engine_id':manifest['engine_id'],'source_sha':manifest['github_context']['source_sha'],
           'database_updated_at':metadata['UpdatedAt'],'scanner':scanner,'images':reviewed}
    scan_operation('SCAN_PROOF_WRITE','LAB_RUNNER',write_proof,state,manifest,proof)
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
