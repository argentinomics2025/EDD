"""EC-021 BCRA: compare official v4 catalog against published Supabase snapshot.

Strictly read-only; this is NOT the legacy Google Apps Script writer.
Never publish source changes; detect drift and report it for review.
"""
import json
from datetime import date
from decimal import Decimal, InvalidOperation
import requests

API="https://api.bcra.gob.ar/estadisticas/v4.0/Monetarias"
ENDPOINT="https://fvyzacodrrmlxgzhneyt.supabase.co/rest/v1/bcra_data"
PUBLIC_KEY="sb_publishable_32r2WZE28EI-O4aIP1D4Mw_fnwZ826j"
IDS={1,7,15,16,31}
LIMIT=1500

def get_json(url,*,http=requests,params=None,headers=None):
    r=http.get(url,params=params,headers=headers,timeout=25)
    r.raise_for_status()
    if len(r.content)>3_000_000:
        raise RuntimeError("Unexpected oversized BCRA/API payload")
    return r.json()

def compare(catalog,stored,*,today=None):
    if not isinstance(catalog,dict) or catalog.get("status") not in (200,"200"):
        raise RuntimeError("Official BCRA API status invalid")
    rows=catalog.get("results")
    if not isinstance(rows,list) or not 20<=len(rows)<=LIMIT:
        raise RuntimeError("Unexpected BCRA catalog length")
    official={}
    for row in rows:
        if not isinstance(row,dict):raise RuntimeError("Untrusted BCRA row")
        i=row.get("idVariable")
        if i not in IDS:continue
        if i in official:raise RuntimeError("Duplicate BCRA variable")
        d=date.fromisoformat(str(row.get("ultFechaInformada")))
        val=Decimal(str(row.get("ultValorInformado")))
        if not val.is_finite() or val<=0:
            raise RuntimeError("Bad BCRA numeric value")
        official[i]={"date":d.isoformat(),"value":val}
    if len(official)!=len(IDS):
        raise RuntimeError("Missing official BCRA variable")
    if not isinstance(stored,list) or len(stored)!=len(IDS):
        raise RuntimeError("Wrong Supabase BCRA snapshot")
    today=today or date.today()
    output={}
    seen=set()
    for row in stored:
        i=row.get("id_variable")
        if i not in IDS or i in seen:raise RuntimeError("Unknown or duplicate stored ID")
        seen.add(i)
        old=date.fromisoformat(str(row["fecha"]))
        latest=date.fromisoformat(official[i]["date"])
        if old>today or latest>today:raise RuntimeError("Future BCRA date")
        stored_val=Decimal(str(row["valor"]))
        if not stored_val.is_finite():raise RuntimeError("Nonfinite stored value")
        if old>latest:state="stored_ahead_of_official"
        elif old<latest:state="source_ahead"
        elif stored_val!=official[i]["value"]:state="same_date_value_mismatch"
        else:state="matched"
        output[str(i)]={"status":state,"official_date":latest.isoformat(),"stored_date":old.isoformat()}
    return {"mode":"read_only_audit","source":API,"variables":output,
            "writes_to_supabase":False,"updates_histories":False}

def run(*,http=requests):
    c=get_json(API,http=http,params={"limit":LIMIT})
    s=get_json(ENDPOINT,http=http,params={"select":"id_variable,fecha,valor","order":"id_variable.asc","limit":"10"},
             headers={"apikey":PUBLIC_KEY,"Accept":"application/json"})
    return compare(c,s)

if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=False,sort_keys=True))
