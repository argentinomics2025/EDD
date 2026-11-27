"""EC-022 salary sources: read-only nominal RIPTE parser and INDEC download probe."""
import argparse, hashlib, json, re
from datetime import date, datetime
from decimal import Decimal
from html.parser import HTMLParser
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

RIPTE="https://www.argentina.gob.ar/trabajo/seguridadsocial/ripte"
INDEC="https://www.indec.gob.ar/ftp/cuadros/sociedad/"
MONTHS={m:i+1 for i,m in enumerate("enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split())}
MONTHS["setiembre"]=9
def download(url):
    with urlopen(Request(url,headers={"User-Agent":"EconomiaCriolla-EC022/1"}),timeout=30) as r:
        raw=r.read(12000001)
    if not raw or len(raw)>12000000: raise ValueError("Invalid source size")
    return raw

class Tables(HTMLParser):
    def __init__(self):
        super().__init__(); self.tables=[]; self.table=None; self.row=None; self.cell=None
    def handle_starttag(self,tag,attrs):
        if tag=="table":
            if self.table is not None: raise ValueError("Nested table")
            self.table=[]
        elif tag=="tr" and self.table is not None: self.row=[]
        elif tag in ("td","th") and self.row is not None: self.cell=[]
    def handle_data(self,data):
        if self.cell is not None: self.cell.append(data)
    def handle_endtag(self,tag):
        if tag in ("td","th") and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split())); self.cell=None
        elif tag=="tr" and self.row is not None: self.table.append(self.row); self.row=None
        elif tag=="table" and self.table is not None: self.tables.append(self.table); self.table=None

def number(s):
    s=s.strip().replace("$","").replace("%","").strip()
    if not re.fullmatch(r"-?(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?",s): raise ValueError("Invalid AR number")
    return Decimal(s.replace(".","").replace(",","."))

def parse_ripte(raw,today=None):
    today=today or datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date()
    p=Tables(); p.feed(raw.decode("utf-8-sig")); matches=[]
    for t in p.tables:
        for idx,row in enumerate(t):
            h=[x.casefold() for x in row]
            if len(h)>=3 and h[0]=="mes" and "monto" in h[1] and "pesos" in h[1] and "variaci" in h[2]: matches.append(t[idx+1:])
    if len(matches)!=1: raise ValueError("RIPTE table identity not unique")
    rows={}
    for r in matches[0]:
        if not r or not any(r): continue
        if len(r)<3: raise ValueError("Incomplete row")
        m=re.fullmatch(r"([a-záéíóú]+)\s*/\s*(\d{4})",r[0].casefold())
        if not m or m[1] not in MONTHS: raise ValueError("Invalid month")
        d=date(int(m[2]),MONTHS[m[1]],1); v=number(r[1]); change=number(r[2])
        if d>=today.replace(day=1) or d in rows or v<=0 or change<=-100: raise ValueError("Invalid observation")
        rows[d]=(v,change)
    if len(rows)<2: raise ValueError("Insufficient history")
    dates=sorted(rows)
    for a,b in zip(dates,dates[1:]):
        if (b.year-a.year)*12+b.month-a.month!=1: raise ValueError("Missing month")
        if abs((rows[b][0]/rows[a][0]-1)*100-rows[b][1])>Decimal("0.15"): raise ValueError("Amount/change mismatch")
    return {"source":RIPTE,"sha256":hashlib.sha256(raw).hexdigest(),"series":"RIPTE_NOMINAL","unit":"ARS","observations":[{"date":str(d),"value":str(rows[d][0]),"monthly_percent":str(rows[d][1])} for d in dates],"writes_to_supabase":False}

def probe_indec(year,fetch=download):
    if not 2016<=year<=datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).year: raise ValueError("Invalid year")
    out=[]
    for name in [f"sh_cvs_diarios_{year}.xls","indice_salarios.csv","variacion_indice_salarios.csv","metadatos_series_salarios.txt"]:
        url=INDEC+name; raw=fetch(url)
        if name.endswith(".xls") and not raw.startswith(bytes.fromhex("D0CF11E0A1B11AE1")): raise ValueError("Not XLS")
        if not name.endswith(".xls") and raw.lstrip().lower().startswith((b"<html",b"<!doctype")): raise ValueError("Unexpected HTML")
        out.append({"source":url,"sha256":hashlib.sha256(raw).hexdigest(),"bytes":len(raw),"status":"download_only_schema_unverified"})
    return out

if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("source",choices=["ripte","indec"]); p.add_argument("--year",type=int,default=datetime.now().year); a=p.parse_args()
    print(json.dumps(parse_ripte(download(RIPTE)) if a.source=="ripte" else probe_indec(a.year)))
