"""Write source-bound BCRA UVA observations; disabled until explicitly enabled.

This command cannot approve observations and requires existing series catalog
entries plus an exclusive EC-022 database identity. It is not production-ready
until deployed, roles provisioned, and end-to-end validation completed.
"""
import argparse
import json
import os
from pathlib import Path
import psycopg

from scripts.ec022_prepare_uva import prepare_manifest
from scripts.ec022_writer_draft import prepare,write

def main():
    if os.environ.get('EC022_WRITE_ENABLED') != '1':
        raise SystemExit('EC-022 writer disabled')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_file',type=Path)
    parser.add_argument('--retrieved-at',required=True,help='Actual source retrieval time, ISO 8601 with timezone')
    args=parser.parse_args()
    dsn=os.environ.get('EC022_DATABASE_URL')
    if not dsn: raise SystemExit('EC022_DATABASE_URL is required')
    raw=args.source_file.read_bytes()
    manifest=prepare_manifest(raw,args.retrieved_at)
    rows=prepare(manifest,raw)
    try:
        with psycopg.connect(dsn,autocommit=True) as conn:
            result=write(conn,rows)
    except Exception:
        raise SystemExit('EC-022 write failed; transaction rolled back') from None
    print(json.dumps({'source_sha256':manifest['source_sha256'],**result}))

if __name__=='__main__': main()
