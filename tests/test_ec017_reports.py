"""EC-017 preparatory checks: no Docker, SQL, images or network."""
import copy
import datetime
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import yaml
from infra.ec017 import collect_reports as reports
from infra.ec016.runner import policy

ROOT=Path(__file__).resolve().parents[1]
IMAGE='sha256:'+'a'*64


def report(high=False):
    return {'SchemaVersion':2,'Metadata':{'ImageID':IMAGE},'Results':[{
        'Packages':[{'Name':'synthetic','Version':'1'}],
        'Vulnerabilities':[{'VulnerabilityID':'CVE-2026-0001','PkgName':'synthetic',
                            'InstalledVersion':'1','FixedVersion':'2','Severity':'HIGH'}] if high else []}]}


class Reports(unittest.TestCase):
    def test_workflow_manual_pinned_no_services_always_uploads_json_only(self):
        text=(ROOT/'.github/workflows/ec017_reports.yml').read_text();w=yaml.safe_load(text)
        self.assertEqual(set(w.get('on',w.get(True))),{'workflow_dispatch'})
        self.assertEqual(w['permissions'],{'contents':'read'})
        self.assertEqual(set(w['jobs']),{'reports'})
        job=w['jobs']['reports'];self.assertNotIn('services',job);self.assertNotIn('container',job)
        self.assertEqual(job['runs-on'],'ubuntu-24.04')
        steps=job['steps'];self.assertEqual(steps[0]['id'],'authorization')
        for s in steps:
            if 'uses' in s:self.assertRegex(s['uses'],r'@[a-f0-9]{40}$')
        upload=steps[-1];self.assertIn('always()',upload['if'])
        self.assertTrue(upload['with']['path'].endswith('/evidence/*.json'))
        self.assertEqual(upload['with']['retention-days'],1)
        self.assertEqual(upload['with']['if-no-files-found'],'error')
        self.assertNotIn('continue-on-error',text);self.assertNotIn('secrets.',text)
        baseline=next(s for s in steps if s.get('with',{}).get('path')=='ec017-original')
        self.assertEqual(baseline['with']['ref'],reports.BASELINE)

    def test_authorized_trixie_candidates_and_verified_receipts(self):
        refs=policy.verify_images(ROOT/'infra/ec016')
        self.assertEqual(refs['postgres'],'docker.io/library/postgres:16.15-trixie@sha256:9e2cf6287f25c3151f4c9421ccce2b17f3e60061c111a29165e0d2cdd9ff0a97')
        self.assertEqual(refs['python'],'docker.io/library/python:3.12.14-slim-trixie@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f')
        self.assertEqual(refs['postgrest'],'docker.io/postgrest/postgrest:v12.2.12@sha256:5f4ce744539bbba786b4e24dbbd95bdb2a956dcf568c5374995a0ff4a68f5bd2')

    def test_report_requires_identity_inventory_and_complete_vulnerability(self):
        self.assertEqual(reports.review(report(True),IMAGE)['HIGH'],1)
        for change in [{'Metadata':{'ImageID':'wrong'}},{'Results':[]},{'SchemaVersion':1}]:
            with self.assertRaises(ValueError):reports.review(dict(report(),**change),IMAGE)
        bad=report(True);del bad['Results'][0]['Vulnerabilities'][0]['InstalledVersion']
        with self.assertRaises(ValueError):reports.review(bad,IMAGE)
        missing_fix=report(True);del missing_fix['Results'][0]['Vulnerabilities'][0]['FixedVersion']
        self.assertEqual(reports.review(missing_fix,IMAGE)['HIGH'],1)

    def test_any_candidate_high_or_critical_even_unfixed_blocks(self):
        records=[{'group':g,'component':c,'complete':True,'exit_code':0,
                  'findings':{'HIGH':0,'CRITICAL':0}} for g in ('original','candidate') for c in reports.COMPONENTS]
        records[0].update(exit_code=1,findings={'HIGH':116,'CRITICAL':16})
        self.assertTrue(reports.approved(records))
        for severity in ('HIGH','CRITICAL'):
            bad=copy.deepcopy(records);bad[-1]['findings'][severity]=1
            self.assertFalse(reports.approved(bad))
        for field,value in [('complete',False),('exit_code',2)]:
            bad=copy.deepcopy(records);bad[0][field]=value
            self.assertFalse(reports.approved(bad))
        self.assertFalse(reports.approved(records[:-1]))

    def test_scan_preserves_json_findings_and_db_metadata_on_exit_one(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);evidence=root/'evidence';evidence.mkdir()
            (root/'cache/db').mkdir(parents=True)
            now=datetime.datetime.now(datetime.timezone.utc).isoformat()
            metadata={'Version':2,'UpdatedAt':now,'DownloadedAt':now}
            (root/'cache/db/metadata.json').write_text(json.dumps(metadata))
            def run(args,**kwargs):
                self.assertIn('--ignore-unfixed=false',args)
                self.assertEqual(args[args.index('--severity')+1],'HIGH,CRITICAL')
                self.assertEqual(args[args.index('--exit-code')+1],'1')
                Path(args[args.index('--output')+1]).write_text(json.dumps(report(True)))
                return subprocess.CompletedProcess(args,1,'PRIVATE','PRIVATE')
            with patch.object(reports,'command',side_effect=run),patch('sys.stdout',io.StringIO()) as output:
                data=reports.scan(root,evidence,'original','postgres','fixed-image',IMAGE)
            self.assertTrue(data['complete']);self.assertEqual(data['findings']['HIGH'],1)
            self.assertEqual(data['database'],metadata)
            self.assertEqual(output.getvalue(),'')
            self.assertIn('FixedVersion', (evidence/'original-postgres.json').read_text())
            metadata['UpdatedAt']='2020-01-01T00:00:00Z'
            (root/'cache/db/metadata.json').write_text(json.dumps(metadata))
            with patch.object(reports,'command',side_effect=run):
                self.assertFalse(reports.scan(root,evidence,'original','postgres','fixed-image',IMAGE)['complete'])

    def test_main_attempts_all_eight_and_rebuilds_both_source_trees(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);temp=root/'temp';temp.mkdir();(temp/'ec017-trivy').mkdir()
            for dest in (root/'infra/ec016',root/'ec017-original/infra/ec016'):
                shutil.copytree(ROOT/'infra/ec016',dest)
            def command(args,**kwargs):
                if '--version' in args:return subprocess.CompletedProcess(args,0,'Version: 0.69.3\n','')
                return subprocess.CompletedProcess(args,0,(reports.BASELINE if '-C' in args else 'c'*40)+'\n','')
            def scan(trivy,evidence,group,name,ref,image):
                (evidence/(group+'-'+name+'.json')).write_text(json.dumps(report(group=='original')))
                return {'group':group,'component':name,'complete':True,'exit_code':1 if group=='original' else 0,
                        'findings':{'HIGH':1 if group=='original' else 0,'CRITICAL':0}}
            binding={'source_sha':'c'*40,'run_id':'123'}
            with patch.object(reports,'validate_host_context',return_value=binding), \
                 patch.object(reports.Path,'cwd',return_value=root),patch.object(reports,'command',side_effect=command), \
                 patch.object(reports,'docker',return_value='') as docker,patch.object(reports,'inspect_image',return_value=IMAGE), \
                 patch.object(reports,'scan',side_effect=scan) as scanning, \
                 patch.object(reports,'native_inventory',return_value={'file':'synthetic'}) as native, \
                 patch.dict(os.environ,{'RUNNER_TEMP':str(temp)}),patch('sys.stdout',io.StringIO()):
                with self.assertRaises(SystemExit) as caught:reports.main()
            self.assertEqual(caught.exception.code,0);self.assertEqual(scanning.call_count,8);self.assertEqual(native.call_count,2)
            builds=[c.args[0] for c in docker.call_args_list if c.args[0][0]=='build']
            self.assertEqual(len(builds),2)
            self.assertNotEqual(builds[0][-1],builds[1][-1])
            manifest=json.loads((temp/'ec017-trivy/evidence/manifest.json').read_text())
            self.assertEqual(len(manifest['reports']),8)
            self.assertTrue(manifest['candidate_gate_passed'])

    def test_local_command_cannot_contact_shared_docker(self):
        with patch.dict(os.environ,{},clear=True),patch.object(reports.subprocess,'run') as run:
            with self.assertRaises(Exception):reports.docker(['info'])
            run.assert_not_called()
