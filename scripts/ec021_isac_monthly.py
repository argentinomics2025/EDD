"""EC-021 ISAC: official seasonally adjusted activity + original inputs, atomic INSERT-only.

Fail-closed: no database without --commit, explicit kill switch and the dedicated role.
Existing history, including revised prior editions, is never updated.
"""
import argparse
import csv
import hashlib
import io
import json
import os
import re
from datetime import date, timedelta
from decimal import Decimal
from urllib.parse import urlparse

import requests

from scripts.ec021_construction_isac_readonly_audit import SOURCE as INDEX_URL, SERIES
from scripts.ec021_isac_inputs_readonly_audit import (
    SOURCE as INPUTS_URL, FIELDS, SOURCE_COLUMNS, DB, DB_INPUTS, KEY
)

ROLE = "ec021_isac_writer"
START = date(2026, 10, 1)
ACT_COLS = ("fecha", "indice", "variacion_mensual")
INPUT_COLS = ("fecha",) + tuple(FIELDS) + tuple("var_" + f for f in FIELDS)
HEADERS = {"User-Agent": "EconomiaCriolla-ISAC/1.0"}

def dec(value):
    d=Decimal(str(value))
    if not d.is_finite() or d<=0:
        raise ValueError("ISAC data must be positive and finite")
    return d

def month_before(period):
    d=date.fromisoformat(period+"-01")
    return (d-timedelta(days=1)).replace(day=1)

def month_after(d):
    return date(d.year+int(d.month==12),d.month%12+1,1)

def fetch(url, *, params=None, limit=4_000_000, http=requests):
    if not url.startswith(("https://apis.datos.gob.ar/series/api/series",
                           "https://infra.datos.gob.ar/catalog/sspm/dataset/33/distribution/33.3/download/")):
        raise ValueError("Unexpected source host")
    r=http.get(url,params=params,headers=HEADERS,timeout=35,allow_redirects=True)
    r.raise_for_status()
    if urlparse(r.url).scheme != "https" or urlparse(r.url).hostname not in {"apis.datos.gob.ar","infra.datos.gob.ar"} or len(r.history)>2 or not r.content or len(r.content)>limit:
        raise ValueError("Source missing, redirected or oversized")
    return r.content,hashlib.sha256(r.content).hexdigest()

def parse_index(content):
    raw=json.loads(content)
    rows=raw.get("data")
    if not isinstance(rows,list) or len(rows)<24:
        raise ValueError("Unexpected ISAC adjusted index history")
    out={}
    for row in rows:
        if not isinstance(row,list) or len(row)!=2:
            raise ValueError("Unexpected index data shape")
        when=date.fromisoformat(str(row[0])[:10])
        if when in out:
            raise ValueError("Duplicate index date")
        if row[1] is not None:
            out[when]=dec(row[1])
    if len(out)<24:
        raise ValueError("Missing index history")
    return out

def parse_inputs(content):
    reader=csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    headers=reader.fieldnames or ()
    expected={"indice_tiempo"}|{SOURCE_COLUMNS.get(f,"isac_"+f) for f in FIELDS}
    if not expected.issubset(set(headers)):
        raise ValueError("Missing official ISAC inputs columns")
    out={}
    for row in reader:
        when=date.fromisoformat(row["indice_tiempo"][:10])
        if when in out:
            raise ValueError("Duplicate inputs date")
        out[when]={field:dec(row[SOURCE_COLUMNS.get(field,"isac_"+field)])
                   for field in FIELDS if row.get(SOURCE_COLUMNS.get(field,"isac_"+field))}
    if len(out)<24:
        raise ValueError("Missing inputs history")
    return out

def source_report(release_month, *, http=requests):
    if not re.fullmatch(r"20\d{2}-(0[1-9]|1[0-2])",release_month):
        raise ValueError("Invalid release month")
    target=month_before(release_month)
    index_bytes,index_sha=fetch(INDEX_URL,params={"ids":SERIES,"limit":500,"format":"json"},http=http)
    inputs_bytes,inputs_sha=fetch(INPUTS_URL,http=http)
    index,inputs=parse_index(index_bytes),parse_inputs(inputs_bytes)
    if max(index)>date.today().replace(day=1) or max(inputs)>date.today().replace(day=1):
        raise ValueError("Future official source month")
    common={d for d in index if d in inputs}
    if not common:
        raise ValueError("No overlapping official sources")
    missing=(target not in index,target not in inputs)
    if any(missing):
        if missing[0] != missing[1]:
            raise ValueError("Official sources disagree on target month")
        if max(index)>=target or max(inputs)>=target:
            raise ValueError("Missing target inside available history")
        return {"status":"awaiting_publication","period":target.isoformat(),
                "last_activity":max(index).isoformat(),"last_inputs":max(inputs).isoformat(),
                "writes_to_supabase":False}
    if target not in common:
        raise ValueError("Missing official target")
    prev=(target-timedelta(days=1)).replace(day=1)
    if prev not in index or prev not in inputs:
        raise ValueError("Previous official period missing")
    if len(inputs[target])!=len(FIELDS) or len(inputs[prev])!=len(FIELDS):
        raise ValueError("Incomplete official inputs")
    activity={"fecha":target.isoformat(),"indice":str(index[target]),
              "variacion_mensual":str((index[target]/index[prev]-1)*100)}
    input_values={"fecha":target.isoformat()}
    for f in FIELDS:
        input_values[f]=str(inputs[target][f])
        input_values["var_"+f]=str((inputs[target][f]/inputs[prev][f]-1)*100)
    history=[]
    cursor=prev
    for _ in range(9):
        if cursor not in index or cursor not in inputs or len(inputs[cursor])!=len(FIELDS):
            raise ValueError("At least nine consecutive official prior months are required")
        history.append({"fecha":cursor.isoformat(),"indice":str(index[cursor]),
                        "insumos":{f:str(inputs[cursor][f]) for f in FIELDS}})
        cursor=(cursor-timedelta(days=1)).replace(day=1)
    return {"status":"source_ready","period":target.isoformat(),"activity":activity,
            "history_to_reconcile":history,
            "inputs":input_values,"source_index_sha":index_sha,"source_inputs_sha":inputs_sha,
            "index_url":INDEX_URL,"index_series":SERIES,"inputs_url":INPUTS_URL,
            "writes_to_supabase":False}

def compare_published(actual,incoming, cols, tolerance=Decimal("0.051")):
    for key in cols:
        if key=="fecha":continue
        if actual.get(key) is None or abs(Decimal(str(actual[key]))-Decimal(str(incoming[key])))>tolerance:
            raise ValueError("Published ISAC history/source mismatch, stop instead of overwrite")
    return True

def insert_once(report, dsn):
    import psycopg
    from psycopg.types.json import Jsonb
    if report["status"]!="source_ready":
        return {"status":"awaiting_publication","applied":False,"period":report["period"]}
    target=date.fromisoformat(report["period"])
    if target<START or target>=date.today().replace(day=1):
        raise ValueError("No insertion before cutoff or for current/future months")
    with psycopg.connect(dsn,connect_timeout=12,sslmode="require") as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute("SELECT current_user")
                actor=cur.fetchone()[0]
                if actor!=ROLE:
                    raise PermissionError("ISAC requires dedicated INSERT-only login role")
                cur.execute("SELECT pg_advisory_xact_lock(2026,211)")
                fingerprints={}
                for table,cols in (("construccion_actividad",ACT_COLS),
                                   ("construccion_insumos",INPUT_COLS)):
                    cur.execute("SELECT count(*),count(DISTINCT fecha),max(fecha) FROM public."+table)
                    count,unique,last=cur.fetchone()
                    if count!=unique or not last:
                        raise ValueError("Invalid or duplicate stored ISAC history")
                    cur.execute("SELECT md5(string_agg(row_to_json(t)::text,'|' ORDER BY t.fecha)) FROM (SELECT * FROM public."+table+" ORDER BY fecha)t")
                    fingerprints[table]=(count,last,cur.fetchone()[0])
                # Do not build a new monthly rate on revised, contradictory prior months.
                history=report.get("history_to_reconcile",[])
                if len(history)!=9:
                    raise ValueError("Missing nine source historical comparisons")
                for month in history:
                    when=date.fromisoformat(month["fecha"])
                    cur.execute("SELECT indice FROM public.construccion_actividad WHERE fecha=%s",(when,))
                    stored=cur.fetchone()
                    if not stored or abs(Decimal(str(stored[0]))-Decimal(month["indice"]))>Decimal("0.051"):
                        raise ValueError("Adjusted ISAC recent history revised: manual edition review")
                    cur.execute("SELECT "+",".join(FIELDS)+" FROM public.construccion_insumos WHERE fecha=%s",(when,))
                    stored=cur.fetchone()
                    if not stored:
                        raise ValueError("Missing inputs recent history")
                    for f,value in zip(FIELDS,stored):
                        if value is None or abs(Decimal(str(value))-Decimal(month["insumos"][f]))>Decimal("0.051"):
                            raise ValueError("Input "+f+" recent history revised: manual edition review")
                exists=[]
                for table,cols,payload in (
                    ("construccion_actividad",ACT_COLS,report["activity"]),
                    ("construccion_insumos",INPUT_COLS,report["inputs"])
                ):
                    cur.execute("SELECT "+",".join(cols)+" FROM public."+table+" WHERE fecha=%s",(target,))
                    record=cur.fetchone()
                    if record:
                        compare_published(dict(zip(cols,record)),payload,cols)
                    exists.append(record is not None)
                if any(exists):
                    if not all(exists):
                        raise ValueError("Only one ISAC target table has existing month")
                    cur.execute("SELECT index_sha256,inputs_sha256 FROM ec021_audit.isac_source_editions WHERE period=%s",(target,))
                    provenance=cur.fetchone()
                    if provenance is None:
                        raise ValueError("Existing period has no audited source edition")
                    if provenance!=(report["source_index_sha"],report["source_inputs_sha"]):
                        raise ValueError("Official source edition changed: review only")
                    return {"status":"no_change","period":report["period"],"applied":False,"db_role":actor}
                for table in ("construccion_actividad","construccion_insumos"):
                    count,last,digest=fingerprints[table]
                    if month_after(last)!=target or not digest:
                        raise ValueError("ISAC gap or missing historical backup")
                cur.execute("SELECT 1 FROM ec021_audit.isac_source_editions WHERE period=%s",(target,))
                if cur.fetchone():
                    raise ValueError("Edition ledger exists without target row")
                cur.execute("""INSERT INTO ec021_audit.isac_source_editions
                    (period,index_sha256,inputs_sha256,index_url,index_series,inputs_url,previous_activity_hash,previous_inputs_hash,source_record)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (target,report["source_index_sha"],report["source_inputs_sha"],
                     report["index_url"],report["index_series"],report["inputs_url"],
                     fingerprints["construccion_actividad"][2],fingerprints["construccion_insumos"][2],Jsonb(report)))
                for table,cols,payload in (
                    ("construccion_actividad",ACT_COLS,report["activity"]),
                    ("construccion_insumos",INPUT_COLS,report["inputs"])
                ):
                    cur.execute("INSERT INTO public."+table+" ("+",".join(cols)+") VALUES ("+",".join(["%s"]*len(cols))+")",
                                (target,*(Decimal(payload[c]) for c in cols[1:])))
                    count,last,digest=fingerprints[table]
                    cur.execute("SELECT count(*),count(DISTINCT fecha),max(fecha) FROM public."+table)
                    n,u,latest=cur.fetchone()
                    if n!=count+1 or n!=u or latest!=target:
                        raise ValueError("ISAC insert count mismatch; rolling back")
                    cur.execute("SELECT md5(string_agg(row_to_json(t)::text,'|' ORDER BY t.fecha)) FROM (SELECT * FROM public."+table+" WHERE fecha<%s ORDER BY fecha)t",(target,))
                    if cur.fetchone()[0]!=digest:
                        raise ValueError("ISAC historic fingerprint changed; rolling back")
                return {"status":"inserted","period":report["period"],"applied":True,
                        "new_count":fingerprints["construccion_actividad"][0]+1,
                        "db_role":actor}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--release-month",required=True)
    p.add_argument("--commit",action="store_true")
    args=p.parse_args()
    report=source_report(args.release_month)
    if not args.commit:
        print(json.dumps({"status":report["status"],"period":report["period"],
                          "writes_to_supabase":False,"activity_last":report.get("last_activity"),
                          "inputs_last":report.get("last_inputs")},sort_keys=True))
        return
    if os.environ.get("EC021_ISAC_WRITES_ENABLED")!="true":
        raise PermissionError("ISAC writes disabled by kill switch")
    dsn=os.environ.get("EC021_ISAC_DB_DSN")
    if not dsn:
        raise PermissionError("Dedicated EC021_ISAC_DB_DSN missing")
    print(json.dumps(insert_once(report,dsn),sort_keys=True))

if __name__=="__main__":
    main()
