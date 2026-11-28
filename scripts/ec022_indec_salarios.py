"""Read the official INDEC salary index CSV without persisting observations."""
import csv
import hashlib
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation

URL = "https://www.indec.gob.ar/ftp/cuadros/sociedad/indice_salarios.csv"
FIELDS = ["periodo", "IS_sector_privado_registrado", "IS_sector_publico",
          "IS_total_registrado", "IS_sector_no_registrado", "IS_indice_total"]

def parse(raw):
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")), delimiter=";")
    if reader.fieldnames != FIELDS:
        raise ValueError("Unexpected INDEC salary schema")
    observations = []
    last = None
    for row in reader:
        if None in row or any(v is None for v in row.values()):
            raise ValueError("Malformed row")
        period = datetime.strptime(row["periodo"], "%d/%m/%Y").date()
        if period.day != 1 or (last and (period.year-last.year)*12+period.month-last.month != 1):
            raise ValueError("Invalid monthly sequence")
        last = period
        val = row["IS_indice_total"].strip()
        if val == "NA":
            continue
        try:
            value = Decimal(val.replace(",", "."))
        except InvalidOperation as exc:
            raise ValueError("Invalid value") from exc
        if not value.is_finite() or value <= 0:
            raise ValueError("Invalid value")
        observations.append({"date": period.isoformat(), "value": str(value)})
    if not observations:
        raise ValueError("No observations")
    return {"series": "INDEC_IS_TOTAL", "frequency": "monthly", "unit": "index",
            "base": "2016-10=100", "source": URL,
            "sha256": hashlib.sha256(raw).hexdigest(), "observations": observations,
            "writes_to_supabase": False}
