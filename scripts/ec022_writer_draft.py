"""Experimental EC-022 batch writer, disabled by default; not production ready.

The input must already have been parsed and economically validated. This tool
only verifies its source file hash and writes one atomic batch via the database
idempotency function; it cannot approve or publish observations.
"""
import hashlib
import json
import os
import re
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

import psycopg

ALLOWED_HOSTS={'api.bcra.gob.ar','www.bcra.gob.ar','www.indec.gob.ar',
               'sitioanterior.indec.gob.ar','www.argentina.gob.ar','infra.datos.gob.ar'}

def prepare(manifest, source_bytes):
    if set(manifest) != {'source_url','source_sha256','retrieved_at','publication_date','observations'}:
        raise ValueError('Invalid manifest fields')
    url=manifest['source_url']
    parsed=urlsplit(url)
    if parsed.scheme!='https' or parsed.hostname not in ALLOWED_HOSTS or parsed.username or parsed.password or parsed.port not in (None,443):
        raise ValueError('Invalid official source URL')
    digest=hashlib.sha256(source_bytes).hexdigest()
    if manifest['source_sha256'] != digest: raise ValueError('Source hash mismatch')
    retrieved=datetime.fromisoformat(manifest['retrieved_at'].replace('Z','+00:00'))
    if retrieved.tzinfo is None: raise ValueError('Recovery timestamp requires timezone')
    publication=date.fromisoformat(manifest['publication_date']) if manifest['publication_date'] is not None else None
    rows=[]; keys=set()
    for row in manifest['observations']:
        if set(row) != {'series','period','value'} or not re.fullmatch(r'[a-zA-Z0-9_]{1,80}',row['series']):
            raise ValueError('Invalid observation')
        period=date.fromisoformat(row['period']); value=Decimal(row['value'])
        if not value.is_finite() or (row['series'],period) in keys: raise ValueError('Invalid or duplicate observation')
        keys.add((row['series'],period))
        rows.append((row['series'],period,digest,value,url,retrieved,publication))
    if not rows: raise ValueError('Empty batch')
    return rows

def write(conn, rows):
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("""select r.rolsuper, r.rolbypassrls,
                pg_has_role(current_user,'ec022_ingestor','MEMBER'),
                pg_has_role(current_user,'ec022_validador','MEMBER'),
                pg_has_role(current_user,'ec022_escritor_funcion','MEMBER'),
                has_table_privilege(current_user,'public.ec022_observaciones','INSERT'),
                has_table_privilege(current_user,'public.ec022_observaciones','UPDATE'),
                has_table_privilege(current_user,'public.ec022_observaciones','DELETE')
                from pg_roles r where r.rolname=current_user""")
            privileges=cur.fetchone()
            if privileges != (False,False,True,False,False,False,False,False):
                raise PermissionError('Writer role is not exclusive or has excessive privileges')
            result={'inserted':0,'no_change':0}
            for row in rows:
                cur.execute('select public.ec022_ingestar_observacion(%s,%s,%s,%s,%s,%s,%s)',row)
                status=cur.fetchone()[0]
                if status not in result: raise ValueError('Unknown database status')
                result[status]+=1
            return result

def main():
    if os.environ.get('EC022_WRITE_ENABLED')!='1':
        raise SystemExit('EC-022 writer disabled')
    if len(sys.argv)!=3: raise SystemExit('Usage: python -m scripts.ec022_writer_draft MANIFEST SOURCE_FILE')
    dsn=os.environ.get('EC022_DATABASE_URL')
    if not dsn: raise SystemExit('EC022_DATABASE_URL is required')
    rows=prepare(json.loads(Path(sys.argv[1]).read_text(encoding='utf-8')),Path(sys.argv[2]).read_bytes())
    try:
        with psycopg.connect(dsn,autocommit=True) as conn: result=write(conn,rows)
    except Exception:
        # Database diagnostics may contain credentials, values or connection data.
        raise SystemExit('EC-022 write failed; transaction rolled back') from None
    print(json.dumps(result))

if __name__=='__main__': main()
