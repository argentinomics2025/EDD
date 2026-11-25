"""EC-021: audit DollarApi USD/ARS quotes against EC dashboard, with no writes.

DolarApi aggregates third parties. Citation does not certify redistribution rights.
No automatic correction of earlier observations or ticker rename.
"""
import json
from datetime import datetime,timezone
from decimal import Decimal, InvalidOperation
import requests

SOURCE="https://dolarapi.com/v1/dolares"
DB="https://fvyzacodrrmlxgzhneyt.supabase.co/rest/v1/economic_indicators"
KEY="sb_publishable_32r2WZE28EI-O4aIP1D4Mw_fnwZ826j"
HOUSES={"oficial":"dolar-oficial","blue":"dolar-blue","bolsa":"dolar-mep",
        "contadoconliqui":"dolar-ccl","mayorista":"dolar-mayorista",
        "cripto":"dolar-cripto","tarjeta":"dolar-tarjeta"}

def read_json(url,*,http=requests,params=None,headers=None):
    resp=http.get(url,params=params,headers=headers,timeout=20)
    resp.raise_for_status()
    if len(resp.content)>300000:raise ValueError("Large unexpected exchange payload")
    return resp.json()

def amount(raw):
    if raw is None or isinstance(raw,bool):return None
    try: d=Decimal(str(raw))
    except (TypeError,InvalidOperation) as ex:raise ValueError("Invalid exchange price") from ex
    if not d.is_finite() or not 1<=d<=100000:
        raise ValueError("Exchange price out of range")
    return d

def assess(source,stored):
    if not isinstance(source,list) or not 7<=len(source)<=15:raise ValueError("Untrusted DollarApi response")
    if not isinstance(stored,list) or not 7<=len(stored)<=15:raise ValueError("Untrusted dashboard snapshot")
    market={}
    for x in source:
        house=x.get("casa")
        if house not in HOUSES:continue
        ticker=HOUSES[house]
        if ticker in market:raise ValueError("Duplicate DollarApi currency ticker")
        sell=amount(x.get("venta"))
        if sell is None:raise ValueError("Missing selling price")
        buy=amount(x.get("compra"))
        when=x.get("fechaActualizacion")
        dt=datetime.fromisoformat(str(when).replace("Z","+00:00"))
        if dt.tzinfo is None:raise ValueError("Currency quote requires timezone")
        market[ticker]={"sell":sell,"buy":buy,"date":dt.date().isoformat()}
    if set(market)!=set(HOUSES.values()):raise ValueError("Expected seven canonical exchange tickers")
    seen=set()
    report={}
    orphan=[]
    for row in stored:
        ticker=row.get("id")
        if ticker not in market:
            if isinstance(ticker,str) and ticker.startswith("dolar-"):orphan.append(ticker)
            continue
        if ticker in seen:raise ValueError("Duplicate dashboard exchange ticker")
        seen.add(ticker)
        actual_sell=amount(row.get("sell_value"))
        actual_buy=amount(row.get("buy_value"))
        expected=market[ticker]
        same=(actual_sell==expected["sell"] and actual_buy==expected["buy"])
        report[ticker]={"status":"matched" if same else "dashboard_differs_from_current_quote",
                        "source_date":expected["date"],
                        "dashboard_last_updated":str(row.get("last_updated"))}
    if seen!=set(market):raise ValueError("Canonical ticker missing in dashboard")
    return {"mode":"read_only_audit","source":SOURCE,"source_credits":"DolarApi; DolarHoy/Ámbito",
            "quotes":report,"stale_extra_tickers":sorted(orphan),
            "writes_to_supabase":False,"updates_historical_quotes":False}

def run(*,http=requests):
    source=read_json(SOURCE,http=http)
    db=read_json(DB,http=http,params={"select":"id,buy_value,sell_value,last_updated",
                                      "id":"like.dolar-*","limit":"20"},
                 headers={"apikey":KEY,"Accept":"application/json"})
    return assess(source,db)

if __name__=="__main__":
    print(json.dumps(run(),sort_keys=True,ensure_ascii=False))
