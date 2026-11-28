"""Explicit, read-only official source probe. Never stores or publishes data."""
import hashlib
import json
from datetime import date, datetime, timedelta
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from scripts.ec022_bcra_hipotecarios import BASE, parse as parse_bcra
from scripts.ec022_bcra_uva import SOURCE as UVA_LOANS_URL, parse as parse_uva_loans
from scripts.ec022_cvs import parse as parse_cvs
from scripts.ec022_hipotecarios_readonly import BASE as API, collect, fetch, results
from scripts.ec022_indec_salarios import URL as SALARIOS_URL, parse as parse_salarios
from scripts.ec022_ipc import SOURCE as IPC_URL, parse as parse_ipc
from scripts.ec022_ripte_historico import SOURCE as RIPTE_URL, parse as parse_ripte

def download(url, maximum=100_000_000):
    request = Request(url, headers={'User-Agent':'Mozilla/5.0 EconomiaCriolla/EC022',
                                    'Referer':'https://www.bcra.gob.ar/consulta-de-series-estadisticas-en-formato-txt/'})
    with urlopen(request,timeout=90) as response:
        raw = response.read(maximum + 1)
    if not raw or len(raw) > maximum:
        raise ValueError('Invalid source size')
    return raw

def bounds(rows):
    return {'count':len(rows),'first':rows[0]['date'],'last':rows[-1]['date']}

def main():
    now = datetime.now(ZoneInfo('America/Argentina/Buenos_Aires')).date()
    summary = {}
    for series_id in (30,31):
        catalog,_ = fetch(API, {'IdVariable':series_id,'Limit':10})
        meta=results(catalog)
        if len(meta)!=1 or meta[0]['idVariable']!=series_id: raise ValueError('BCRA catalog mismatch')
        start=date.fromisoformat(meta[0]['primerFechaInformada'])
        end=min(date.fromisoformat(meta[0]['ultFechaInformada']), now-timedelta(days=1))
        data=collect(series_id,start,end)
        summary[data['series']]={**bounds(data['observations']), 'source':data['source'], 'hashes':data['sha256']}
    cvs_url=f'https://www.indec.gob.ar/ftp/cuadros/sociedad/sh_cvs_diarios_{now.year}.xls'
    data=parse_cvs(download(cvs_url),cvs_url)
    summary['CVS']={'source':cvs_url,'sha256':data['sha256'], 'series':{k:bounds(v) for k,v in data['series'].items()}}
    for key,url,parser in [('salarios',SALARIOS_URL,parse_salarios),('ipc',IPC_URL,parse_ipc),('ripte',RIPTE_URL,parse_ripte)]:
        data=parser(download(url)); summary[key]={**bounds(data['observations']),'source':url,'sha256':data['sha256']}
    for filename in ('tas2_ser.txt','din1_ser.txt'):
        data=parse_bcra(download(BASE+filename),filename)
        summary[filename]={'source':data['source'],'sha256':data['sha256'],
                           'series':{k:{**bounds(v['observations']),'missing_months':v['missing_months']} for k,v in data['series'].items()}}
    uva_loans=parse_uva_loans(download(UVA_LOANS_URL))
    summary['hipotecarios_uva']={**bounds(uva_loans['observations']),'source':UVA_LOANS_URL,
                                'sha256':uva_loans['sha256'],'scope':uva_loans['scope']}
    print(json.dumps({'retrieved':now.isoformat(),'writes_to_supabase':False,'results':summary},ensure_ascii=False))

if __name__=='__main__': main()
