"""Derive ingestion manifests from the previously recovered official files.

No database access. Each source stays a separate edition and each value is
derived by a specific fail-closed parser. The supplied retrieval time must be
the real time the source was retrieved, not the time this file is processed.
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.ec022_bcra_hipotecarios import parse as parse_bcra
from scripts.ec022_cvs import parse as parse_cvs
from scripts.ec022_indec_historicos import parse_cvs as parse_cvs_hist, parse_salarios as parse_sal_hist
from scripts.ec022_indec_salarios import parse as parse_salarios
from scripts.ec022_ipc import parse as parse_ipc
from scripts.ec022_prepare_uva import prepare_manifest as parse_uva
from scripts.ec022_ripte_historico import parse as parse_ripte_csv
from scripts.ec022_ripte_pdf import parse as parse_ripte_pdf

RIPTE_PDF='https://www.argentina.gob.ar/sites/default/files/ripte_septiembre_2026-mdch.pdf'
CVS_2026='https://www.indec.gob.ar/ftp/cuadros/sociedad/sh_cvs_diarios_2026.xls'
KINDS=('bcra_uva','bcra_rates','bcra_balances','cvs_2026','cvs_2012',
       'salarios_actual','salarios_2012','ipc','ripte_csv','ripte_pdf')

def manifest(kind,raw,retrieved_at):
    parsed_time=datetime.fromisoformat(retrieved_at.replace('Z','+00:00'))
    if parsed_time.tzinfo is None: raise ValueError('retrieval timestamp requires timezone')
    if parsed_time > datetime.now(timezone.utc): raise ValueError('retrieval timestamp cannot be in the future')
    if kind=='bcra_uva': return parse_uva(raw,retrieved_at)
    parsers={'bcra_rates':lambda:parse_bcra(raw,'tas2_ser.txt'),
             'bcra_balances':lambda:parse_bcra(raw,'din1_ser.txt'),
             'cvs_2026':lambda:parse_cvs(raw,CVS_2026),
             'cvs_2012':lambda:parse_cvs_hist(raw),
             'salarios_actual':lambda:parse_salarios(raw),
             'salarios_2012':lambda:parse_sal_hist(raw),
             'ipc':lambda:parse_ipc(raw),
             'ripte_csv':lambda:parse_ripte_csv(raw),
             'ripte_pdf':lambda:parse_ripte_pdf(raw,RIPTE_PDF)}
    if kind not in parsers: raise ValueError('unsupported source')
    data=parsers[kind]()
    digest=hashlib.sha256(raw).hexdigest()
    if data['sha256']!=digest: raise ValueError('source hash mismatch')
    observations=[]
    def add(series,row,value):
        if value is not None: observations.append({'series':series,'period':row['date'],'value':str(value)})
    if kind in ('bcra_rates','bcra_balances'):
        for name,series in data['series'].items():
            for row in series['observations']: add('bcra_'+name,row,row['value'])
    elif kind=='cvs_2026':
        for name,rows in data['series'].items():
            for row in rows: add('indec_'+name+'_base_2016',row,row['value'])
    elif kind=='ipc':
        for row in data['observations']:
            add('indec_ipc_nacional_nivel',row,row['index'])
            add('indec_ipc_nacional_variacion_mensual',row,row['monthly_percent'])
    elif kind=='ripte_pdf':
        for row in data['observations']:
            add('ripte_nominal',row,row['value'])
            add('ripte_variacion_mensual_publicada',row,row['monthly_percent'])
    else:
        names={'cvs_2012':'indec_cvs_base_2012', 'salarios_actual':'indec_salarios_total_base_2016',
               'salarios_2012':'indec_salarios_nivel_general_base_2012','ripte_csv':'ripte_nominal'}
        for row in data['observations']: add(names[kind],row,row['value'])
    if not observations: raise ValueError('no observations')
    return {'source_url':data['source'],'source_sha256':digest,'retrieved_at':retrieved_at,
            'publication_date':None,'observations':observations}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('kind',choices=KINDS);p.add_argument('source_file',type=Path)
    p.add_argument('--retrieved-at',required=True,help='Actual retrieval time with timezone')
    a=p.parse_args()
    print(json.dumps(manifest(a.kind,a.source_file.read_bytes(),a.retrieved_at),ensure_ascii=False))

if __name__=='__main__': main()
