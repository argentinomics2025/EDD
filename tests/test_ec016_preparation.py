"""Static/unit EC016 hardening checks. Never invoke Docker, HTTP or SQL."""
import ast
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from infra.ec016 import labctl
from infra.ec016.runner import lab_guard as guard, policy
from scripts import ica_common

ROOT=labctl.ROOT


def manifest():
    run='a'*32
    return {'scope':policy.SCOPE,'run_id':run,'owner_token':'b'*64,
            'project':'ec016-'+run,'network':'ec016-'+run+'-isolated','host_netns':'net:[123]'}


def inventory(m):
    containers=[]
    for i,service in enumerate(policy.IPS,1):
        tags=policy.labels(m)
        tags.update({'com.docker.compose.project':m['project'],'com.docker.compose.service':service,
                     policy.LABEL+'.service':service})
        containers.append({'Id':str(i)*64,'Config':{'Labels':tags}})
    tags=policy.labels(m);tags['com.docker.compose.project']=m['project']
    network={'Id':'4'*64,'Name':m['network'],'Labels':tags,'Internal':True,
             'IPAM':{'Config':[{'Subnet':policy.SUBNET,'Gateway':'172.30.216.1'}]},'Containers':{}}
    return containers,[network],[]


class EC016PreparationTests(unittest.TestCase):
    def setUp(self):
        for target in ('socket.socket.connect','subprocess.run'):
            block=patch(target,side_effect=AssertionError('No service/process access in unit tests'))
            block.start();self.addCleanup(block.stop)

    def config(self):
        return policy.make_config(ROOT,Path('/tmp/ec016-synthetic-metadata'),manifest())

    def test_default_execution_blocked(self):
        with patch.dict('os.environ',{},clear=True),self.assertRaises(RuntimeError):guard.admin_connection()
        with patch.dict('os.environ',{},clear=True),self.assertRaises(RuntimeError):guard.api_client()

    def test_opt_in_is_exact(self):
        guard.assert_opt_in({'EC016_EXECUTE_DISPOSABLE':'YES_SYNTHETIC_ONLY'})
        for value in ('','true','YES','yes_synthetic_only'):
            with self.assertRaises(RuntimeError):guard.assert_opt_in({'EC016_EXECUTE_DISPOSABLE':value})

    def test_all_connection_overrides_rejected(self):
        for name in guard.FORBIDDEN_BINDINGS|{'PGHOSTADDR','PGSSLMODE','supabase_custom'}:
            with self.subTest(name=name),self.assertRaises(RuntimeError):
                guard.assert_opt_in({'EC016_EXECUTE_DISPOSABLE':'YES_SYNTHETIC_ONLY',name:'synthetic'})

    def test_host_execution_fails_even_with_opt_in(self):
        with patch.dict('os.environ',{'EC016_EXECUTE_DISPOSABLE':'YES_SYNTHETIC_ONLY'},clear=True):
            with self.assertRaises((RuntimeError,FileNotFoundError)) :guard.runtime_context()

    def test_fixed_db_parameters_ignore_environment(self):
        with patch.dict('os.environ',{'DATABASE_URL':'postgres://example.invalid/production'},clear=True):
            params=guard.db_parameters()
        self.assertEqual((params['host'],params['hostaddr'],params['dbname']),
                         ('172.30.216.2','172.30.216.2','ec016_disposable'))

    def test_private_http_allowlist(self):
        guard.validate_http_target(guard.API_URL+'/datos_comex?select=*')
        for url in ('https://example.invalid/datos_comex','http://127.0.0.1:3000/datos_comex',
                    'http://172.30.216.3:80/datos_comex','http://172.30.216.30:3000/datos_comex',
                    'http://user:pw@172.30.216.3:3000/datos_comex',
                    guard.API_URL+'/unknown',guard.API_URL+'/datos_comex#fragment'):
            with self.subTest(url=url),self.assertRaises(ValueError):guard.validate_http_target(url)

    def test_db_and_rest_same_run_marker(self):
        m=manifest();marker={'scope':policy.SCOPE,'run_id':m['run_id'],'owner_token':m['owner_token']}
        guard.validate_marker(guard.DB_NAME,'ec016_admin',marker,m)
        policy.validate_marker_payload(marker,m)
        for key in marker:
            other=dict(marker);other[key]='different-run'
            with self.assertRaises(RuntimeError):guard.validate_marker(guard.DB_NAME,'ec016_admin',other,m)
            with self.assertRaises(RuntimeError):policy.validate_marker_payload(other,m)
        with self.assertRaises(RuntimeError):guard.validate_marker('postgres','ec016_admin',marker,m)

    def test_verified_image_evidence(self):
        refs=policy.verify_images(ROOT)
        self.assertEqual(set(refs),{'postgres','python','postgrest'})
        for ref in refs.values():
            self.assertRegex(ref,r'@sha256:[a-f0-9]{64}$');self.assertNotIn(':latest',ref)

    def test_image_digest_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'locks').mkdir()
            for source in (ROOT/'locks').glob('*manifest.json'):(root/'locks'/source.name).write_bytes(source.read_bytes())
            (root/'locks/images.json').write_bytes((ROOT/'locks/images.json').read_bytes())
            with (root/'locks/postgres-manifest.json').open('ab') as stream:stream.write(b' ')
            with self.assertRaises(ValueError):policy.verify_images(root)

    def test_dependencies_transitively_locked(self):
        self.assertEqual(policy.verify_dependencies(ROOT)['status'],'resolved_not_installed')
        text=(ROOT/'Dockerfile').read_text()
        self.assertIn('--require-hashes',text);self.assertIn('--only-binary=:all:',text)
        self.assertIn('ARG PYTHON_IMAGE',text);self.assertIn('FROM ${PYTHON_IMAGE}',text)

    def test_unique_runs_and_no_processes(self):
        with tempfile.TemporaryDirectory() as directory:
            a=labctl.prepare(directory);b=labctl.prepare(directory)
            self.assertNotEqual(a.name,b.name)
            _,ma,ca=labctl.load(a);_,mb,cb=labctl.load(b)
            self.assertNotEqual(ma['owner_token'],mb['owner_token'])
            self.assertNotEqual(ca['name'],cb['name'])
            self.assertIsNone(ma['engine_id'])

    def test_unapproved_engine_blocks_before_docker(self):
        with tempfile.TemporaryDirectory() as directory:
            state=labctl.prepare(directory);_,m,_=labctl.load(state)
            with self.assertRaisesRegex(RuntimeError,'approved dedicated'):labctl.docker(state,m,['info'])

    def test_tampered_plan_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            state=labctl.prepare(directory);path=state/'compose.json'
            config=json.loads(path.read_text());config['services']['ec016-db']['ports']=['5432:5432']
            path.write_text(json.dumps(config))
            with self.assertRaises(ValueError):labctl.load(state)

    def test_added_source_after_prepare_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            state=labctl.prepare(directory)
            changed=labctl.source_hashes();changed['runner/unreviewed.py']='0'*64
            with patch.object(labctl,'source_hashes',return_value=changed),self.assertRaises(ValueError):labctl.load(state)

    def test_symlinked_state_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            state=labctl.prepare(directory);link=Path(directory)/'link';link.symlink_to(state,target_is_directory=True)
            with self.assertRaises(ValueError):labctl.load(link)

    def test_effective_config_allowed(self):
        config=self.config();self.assertTrue(policy.validate_effective(config,config))
        normalized=copy.deepcopy(config)
        for service in normalized['services'].values():
            service['mem_limit']=int(service['mem_limit'][:-1])*1024*1024
        normalized['services']['ec016-tests']['depends_on']={'ec016-api':{'condition':'service_started','required':True,'restart':False}}
        self.assertTrue(policy.validate_effective(normalized,config))

    def test_effective_unsafe_service_options(self):
        config=self.config()
        for key,value in {'ports':['5432:5432'],'env_file':['.env'],'network_mode':'host',
                          'privileged':True,'devices':['/dev/sda'],'cap_add':['ALL'],
                          'volumes_from':['foreign'],'extra_hosts':['foreign:1.2.3.4']}.items():
            actual=copy.deepcopy(config);actual['services']['ec016-db'][key]=value
            with self.subTest(option=key),self.assertRaises(ValueError):policy.validate_effective(actual,config)

    def test_effective_destinations_and_mounts(self):
        config=self.config()
        for mutation in ('env','mount','network','image','build','command'):
            actual=copy.deepcopy(config);service=actual['services']['ec016-tests']
            if mutation=='env':service['environment']['DATABASE_URL']='postgres://example.invalid/prod'
            if mutation=='mount':service['volumes'][0]['read_only']=False
            if mutation=='network':service['networks']['host']={}
            if mutation=='image':service['image']='python:latest'
            if mutation=='build':service['build']['context']='/tmp/foreign'
            if mutation=='command':service['command']=['bash']
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):policy.validate_effective(actual,config)

    def test_effective_network_and_persistent_volume_rejected(self):
        config=self.config()
        for mutation in ('internal','external','ipam','volume','extra-network'):
            actual=copy.deepcopy(config);net=actual['networks']['isolated']
            if mutation=='internal':net['internal']=False
            if mutation=='external':net['external']=True
            if mutation=='ipam':net['ipam']['config'][0]['subnet']='10.0.0.0/8'
            if mutation=='volume':actual['volumes']={'foreign':{}}
            if mutation=='extra-network':actual['networks']['foreign']={}
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):policy.validate_effective(actual,config)

    def test_owned_cleanup_accepts_only_run_ids(self):
        m=manifest();owned=policy.owned_resources(m,*inventory(m))
        self.assertEqual(owned['network_id'],'4'*64);self.assertEqual(owned['volume_ids'],[])

    def test_cleanup_rejects_foreign_resources(self):
        m=manifest()
        for mutation in ('owner','project','service','duplicate','outsider','volume','subnet','id'):
            containers,networks,volumes=inventory(m)
            if mutation=='owner':containers[0]['Config']['Labels'][policy.LABEL+'.owner']='foreign'
            if mutation=='project':containers[0]['Config']['Labels']['com.docker.compose.project']='foreign'
            if mutation=='service':containers[0]['Config']['Labels']['com.docker.compose.service']='foreign'
            if mutation=='duplicate':containers[1]=copy.deepcopy(containers[0])
            if mutation=='outsider':networks[0]['Containers']={'9'*64:{}}
            if mutation=='volume':volumes=['foreign']
            if mutation=='subnet':networks[0]['IPAM']['Config'][0]['Subnet']='10.0.0.0/8'
            if mutation=='id':containers[0]['Id']='foreign'
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):policy.owned_resources(m,containers,networks,volumes)

    def test_cleanup_needs_authorization_and_attestation(self):
        with self.assertRaises(RuntimeError):labctl.cleanup('/nonexistent')
        with tempfile.TemporaryDirectory() as directory:
            state=labctl.prepare(directory)
            with self.assertRaisesRegex(RuntimeError,'recorded ownership'):labctl.cleanup(state,True)

    def test_cleanup_foreign_inventory_causes_zero_removals(self):
        with tempfile.TemporaryDirectory() as directory:
            state=labctl.prepare(directory);_,m,_=labctl.load(state)
            resources=inventory(m)
            (state/'resources.json').write_text(json.dumps(policy.owned_resources(m,*resources)))
            resources[0][0]['Config']['Labels'][policy.LABEL+'.owner']='foreign'
            with patch.object(labctl,'inventory',return_value=resources),patch.object(labctl,'docker') as docker:
                with self.assertRaises(ValueError):labctl.cleanup(state,True)
                docker.assert_not_called()

    def test_cleanup_removes_only_recorded_immutable_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            state=labctl.prepare(directory);_,m,_=labctl.load(state)
            containers,networks,volumes=inventory(m)
            (state/'resources.json').write_text(json.dumps(policy.owned_resources(m,containers,networks,volumes)))
            calls=[]
            def fake_docker(state,run,args):
                calls.append(args)
                if args[:2]==['container','inspect']:
                    return json.dumps([next(c for c in containers if c['Id']==args[2])])
                if args[:2]==['network','inspect']:return json.dumps(networks)
                return ''
            with patch.object(labctl,'inventory',return_value=(containers,networks,volumes)),patch.object(labctl,'docker',side_effect=fake_docker):
                labctl.cleanup(state,True)
            removals=[args for args in calls if args[1]=='rm']
            self.assertEqual(removals,[['container','rm','--force',c['Id']] for c in containers]+[['network','rm',networks[0]['Id']]])

    def test_preflight_rejects_existing_project_without_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            state=labctl.prepare(directory);_,m,config=labctl.load(state)
            with patch.object(labctl,'docker',return_value=json.dumps(config)) as docker,patch.object(labctl,'inventory',return_value=inventory(m)):
                with self.assertRaisesRegex(RuntimeError,'Fresh project'):labctl.preflight(state)
                self.assertEqual(len(docker.call_args_list),1)
                self.assertFalse((state/'effective.json').exists())

    def test_no_global_cleanup_or_automatic_start(self):
        tree=ast.parse((ROOT/'labctl.py').read_text())
        literals=[n.value for n in ast.walk(tree) if isinstance(n,ast.Constant) and isinstance(n.value,str)]
        for word in ('down','prune','--remove-orphans','--volumes','up','start','pull'):
            self.assertNotIn(word,literals)

    def test_bootstrap_gate_precedes_sql_and_image_entrypoint(self):
        shell=(ROOT/'bootstrap.sh').read_text();entry=(ROOT/'db-entrypoint.sh').read_text();sql=(ROOT/'schema.sql').read_text()
        self.assertLess(shell.index('preflight.ok'),shell.index('\npsql '))
        self.assertIn('--host=/var/run/postgresql',shell)
        self.assertLess(entry.index('preflight.ok'),entry.index('exec /usr/local/bin/docker-entrypoint.sh'))
        self.assertLess(sql.index("current_setting('ec016.run_id',true)"),sql.index('CREATE ROLE'))
        self.assertIn("current_setting('ec016.owner_token',true)",sql)
        self.assertIn('FORCE ROW LEVEL SECURITY',sql);self.assertIn('NOBYPASSRLS',sql)

    def test_precise_error_categories_and_eleven_cases(self):
        tree=ast.parse((ROOT/'runner/integration_suite.py').read_text())
        methods=[n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')]
        self.assertEqual(len(methods),11)
        text=(ROOT/'runner/integration_suite.py').read_text()
        for code in ('23514','23505','23502','42P10','42501','P0001'):self.assertIn(repr(code),text)
        self.assertNotIn('with self.assertRaises(APIError)',text.replace('with self.assertRaises(APIError) as caught:',''))
        self.assertIn('policy.require_error_code(caught.exception,code,category)',text);self.assertIn('caught.exception.sqlstate',text)

    def test_mutation_marker_and_transport_safety(self):
        text=(ROOT/'runner/lab_guard.py').read_text()
        self.assertIn('trust_env=False',text);self.assertIn('follow_redirects=False',text)
        self.assertLess(text.index('policy.validate_marker_payload({'),text.index('response=self.inner.handle_request(request)'))
        self.assertIn('runtime_context()  # Context is mandatory for every request.',text)

    def test_negative_errors_do_not_accept_network_or_wrong_sqlstate(self):
        class SQLFailure(Exception):
            def __init__(self,code):self.code=code
        for code in ('23505','23514','42501'):
            policy.require_error_code(SQLFailure(code),code)
            for failure in (ConnectionError('synthetic refusal'),SQLFailure('08006'),SQLFailure('42P01')):
                with self.assertRaises(AssertionError):policy.require_error_code(failure,code)

    def test_rls_and_permission_categories_are_distinct(self):
        class Failure:
            code='42501'
            def __init__(self,message):self.message=message
        policy.require_error_code(Failure('new row violates row-level security policy'),'42501','rls')
        policy.require_error_code(Failure('permission denied for table datos_comex'),'42501','permission')
        for text in ('connection refused','permission denied for table datos_comex','unknown infrastructure failure'):
            with self.assertRaises(AssertionError):policy.require_error_code(Failure(text),'42501','rls')

    def test_robot_lock_unchanged(self):
        with self.assertRaises(RuntimeError):ica_common.ensure_writes_verified()
        with self.assertRaises(RuntimeError):ica_common.persist(None,'datos_comex',[{'fecha':'2010-01-01'}],('fecha',))


if __name__=='__main__':unittest.main()
