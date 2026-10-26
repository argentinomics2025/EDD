"""EC016 fixed disposable targets. This module does not connect on import."""
import base64
import hashlib
import hmac
import json
import os
import time
from urllib.parse import urlsplit
from pathlib import Path
import re
import socket
from . import policy

API_URL = 'http://172.30.216.3:3000'
DB_HOST = '172.30.216.2'
DB_NAME = 'ec016_disposable'
MARKER = 'EC016_DISPOSABLE_SYNTHETIC_ONLY'
# PUBLIC synthetic fixtures, valid only inside the isolated disposable lab.
JWT_KEY = 'EC016_PUBLIC_SYNTHETIC_JWT_KEY_NOT_A_REAL_SECRET_0123456789'
TABLES = ('datos_comex', 'socios_comerciales', 'comex_rubros')
FORBIDDEN_BINDINGS = {'SUPABASE_URL','SUPABASE_KEY','SUPABASE_SERVICE_ROLE_KEY','DATABASE_URL',
                      'PGHOST','PGPORT','PGUSER','PGPASSWORD','PGDATABASE','PGSERVICE',
                      'PGSERVICEFILE','PGPASSFILE','PGRST_DB_URI'}


def assert_opt_in(environment=None):
    environment = os.environ if environment is None else environment
    if environment.get('EC016_EXECUTE_DISPOSABLE') != 'YES_SYNTHETIC_ONLY':
        raise RuntimeError('Disposable integration execution has not been opted in')
    if (FORBIDDEN_BINDINGS & {name.upper() for name in environment}
            or any(name.upper().startswith(('PG','SUPABASE_')) for name in environment)):
        raise RuntimeError('Unexpected connection binding present; refusing execution')


def runtime_context():
    assert_opt_in()
    if os.environ.get('EC016_ACTIONS_SERVICES') is not None:
        from ..services import runtime_context as services_context
        return services_context()
    root=Path('/run/ec016')
    if not Path('/.dockerenv').is_file():raise RuntimeError('Must run inside the attested container')
    manifest=policy.validate_manifest(json.loads((root/'manifest.json').read_text()))
    if any(p.is_symlink() for p in root.iterdir()):raise RuntimeError('Symlinked context rejected')
    if os.environ.get('EC016_RUN_ID')!=manifest['run_id'] or os.environ.get('EC016_CONTAINER_ROLE')!='ec016-tests':
        raise RuntimeError('Run/role mismatch')
    if os.readlink('/proc/self/ns/net')==manifest['host_netns']:raise RuntimeError('Host network namespace forbidden')
    if socket.gethostname()!=manifest['project']+'-ec016-tests':raise RuntimeError('Unexpected container hostname')
    mounts=Path('/proc/self/mountinfo').read_text().splitlines()
    if not any(line.split()[4]=='/run/ec016' and 'ro' in line.split()[5].split(',') for line in mounts):
        raise RuntimeError('Read-only context mount is required')
    local=Path('/proc/net/fib_trie').read_text()
    if not re.search(r'172\.30\.216\.4\s*\n\s*[/]32 host LOCAL',local):raise RuntimeError('Wrong private interface')
    routes=Path('/proc/net/route').read_text().splitlines()[1:]
    if any(len(line.split())>1 and line.split()[1]=='00000000' for line in routes):
        raise RuntimeError('Default route is forbidden')
    attestation=json.loads((root/'preflight.json').read_text())
    expected={'scope':policy.SCOPE,'run_id':manifest['run_id'],'owner_token':manifest['owner_token']}
    policy.validate_marker_payload({k:attestation.get(k) for k in expected},manifest)
    if not manifest.get('engine_id') or attestation.get('engine_id')!=manifest['engine_id']:
        raise RuntimeError('Engine attestation mismatch')
    if (root/'preflight.ok').read_text().strip()!=manifest['run_id']+':'+manifest['owner_token']:
        raise RuntimeError('Missing preflight approval')
    if manifest.get('github_context') is not None:
        if (root/'security.ok').read_text().strip()!=manifest['run_id']+':'+manifest['owner_token']:
            raise RuntimeError('Missing image security clearance')
        proof=json.loads((root/'network-guard.json').read_text())
        if (proof.get('run_id')!=manifest['run_id'] or proof.get('owner_token')!=manifest['owner_token']
                or proof.get('policy')!='bridge-default-deny-v1'):
            raise RuntimeError('Hosted network guard missing or cross-run')
        if (root/'network-guard.ok').read_text().strip()!=manifest['run_id']+':'+manifest['owner_token']+':bridge-default-deny-v1':
            raise RuntimeError('Hosted bridge approval missing')
        ipv6=Path('/proc/net/if_inet6')
        if ipv6.exists() and any(line.split()[-1]!='lo' for line in ipv6.read_text().splitlines()):
            raise RuntimeError('Unexpected IPv6 network interface')
    return manifest


def validate_http_target(url):
    allowed_host='postgrest' if os.environ.get('EC016_ACTIONS_SERVICES') else '172.30.216.3'
    parsed = urlsplit(str(url))
    if (parsed.scheme != 'http' or parsed.hostname != allowed_host or parsed.port != 3000
            or parsed.username or parsed.password or parsed.fragment
            or parsed.path.strip('/') not in (*TABLES, 'ec016_metadata', 'no_unique_fixture')):
        raise ValueError('Only the fixed EC016 disposable API resources are allowed')


def db_parameters():
    # No input URL and no environment-derived DSN or credentials.
    host='postgres' if os.environ.get('EC016_ACTIONS_SERVICES') else DB_HOST
    return {'host':host, **({} if host=='postgres' else {'hostaddr':DB_HOST}), 'port':5432, 'dbname':DB_NAME,
            'user':'ec016_admin', 'password':'EC016_SYNTHETIC_ADMIN_ONLY',
            'connect_timeout':3, 'application_name':'ec016-disposable-tests'}


def validate_marker(database, user, marker, manifest):
    if (database,user)!=(DB_NAME,'ec016_admin'):
        raise RuntimeError('Database identity mismatch')
    policy.validate_marker_payload(marker,manifest)


def jwt(role='ec016_writer', scope='synthetic'):
    if role not in ('ec016_writer','ec016_reader'):
        raise ValueError('Unknown synthetic role')
    def encode(obj):
        raw=json.dumps(obj,sort_keys=True,separators=(',',':')).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b'=')
    header=encode({'alg':'HS256','typ':'JWT'})
    manifest=runtime_context()
    body=encode({'role':role,'ec016_scope':scope,'ec016_run':manifest['run_id'],
                 'ec016_owner':manifest['owner_token'],'exp':int(time.time())+900})
    signature=base64.urlsafe_b64encode(hmac.new(JWT_KEY.encode(),header+b'.'+body,hashlib.sha256).digest()).rstrip(b'=')
    return (header+b'.'+body+b'.'+signature).decode()


def admin_connection():
    manifest=runtime_context()
    import psycopg
    connection=psycopg.connect(**db_parameters(),autocommit=True)
    try:
        row=connection.execute("SELECT current_database(),current_user,(SELECT jsonb_build_object('scope',value,'run_id',run_id,'owner_token',owner_token) FROM api.ec016_metadata WHERE name='scope')").fetchone()
        validate_marker(*row,manifest)
    except Exception:
        connection.close()
        raise
    return connection


def api_client(role='ec016_writer', scope='synthetic', anonymous=False):
    manifest=runtime_context()
    import httpx
    from postgrest import SyncPostgrestClient
    class GuardedTransport(httpx.BaseTransport):
        def __init__(self):
            self.inner=httpx.HTTPTransport(retries=0,trust_env=False)
            self.drop_next_post_response=False
        def handle_request(self,request):
            validate_http_target(request.url)
            runtime_context()  # Context is mandatory for every request.
            if request.method not in ('GET','HEAD'):
                marker_request=httpx.Request('GET',api_url+'/ec016_metadata?name=eq.scope&select=value,run_id,owner_token',
                                            headers={'Accept-Profile':'api'})
                marker_response=self.inner.handle_request(marker_request)
                try:
                    marker_response.request=marker_request
                    marker_response.read(); marker_response.raise_for_status()
                    rows=marker_response.json()
                    if len(rows)!=1:raise RuntimeError('API marker absent/ambiguous')
                    policy.validate_marker_payload({'scope':rows[0]['value'],'run_id':rows[0]['run_id'],
                                                     'owner_token':rows[0]['owner_token']},manifest)
                finally:marker_response.close()
            response=self.inner.handle_request(request)
            if self.drop_next_post_response and request.method=='POST' and response.status_code<300:
                self.drop_next_post_response=False
                response.read()  # Successful PostgREST response: transaction has completed.
                response.close()
                raise httpx.ReadTimeout('Synthetic lost response after commit',request=request)
            return response
        def close(self):self.inner.close()
    headers={'Accept-Profile':'api','Content-Profile':'api'}
    if not anonymous:headers['Authorization']='Bearer '+jwt(role,scope)
    api_url='http://postgrest:3000' if os.environ.get('EC016_ACTIONS_SERVICES') else API_URL
    client=SyncPostgrestClient(api_url,schema='api',headers=headers)
    # Replace the default session BEFORE the first request: no proxy inheritance,
    # redirects or general outbound transport. SDK API must be verified at first run.
    client.session.close()
    transport=GuardedTransport()
    client.session=httpx.Client(base_url=api_url,headers=headers,transport=transport,
                               timeout=5,trust_env=False,follow_redirects=False)
    return client,transport
