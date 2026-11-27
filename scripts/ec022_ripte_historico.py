"""Read official Economía RIPTE historical CSV; keep this edition separate."""
import csv
import hashlib
import io
from datetime import date
from decimal import Decimal, InvalidOperation

SOURCE = "https://infra.datos.gob.ar/catalog/sspm/dataset/158/distribution/158.1/download/remuneracion-imponible-promedio-trabajadores-estables-ripte-total-pais-pesos-serie-mensual.csv"

def parse(raw):
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    if reader.fieldnames != ["indice_tiempo", "ripte"]:
        raise ValueError("Unexpected RIPTE CSV schema")
    rows = []
    last = None
    for row in reader:
        if None in row or any(v is None for v in row.values()):
            raise ValueError("Malformed RIPTE row")
        try:
            d = date.fromisoformat(row["indice_tiempo"])
            value = Decimal(row["ripte"])
        except (ValueError, InvalidOperation) as exc:
            raise ValueError("Invalid RIPTE value") from exc
        if d.day != 1 or (last and (d.year-last.year)*12+d.month-last.month != 1) or not value.is_finite() or value <= 0:
            raise ValueError("Invalid RIPTE history")
        rows.append({"date":d.isoformat(),"value":str(value)})
        last = d
    if not rows:
        raise ValueError("Empty RIPTE history")
    return {"source":SOURCE,"sha256":hashlib.sha256(raw).hexdigest(),"series":"RIPTE_NOMINAL",
            "unit":"ARS", "frequency":"monthly", "observations":rows,"writes_to_supabase":False}
