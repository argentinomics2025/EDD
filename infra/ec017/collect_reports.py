"""Eight public-image reports only. No services, SQL, SDK or publication imports."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from infra.ec016.runner import policy
from infra.ec016.security_gate import validate_database
from infra.ec016.github_runner import validate_host_context, REPOSITORY, REF

BASELINE='922c1fc5094c485bce97a2d8f3c044381efcb188'
WORKFLOW=REPOSITORY+'/.github/workflows/ec017_reports.yml@'+REF
COMPONENTS=('postgres','postgrest','python','runner')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(args, *, check=True):
    # No inherited tokens, proxies, Docker contexts or connection strings.
    validate_host_context(workflow=WORKFLOW)
    temp=Path(os.environ['RUNNER_TEMP'])
    env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':str(temp),
         'DOCKER_CONFIG':str(temp/'ec017-empty-docker')}
    return subprocess.run(args,env=env,check=check,capture_output=True,text=True,timeout=1200)


def docker(args):
    return command(['docker','--host','unix:///var/run/docker.sock',*args]).stdout


def inspect_image(reference):
    data=json.loads(docker(['image','inspect',reference]))[0]
    if (data.get('Architecture')!='amd64' or data.get('Os')!='linux'
            or not re.fullmatch(r'sha256:[a-f0-9]{64}',data.get('Id',''))):
        raise RuntimeError('Invalid image')
    return data['Id']


def review(report, image_id, *, inventory_gap=False):
    if report.get('SchemaVersion')!=2 or report.get('Metadata',{}).get('ImageID')!=image_id:
        raise ValueError('Unbound report')
    results=report.get('Results',[] if inventory_gap else None)
    if not isinstance(results,list):raise ValueError('Missing results')
    packages=0;counts={'HIGH':0,'CRITICAL':0}
    for result in results:
        entries=result.get('Packages') or []
        if not isinstance(entries,list):raise ValueError('Invalid inventory')
        packages+=len(entries)
        for issue in result.get('Vulnerabilities') or []:
            if (not issue.get('VulnerabilityID') or not issue.get('PkgName')
                    or not issue.get('InstalledVersion')):
                raise ValueError('Incomplete vulnerability')
            # FixedVersion may be absent/empty when no upstream fix exists.
            severity=issue.get('Severity')
            if severity not in ('UNKNOWN','LOW','MEDIUM','HIGH','CRITICAL'):
                raise ValueError('Invalid severity')
            if severity in counts:counts[severity]+=1
    if not packages and not inventory_gap:raise ValueError('Missing inventory')
    return {'packages':packages,'inventory_unavailable':not packages,**counts}


def scan(root, evidence, group, name, reference, image_id):
    report=evidence/(group+'-'+name+'.json')
    run=command([str(root/'trivy'),'image','--cache-dir',str(root/'cache'),
        '--config',str(root/'config.yaml'),'--ignorefile',str(root/'empty.ignore'),
        '--scanners','vuln','--list-all-pkgs','--severity','HIGH,CRITICAL',
        '--ignore-unfixed=false','--exit-code','1','--format','json',
        '--quiet','--timeout','10m','--output',str(report),reference],check=False)
    record={'group':group,'component':name,'exit_code':run.returncode,'complete':False,
            'scanned_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    # Never publish either command stream, even on failure.
    if report.is_file():
        record['report_sha256']=digest(report)
        try:
            record['findings']=review(json.loads(report.read_text()),image_id,inventory_gap=name=='postgrest')
            db=root/'cache/db/metadata.json'
            metadata=json.loads(db.read_text());validate_database(metadata)
            record['database']=metadata
            record['database_metadata_sha256']=digest(db)
            record['complete']=run.returncode in (0,1)
            if run.returncode==1 and not any(record['findings'][s] for s in ('HIGH','CRITICAL')):
                record['complete']=False
        except Exception:pass
    return record


def approved(records):
    expected={(group,name) for group in ('original','candidate') for name in COMPONENTS}
    if len(records)!=8 or {(r['group'],r['component']) for r in records}!=expected:return False
    if not all(r.get('complete') and r.get('exit_code') in (0,1) for r in records):return False
    # Baseline vulnerabilities are evidence, never clearance for candidate images.
    return all(r['exit_code']==0 and not any(r['findings'][s] for s in ('HIGH','CRITICAL'))
               for r in records if r['group']=='candidate')


def main():
    binding=validate_host_context(workflow=WORKFLOW)
    checkout=Path.cwd()
    if command(['git','rev-parse','HEAD']).stdout.strip()!=binding['source_sha']:
        raise RuntimeError('Unapproved checkout')
    original=checkout/'ec017-original'
    if command(['git','-C',str(original),'rev-parse','HEAD']).stdout.strip()!=BASELINE:
        raise RuntimeError('Wrong baseline')
    root=Path(os.environ['RUNNER_TEMP'])/'ec017-trivy'
    evidence=root/'evidence';evidence.mkdir(mode=0o700,exist_ok=False)
    version=command([str(root/'trivy'),'--version']).stdout
    if not version.startswith('Version: 0.69.3'):raise RuntimeError('Wrong scanner')
    records=[]
    for group,source in [('original',original),('candidate',checkout)]:
        lab=source/'infra/ec016';refs=policy.verify_images(lab)
        lock=json.loads((lab/'locks/images.json').read_text())['images']
        for name in COMPONENTS:
            record={'group':group,'component':name,'complete':False}
            try:
                if name=='runner':
                    reference='ec017-'+group+':'+binding['run_id']
                    docker(['build','--platform','linux/amd64','--build-arg','PYTHON_IMAGE='+refs['python'],
                            '-t',reference,str(lab)])
                    provenance={'base_reference':refs['python'],'dockerfile_sha256':digest(lab/'Dockerfile'),
                                'requirements_sha256':digest(lab/'requirements.lock')}
                else:
                    reference=refs[name]
                    index=json.loads((lab/'locks'/(name+'-manifest.json')).read_text())
                    platform=[m['digest'] for m in index['manifests']
                              if m.get('platform',{}).get('os')=='linux'
                              and m.get('platform',{}).get('architecture')=='amd64']
                    if platform!=[lock[name]['amd64_manifest_digest']]:
                        raise ValueError('Unverified platform receipt')
                    docker(['pull','--platform','linux/amd64',reference])
                    provenance={'index_digest':lock[name]['digest'],
                                'amd64_manifest_digest':lock[name]['amd64_manifest_digest']}
                image_id=inspect_image(reference)
                record.update(scan(root,evidence,group,name,reference,image_id))
                record.update(provenance,reference=reference,image_id=image_id,
                    source_sha=BASELINE if group=='original' else binding['source_sha'])
            except Exception:
                record['complete']=False
            records.append(record)
    result={'source_sha':binding['source_sha'],'baseline_sha':BASELINE,'scanner':'0.69.3',
            'run_id':binding['run_id'],'collected_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'reports':records,'candidate_gate_passed':approved(records)}
    (evidence/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    print('EC017_REPORTS_COMPLETE' if all(r.get('complete') for r in records) else 'EC017_REPORTS_INCOMPLETE')
    raise SystemExit(0 if result['candidate_gate_passed'] else 1)


if __name__=='__main__':
    try:main()
    except Exception:
        print('EC017_COLLECTION_FAILED')
        raise SystemExit(1) from None
