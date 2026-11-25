"""EC-021 Construcción ISAC: official API vs stored index, audit only.

Historical values may be revised and seasonally adjusted; never overwrite
without documented matching series methodology and edition.
"""
import json
from datetime import date
from decimal import Decimal
import requests

SOURCE="https://apis.datos.gob.ar/series/api/series"
SERIES="33.2_ISAC_NIVELRAL_0_M_18_63"
DB="https://fvyzacodrrmlxgzhneyt.supabase.co/rest/v1/construccion_actividad"
KEY="sb_publishable_32r2WZE28EI-O4aIP1D4Mw_fnwZ826j"

def read(url,*,http=requests,params=None,headers=None):
    r=http.get(url,params=params,headers=headers,timeout=25)
    r.raise_for_status()
    if len(r.content)>2_000_000:raise ValueError("Unexpected oversized construction response")
    return r.json()

def assess(source,stored):
    rows=source.get("data") if isinstance(source,dict) else None
    if not isinstance(rows,list) or len(rows)<12:raise ValueError("Missing ISAC source observations")
    official={}
    for row in rows:
        if not isinstance(row,list) or len(row)!=2:raise ValueError("Invalid official ISAC row")
        when=date.fromisoformat(str(row[0])[:10]).isoformat()
        value=row[1]
        if value is None:continue
        n=Decimal(str(value))
        if not n.is_finite() or n<=0:raise ValueError("Invalid ISAC index")
        if when in official:raise ValueError("Repeated official ISAC date")
        official[when]=n
    if len(official)<12:raise ValueError("Insufficient ISAC source index values")
    if not isinstance(stored,list) or len(stored)<3:raise ValueError("No DB overlap")
    seen=set()
    overlap=[]
    for row in stored:
        when=str(row["fecha"])
        if when in seen:raise ValueError("Duplicate stored ISAC date")
        seen.add(when)
        if when in official:
            old=Decimal(str(row["indice"]))
            if not old.is_finite():raise ValueError("Invalid stored ISAC")
            overlap.append({"month":when,
                            "status":"matched" if abs(old-official[when])<=Decimal("0.05") else "index_differs_review_series_definition",
                            "absolute_difference":str(abs(old-official[when]))})
    if len(overlap)<3:raise ValueError("Insufficient matching periods")
    return {"mode":"read_only_audit","source":SOURCE,"series_id":SERIES,
            "latest_official_month":max(official),
            "latest_stored_month":max(seen),
            "overlap":overlap[:10],
            "writes_to_supabase":False,"revises_historical_values":False}

def run(*,http=requests):
    source=read(SOURCE,http=http,params={"ids":SERIES,"limit":500,"format":"json"})
    stored=read(DB,http=http,params={"select":"fecha,indice","order":"fecha.desc","limit":"30"},
                headers={"apikey":KEY,"Accept":"application/json"})
    return assess(source,stored)

if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=False,sort_keys=True))
