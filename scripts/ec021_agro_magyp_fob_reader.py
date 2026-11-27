"""EC-021 Agro: official MAGyP FOB daily prices, read-only, no credentials.

FOB export prices are NOT Rosario CAC pizarra, CBOT futures nor producer prices.
Each selected tariff classification and shipping window is an explicit series.
Official MAGyP JSON API: https://www.magyp.gob.ar/sitio/areas/
ss_mercados_agropecuarios/fob_oficiales/_archivos/000021_Precios%20Fob%20Api.php
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import math
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

API_URLS = (
    "https://www.magyp.gob.ar/sitio/areas/ss_mercados_agropecuarios/ws/ssma/precios_fob.php",
    "https://monitorsiogranos.magyp.gob.ar/ws/ssma/precios_fob.php",
)
CODES = {
    "soja_fob_granel": "12019000190C",
    "maiz_fob_granel": "10059010120A",
    "trigo_pan_fob_granel": "10019900110W",
    "girasol_fob": "12060090910Y",
}
MAX_BYTES = 1_000_000
SOURCE = "Secretaría de Agricultura, Ganadería y Pesca — Precios FOB oficiales"
DATASET_LICENSE = "CC BY 4.0 — Datos Argentina (sspm_358)"
DATASET_URL = "https://www.datos.gob.ar/es/dataset/sspm-precios-fob-oficiales"

class AgroFOBError(ValueError):
    pass


def parse_official(payload: object, *, expected_date: dt.date) -> dict:
    if not isinstance(payload, dict) or not isinstance(payload.get("posts"), list):
        raise AgroFOBError("Missing official JSON posts")
    posts = payload["posts"]
    if not 4 <= len(posts) <= 1000:
        raise AgroFOBError("Unexpected official positions count")
    selection = {}
    for item in posts:
        if not isinstance(item, dict):
            raise AgroFOBError("Malformed official item")
        code = item.get("posicion")
        if code not in CODES.values():
            continue
        crop = next(name for name, pos in CODES.items() if pos == code)
        date_text = str(item.get("fecha", ""))[:10]
        if date_text != expected_date.isoformat():
            raise AgroFOBError("Official publication date differs from request")
        price = item.get("precio")
        if isinstance(price, bool) or not isinstance(price, (float, int)):
            raise AgroFOBError("FOB value is not numeric")
        price = float(price)
        if not math.isfinite(price) or not 20 <= price <= 10000:
            raise AgroFOBError("Invalid FOB price")
        try:
            yr1, mo1 = int(item["añoDesde"]), int(item["mesDesde"])
            yr2, mo2 = int(item["añoHasta"]), int(item["mesHasta"])
            start, end = dt.date(yr1, mo1, 1), dt.date(yr2, mo2, 1)
        except (KeyError, ValueError, TypeError) as exc:
            raise AgroFOBError("Invalid shipment month or year") from exc
        shipment_month = dt.date(expected_date.year, expected_date.month, 1)
        if end < start:
            raise AgroFOBError("Reversed shipment window")
        # Choose only the official tranche that covers the requested trading month.
        if not (start <= shipment_month <= end):
            continue
        circular = str(item.get("circular", "")).strip()
        if not circular.isdecimal():
            raise AgroFOBError("Invalid official circular")
        if crop in selection:
            raise AgroFOBError("Overlapping shipment windows for same product")
        selection[crop] = {
            "fecha": expected_date.isoformat(),
            "serie": crop,
            "posicion": code,
            "precio_usd_tn": price,
            "embarque_desde": start.isoformat(),
            "embarque_hasta": end.isoformat(),
            "circular": circular,
            "fuente": SOURCE,
        }
    if set(selection) != set(CODES):
        raise AgroFOBError("Incomplete official 4-product / shipment batch")
    if len({v["circular"] for v in selection.values()}) != 1:
        raise AgroFOBError("Conflicting circulars in same official release")
    records = [selection[k] for k in sorted(selection)]
    digest = hashlib.sha256(json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "status": "validated_read_only",
        "fecha": expected_date.isoformat(),
        "circular": records[0]["circular"],
        "fuente": SOURCE,
        "licencia_catalogo": DATASET_LICENSE,
        "catalogo": DATASET_URL,
        "unidad": "USD/tn (FOB exportación, no precio en Rosario)",
        "series": records,
        "sha256": digest,
        "applied": False,
    }


def fetch_official(day: dt.date) -> dict:
    errors = []
    for endpoint in API_URLS:
        url = endpoint + "?" + urlencode({"Fecha": day.strftime("%d/%m/%Y")})
        try:
            req = Request(url, headers={"Accept":"application/json","User-Agent":"EconomiaCriolla-EC021/1.0"})
            with urlopen(req, timeout=20) as response:
                host = urlparse(response.url).hostname
                if host not in ("www.magyp.gob.ar", "monitorsiogranos.magyp.gob.ar"):
                    raise AgroFOBError("Unexpected provider redirect")
                raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise AgroFOBError("Oversized official response")
            return json.loads(raw.decode("utf-8-sig"))
        except Exception as exc:
            errors.append(type(exc).__name__)
    raise AgroFOBError("Official API unavailable on both allowed endpoints (" + ",".join(errors) + ")")


def fetch_latest(*, now: dt.date | None = None) -> dict:
    now = now or dt.datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date()
    if now.weekday() >= 5:
        # The official source explicitly does not publish on weekends.
        days_back = 1 if now.weekday() == 5 else 2
    else:
        days_back = 0
    for lag in range(days_back, 8):
        candidate = now - dt.timedelta(days=lag)
        if candidate.weekday() >= 5:
            continue
        payload = fetch_official(candidate)
        if isinstance(payload, dict) and isinstance(payload.get("posts"), list) and not payload["posts"]:
            continue
        report = parse_official(payload, expected_date=candidate)
        if lag > 6:
            raise AgroFOBError("Source older than 6 calendar days")
        return report
    raise AgroFOBError("No complete recent official FOB release")


def main() -> int:
    p = argparse.ArgumentParser()
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--date")
    group.add_argument("--latest", action="store_true")
    args = p.parse_args()
    try:
        result = (parse_official(fetch_official(dt.date.fromisoformat(args.date)),
                                 expected_date=dt.date.fromisoformat(args.date))
                  if args.date else fetch_latest())
    except (AgroFOBError, ValueError) as exc:
        print(json.dumps({"status": "rejected", "reason": str(exc), "applied": False}))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
