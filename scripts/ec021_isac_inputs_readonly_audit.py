"""EC-021 Construction inputs: audit official ORIGINAL-series CSV versus Supabase, no writes."""
from collections import Counter
from datetime import date
from decimal import Decimal
import csv
import hashlib
import io
import json
import requests

from scripts.ec021_construction_isac_readonly_audit import DB, KEY, read

SOURCE = "https://infra.datos.gob.ar/catalog/sspm/dataset/33/distribution/33.3/download/indicador-sintetico-actividad-construccion-insumos-serie-original.csv"
DB_INPUTS = DB.replace("construccion_actividad", "construccion_insumos")
FIELDS = (
    "articulos_sanitarios", "asfalto", "cales", "cemento_portland", "hierro_redondo",
    "hormigon_elaborado", "ladrillos_huecos", "mosaicos", "pinturas",
    "pisos_revestimientos", "placas_yeso", "yeso", "resto"
)
SOURCE_COLUMNS = {
    "articulos_sanitarios": "isac_articulos_sanitarios_de_ceramica",
    "hierro_redondo": "isac_hierro_redondo_y_aceros_para_la_construccion",
    "mosaicos": "isac_mosaicos_graniticos_y_calcareos",
    "pinturas": "isac_pinturas_para_construccion",
    "pisos_revestimientos": "isac_pisos_y_revestimientos_ceramicos",
    "placas_yeso": "isac_placas_de_yeso",
}
MAX_BYTES = 4 * 1024 * 1024

def analyze(text, stored):
    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames or []
    if "indice_tiempo" not in headers:
        raise ValueError("Official CSV missing time index")
    rows = list(reader)
    if len(rows) < 24 or len(rows) > 1000:
        raise ValueError("Implausible input source history")
    sources = {}
    for row in rows:
        when = date.fromisoformat(row["indice_tiempo"][:10]).isoformat()
        if when in sources:
            raise ValueError("Duplicate official monthly date")
        sources[when] = row
    if not stored or len(stored) < 6:
        raise ValueError("No public Supabase overlap")
    if len({r["fecha"] for r in stored}) != len(stored):
        raise ValueError("Duplicate stored input date")
    comparisons = []
    missing_columns = []
    for field in FIELDS:
        source_col = SOURCE_COLUMNS.get(field, "isac_" + field)
        if source_col not in headers:
            missing_columns.append(source_col)
            continue
        aligned = []
        for dbrow in stored:
            when = dbrow["fecha"]
            source_row = sources.get(when)
            if not source_row or not source_row.get(source_col) or dbrow.get(field) is None:
                continue
            official = Decimal(source_row[source_col])
            published = Decimal(str(dbrow[field]))
            if not official.is_finite() or not published.is_finite():
                raise ValueError("Non finite construction input")
            aligned.append((when, abs(official-published), str(official), str(published)))
        if aligned:
            match = sum(err <= Decimal("0.051") for _,err,_,_ in aligned)
            comparisons.append({"field":field,"compared":len(aligned),"matched_with_rounding":match,
                                "mismatched":len(aligned)-match,
                                "latest_absolute_difference":str(aligned[0][1]),
                                "mismatch_samples":[{"fecha":when,"source":src,"db":db,"difference":str(diff)} for when,diff,src,db in aligned if diff > Decimal("0.051")][:3]})
    return {"mode":"read_only",
            "source":SOURCE,"source_rows":len(rows),"last_official":max(sources),
            "last_stored":max(x["fecha"] for x in stored),
            "missing_source_columns":missing_columns,
            "official_header":headers,
            "fields":comparisons,"writes_to_supabase":False}

def main():
    r=requests.get(SOURCE,timeout=35,allow_redirects=False,headers={"User-Agent":"EconomiaCriolla-ISAC-Audit/1.0"})
    r.raise_for_status()
    if r.is_redirect or len(r.content)>MAX_BYTES or not r.content:
        raise ValueError("Untrusted official inputs response")
    payload=r.content.decode("utf-8-sig")
    report=analyze(payload,read(DB_INPUTS,params={"select":"*","order":"fecha.desc","limit":"30"},headers={"apikey":KEY,"Accept":"application/json"}))
    report["sha256"]=hashlib.sha256(r.content).hexdigest()
    print(json.dumps(report,ensure_ascii=False,sort_keys=True))
if __name__=="__main__":main()
