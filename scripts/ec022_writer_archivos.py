"""Source-bound, opt-in EC-022 file ingestion. No approval or publication.

Requires existing validated catalog entries and an exclusive ingestor role.
UVA/CER BCRA API pages are not handled by this file-based writer.
"""
import argparse
import json
import os
from pathlib import Path
import psycopg

from scripts.ec022_prepare_archivos import KINDS,manifest
from scripts.ec022_writer_draft import prepare,write

def main():
    if os.environ.get('EC022_WRITE_ENABLED')!='1': raise SystemExit('EC-022 writer disabled')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind',choices=KINDS);parser.add_argument('source_file',type=Path)
    parser.add_argument('--retrieved-at',required=True,help='Actual source retrieval time with timezone')
    args=parser.parse_args()
    dsn=os.environ.get('EC022_DATABASE_URL')
    if not dsn: raise SystemExit('EC022_DATABASE_URL is required')
    raw=args.source_file.read_bytes()
    batch=manifest(args.kind,raw,args.retrieved_at)
    rows=prepare(batch,raw)
    try:
        with psycopg.connect(dsn,autocommit=True) as conn: result=write(conn,rows)
    except Exception:
        raise SystemExit('EC-022 write failed; transaction rolled back') from None
    print(json.dumps({'source_sha256':batch['source_sha256'],**result}))

if __name__=='__main__': main()
