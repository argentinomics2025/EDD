"""Build a source-bound UVA manifest; this module does not access a database."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.ec022_bcra_uva import parse

AMOUNT_SERIES='bcra_hipotecarios_uva_monto_miles_ars'
RATE_SERIES='bcra_hipotecarios_uva_tna_porcentaje'

def prepare_manifest(raw, retrieved_at):
    timestamp=datetime.fromisoformat(retrieved_at.replace('Z','+00:00'))
    if timestamp.tzinfo is None: raise ValueError('retrieved_at requires a timezone')
    if timestamp > datetime.now(timezone.utc): raise ValueError('retrieved_at cannot be in the future')
    parsed=parse(raw)
    if parsed['sha256'] != hashlib.sha256(raw).hexdigest(): raise ValueError('source hash mismatch')
    observations=[]
    for row in parsed['observations']:
        observations.append({'series':AMOUNT_SERIES,'period':row['date'],'value':row['amount_thousand_ars']})
        if not row['zero_amount_rate_not_interpreted']:
            observations.append({'series':RATE_SERIES,'period':row['date'],'value':row['annual_nominal_rate_percent']})
    return {'source_url':parsed['source'],'source_sha256':parsed['sha256'],
            'retrieved_at':retrieved_at,'publication_date':None,'observations':observations}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_file',type=Path)
    parser.add_argument('--retrieved-at',required=True,help='Actual source retrieval time, ISO 8601 with timezone')
    args=parser.parse_args()
    print(json.dumps(prepare_manifest(args.source_file.read_bytes(),args.retrieved_at),ensure_ascii=False))

if __name__=='__main__': main()
