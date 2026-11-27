"""Read selected BCRA monthly mortgage series from official TXT datasets.

Series are separate: the operated amount is a flow, the balance is a stock,
and the weighted rate is neither a bank offer nor a CFT. No writes.
"""
import calendar
import hashlib
from datetime import datetime
from decimal import Decimal, InvalidOperation

BASE = "https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/"
SERIES = {
    "tas2_ser.txt": {
        "3772": ("tasa_hipotecaria", "percent_nominal_annual", "weighted_rate"),
        "4291": ("monto_otorgado_hipotecario", "thousand_ARS", "monthly_flow"),
    },
    "din1_ser.txt": {
        "154": ("saldo_hipotecario_total", "thousand_ARS", "end_month_stock"),
        "155": ("saldo_hipotecario_vivienda", "thousand_ARS", "end_month_stock"),
    },
}

def parse(raw, filename):
    if filename not in SERIES:
        raise ValueError("Unknown BCRA dataset")
    selected = SERIES[filename]
    rows = {key: {} for key in selected}
    for line in raw.decode("ascii").splitlines():
        parts = line.split(";")
        if not parts or parts[0] not in rows:
            continue
        if len(parts) != 3:
            raise ValueError("Malformed selected row")
        key, text_date, text_value = parts
        try:
            d = datetime.strptime(text_date, "%d/%m/%Y").date()
            value = Decimal(text_value)
        except (ValueError, InvalidOperation) as exc:
            raise ValueError("Invalid BCRA observation") from exc
        if d.day != calendar.monthrange(d.year, d.month)[1] or d in rows[key] or not value.is_finite() or value < 0:
            raise ValueError("Invalid BCRA observation")
        rows[key][d] = value
    result = {}
    for key, (name, unit, kind) in selected.items():
        if not rows[key]:
            raise ValueError("Missing selected series")
        dates = sorted(rows[key])
        missing_months = sum((b.year-a.year)*12+b.month-a.month-1 for a,b in zip(dates,dates[1:]))
        result[name] = {"bcra_id": key, "frequency": "monthly", "unit": unit, "kind": kind,
                        "currency": "pesos_serie_bcra", "missing_months": missing_months,
                        "historical_currency_and_methodology_breaks_unverified": True,
                        "observations": [{"date": d.isoformat(), "value": str(rows[key][d])} for d in dates]}
    return {"source": BASE+filename, "sha256": hashlib.sha256(raw).hexdigest(),
            "series": result, "writes_to_supabase": False}
