"""Read-only, bounded probe for official MAGyP FOB daily JSON — no database."""
from __future__ import annotations
import argparse
import datetime as dt
import json
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

HOSTS = ("www.magyp.gob.ar", "monitorsiogranos.magyp.gob.ar")
PATHS = (
    "/sitio/areas/ss_mercados_agropecuarios/ws/ssma/precios_fob.php",
    "/ws/ssma/precios_fob.php",
)
MAX_BYTES = 1_000_000


def probe(day: dt.date) -> dict:
    errors = []
    for host, path in zip(HOSTS, PATHS):
        url = "https://" + host + path + "?" + urlencode({"Fecha": day.strftime("%d/%m/%Y")})
        try:
            req = Request(url, headers={"User-Agent": "EconomiaCriolla-EC021/1.0", "Accept": "application/json"})
            with urlopen(req, timeout=18) as resp:
                final = urlparse(resp.url)
                if final.hostname not in HOSTS:
                    raise ValueError("unexpected redirect")
                data = resp.read(MAX_BYTES + 1)
                if len(data) > MAX_BYTES:
                    raise ValueError("large response")
                ctype = resp.headers.get("Content-Type", "")
                raw = data.decode("utf-8-sig")
                parsed = json.loads(raw)
                summary = summarize(parsed)
                return {"date_requested": day.isoformat(), "provider_host": final.hostname,
                        "content_type": ctype, "size_bytes": len(data),
                        "shape": summary, "applied": False}
        except Exception as exc:
            errors.append({"host": host, "error_type": type(exc).__name__})
    return {"date_requested": day.isoformat(), "status": "unavailable",
            "errors": errors, "applied": False}


def summarize(data: object) -> dict:
    if isinstance(data, dict):
        return {"type": "object", "keys": sorted(data.keys())[:30],
                "subtypes": {str(k): type(v).__name__ for k,v in list(data.items())[:10]},
                "first": [summarize(v) for v in list(data.values())[:1]]}
    if isinstance(data, list):
        result = {"type": "array", "length": len(data)}
        if data:
            result["first"] = summarize(data[0])
            if isinstance(data[0], dict):
                first = data[0]
                result["public_sample"] = {str(k): str(v)[:60] for k,v in list(first.items())[:12]}
        return result
    return {"type": type(data).__name__, "value": str(data)[:90]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="2026-11-25")
    args = parser.parse_args()
    day = dt.date.fromisoformat(args.date)
    out = probe(day)
    print(json.dumps(out, ensure_ascii=False))
    raise SystemExit(1 if out.get("status") == "unavailable" else 0)
