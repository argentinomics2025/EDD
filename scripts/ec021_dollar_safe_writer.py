"""Safe EC-021 dollar writer. No license is assumed by code."""
import os, json, argparse
from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
import requests

SOURCE = "https://dolarapi.com/v1/dolares"
TICKERS = {"oficial":"dolar-oficial","blue":"dolar-blue","bolsa":"dolar-mep",
           "contadoconliqui":"dolar-ccl","cripto":"dolar-cripto",
           "mayorista":"dolar-mayorista","tarjeta":"dolar-tarjeta"}
AR = ZoneInfo("America/Argentina/Buenos_Aires")

def validate(payload, now=None):
    now = now or datetime.now(timezone.utc)
    if not isinstance(payload, list) or not 7 <= len(payload) <= 15:
        raise ValueError("Invalid source list")
    result = {}
    for raw in payload:
        if not isinstance(raw, dict):
            raise ValueError("Malformed record")
        key = TICKERS.get(raw.get("casa"))
        if not key:
            continue
        if key in result:
            raise ValueError("Duplicate ticker")
        dt = datetime.fromisoformat(str(raw.get("fechaActualizacion")).replace("Z","+00:00"))
        if dt.tzinfo is None:
            raise ValueError("Timezone required")
        dt = dt.astimezone(timezone.utc)
        seconds = (now - dt).total_seconds()
        if seconds < -900 or seconds > 96*3600:
            raise ValueError("Stale or future quote")
        buy = None if raw.get("compra") is None else Decimal(str(raw["compra"]))
        sell = Decimal(str(raw["venta"]))
        if not sell.is_finite() or not 1 <= sell <= 100000:
            raise ValueError("Bad sell")
        if buy is not None and (not buy.is_finite() or not 1 <= buy <= sell):
            raise ValueError("Bad buy")
        result[key] = {"buy":buy,"sell":sell,"dt":dt,"day":dt.astimezone(AR).date()}
    if set(result) != set(TICKERS.values()):
        raise ValueError("Missing canonical quotes")
    if len({v["day"] for v in result.values()}) != 1:
        raise ValueError("Mixed days")
    return result

def collect():
    r = requests.get(SOURCE, timeout=20, headers={"User-Agent":"EconomiaCriolla-EC021/1"})
    r.raise_for_status()
    if len(r.content)>300000:
        raise ValueError("Oversize source")
    return validate(r.json())

def run(check_db=False, apply=False):
    source = collect()
    day = next(iter(source.values()))["day"]
    output = {"mode":"validated_source","day":str(day),"quotes":7,"applied":False}
    if not check_db and not apply:
        return output
    if not os.getenv("EC021_DOLLAR_DB_DSN"):
        raise RuntimeError("Dedicated DSN missing")
    import psycopg
    with psycopg.connect(os.environ["EC021_DOLLAR_DB_DSN"],connect_timeout=15) as conn:
        with conn.cursor() as cur:
            cur.execute("select current_user")
            role=cur.fetchone()[0]
            if role!="ec021_dollar_writer":
                raise RuntimeError("Unexpected DB role")
            cur.execute("select id,buy_value,sell_value,last_updated from public.economic_indicators where id=any(%s) for update",(list(source),))
            board={r[0]:r[1:] for r in cur.fetchall()}
            if set(board)!=set(source):
                raise RuntimeError("Incomplete board")
            cur.execute("select ticker,precio_compra,precio_venta from public.historial_cotizaciones where ticker=any(%s) and fecha=%s",(list(source),day))
            existing={r[0]:r[1:] for r in cur.fetchall()}
            conflicts=sorted(t for t,v in source.items() if t in existing and existing[t]!=(v["buy"],v["sell"]))
            newer={t:v for t,v in source.items() if board[t][2] is None or v["dt"]>=board[t][2].astimezone(timezone.utc)}
            output.update({"role":role,"new_history":len(set(source)-set(existing)),
                           "board_updates":len(newer),"historical_conflicts":conflicts})
            if not apply:
                conn.rollback()
                output["mode"]="authenticated_read_only"
                return output
            if os.getenv("EC021_DOLLAR_WRITES_ENABLED")!="true":
                raise RuntimeError("Kill switch disabled")
            if day!=datetime.now(AR).date() or conflicts:
                raise RuntimeError("Unsafe historical or non-current quote")
            for t,v in newer.items():
                cur.execute("update public.economic_indicators set buy_value=%s,sell_value=%s,last_updated=%s where id=%s and (last_updated is null or last_updated<=%s)",
                            (v["buy"],v["sell"],v["dt"],t,v["dt"]))
                if cur.rowcount!=1:
                    raise RuntimeError("Concurrent change")
            for t,v in source.items():
                if t not in existing:
                    cur.execute("insert into public.historial_cotizaciones(fecha,ticker,precio_compra,precio_venta) values(%s,%s,%s,%s)",
                                (day,t,v["buy"],v["sell"]))
            conn.commit()
            output["applied"]=True
            output["mode"]="atomic_append"
            return output

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--check-db",action="store_true")
    parser.add_argument("--apply",action="store_true")
    args=parser.parse_args()
    print(json.dumps(run(check_db=args.check_db,apply=args.apply),default=str,sort_keys=True))
