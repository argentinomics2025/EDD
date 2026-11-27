"""EC-022 official BCRA historical probe. No DB access."""
import argparse
import hashlib
import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

BASE = "https://api.bcra.gob.ar/estadisticas/v4.0/Monetarias"
SERIES = {30: ("CER", "coeficiente"), 31: ("UVA", "ARS/UVA")}

def fetch(url, params):
    with urlopen(Request(url+"?"+urlencode(params), headers={"User-Agent":"EconomiaCriolla-EC022/1"}), timeout=30) as r:
        raw = r.read(4000001)
    if len(raw)>4000000:
        raise ValueError("Response too large")
    return json.loads(raw, parse_float=Decimal), hashlib.sha256(raw).hexdigest()

def results(payload):
    if payload.get("status") not in (200,"200") or not isinstance(payload.get("results"),list):
        raise ValueError("Invalid API response")
    return payload["results"]

def collect(var_id, start, end, reader=fetch, page_size=1000):
    if var_id not in SERIES or not 1<=page_size<=1000 or not start<=end<=datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date():
        raise ValueError("Invalid request")
    name, unit=SERIES[var_id]
    catalog, digest=reader(BASE, {"IdVariable":var_id,"Limit":10})
    entries=results(catalog)
    if len(entries)!=1 or entries[0].get("idVariable")!=var_id:
        raise ValueError("Wrong catalog identity")
    desc=entries[0].get("descripcion","").casefold()
    if not (("cer" in desc.split() or "coeficiente de estabilizaci" in desc) if var_id==30 else ("uva" in desc or "unidad de valor adquisitivo" in desc)):
        raise ValueError("Wrong description")
    hashes=[digest]
    values={}
    expected=(end-start).days+1
    for offset in range(0,expected,page_size):
        payload,digest=reader(f"{BASE}/{var_id}",{"Desde":start.isoformat(),"Hasta":end.isoformat(),"Limit":page_size,"Offset":offset})
        hashes.append(digest)
        rows=results(payload)
        if len(rows)!=1 or rows[0].get("idVariable")!=var_id:
            raise ValueError("Wrong historical identity")
        detail=rows[0].get("detalle")
        if not isinstance(detail,list) or not detail or len(detail)>page_size:
            raise ValueError("Invalid page")
        for row in detail:
            d=date.fromisoformat(row["fecha"])
            v=Decimal(str(row["valor"]))
            if d in values or not start<=d<=end or not v.is_finite() or v<=0:
                raise ValueError("Invalid observation")
            values[d]=v
        if len(values)==expected: break
        if len(detail)<page_size: raise ValueError("Incomplete history")
    if len(values)!=expected: raise ValueError("Incomplete daily coverage")
    return {"series":name,"unit":unit,"source":f"{BASE}/{var_id}","sha256":hashes,"observations":[{"date":str(d),"value":str(values[d])} for d in sorted(values)],"writes_to_supabase":False}

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--days",type=int,default=30)
    a=p.parse_args()
    if not 1<=a.days<=365: p.error("days must be 1..365")
    end=datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date()-timedelta(days=1)
    print(json.dumps([collect(i,end-timedelta(days=a.days-1),end) for i in SERIES]))
