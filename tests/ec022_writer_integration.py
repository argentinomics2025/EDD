"""Only run on a newly created disposable local database after SQL tests."""
import hashlib
import os
from datetime import date
import psycopg
from psycopg.conninfo import conninfo_to_dict
from scripts.ec022_writer_draft import prepare,write

if os.environ.get('EC022_DISPOSABLE_TEST_CLUSTER') != 'yes':
    raise SystemExit('Refusing without explicit disposable-cluster flag')
dsn=os.environ.get('EC022_TEST_DSN','')
parts=conninfo_to_dict(dsn)
if parts.get('host') not in ('localhost','127.0.0.1','::1') or not parts.get('port'):
    raise SystemExit('Refusing non-local database')
raw=b'fixture'
manifest={'source_url':'https://www.indec.gob.ar/test','source_sha256':hashlib.sha256(raw).hexdigest(),
          'retrieved_at':'2026-11-27T10:00:00Z','publication_date':None,
          'observations':[{'series':'test','period':'2021-01-01','value':'3'}]}
rows=prepare(manifest,raw)
with psycopg.connect(dsn,autocommit=True) as conn:
    conn.execute('set role ec022_ingestor')
    assert write(conn,rows)=={'inserted':1,'no_change':0}
    assert write(conn,rows)=={'inserted':0,'no_change':1}
    changed=list(rows[0]);changed[3]=4
    fresh=list(rows[0]);fresh[1]=date(2021,2,1)
    try: write(conn,[fresh,tuple(changed)])
    except psycopg.errors.UniqueViolation: pass
    else: raise AssertionError('Contradictory content accepted')
    assert conn.execute("select count(*) from public.ec022_observaciones where periodo='2021-02-01'").fetchone()[0]==0
print('writer insert, no_change, conflict and batch rollback passed')
