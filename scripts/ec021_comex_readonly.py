"""EC-021 COMEX: lectura oficial estricta. Nunca escribe en Supabase."""
import hashlib
import html
from html.parser import HTMLParser
import json
import re
import ssl
from decimal import Decimal
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler

URL = "https://www.indec.gob.ar/ftp/ica_digital/ica_d_11_262BEEC7410A/"
LIMIT = 2 * 1024 * 1024
MONTHS = {m: i for i, m in enumerate(("enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre").split(), 1)}

def allowed(url):
    p = urlsplit(url)
    return p.scheme == "https" and p.hostname == "www.indec.gob.ar" and p.port is None and not p.username and not p.password and p.path.startswith("/ftp/ica_digital/ica_d_")

class SafeRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, url):
        if not allowed(url):
            raise ValueError("External redirect denied")
        return super().redirect_request(req, fp, code, msg, headers, url)

class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.hidden += 1
    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self.hidden:
            self.hidden -= 1
    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)

def parse(payload):
    if not payload or len(payload) > LIMIT:
        raise ValueError("Invalid response length")
    parser = VisibleText()
    parser.feed(payload.decode("utf-8-sig"))
    text = " ".join(html.unescape(" ".join(parser.parts)).split())
    pub = re.search(r"Fecha de publicación:\s*(\d{1,2}) de (\w+) de (20\d{2})", text, re.I)
    match = re.search(r"En (\w+) de (20\d{2}), las exportaciones alcanzaron\s+([\d.]+) millones de dólares.*?y las importaciones,\s+([\d.]+) millones de dólares.*?balanza comercial registró un superávit de\s+([\d.]+) millones de dólares", text, re.I)
    if not pub or not match:
        raise ValueError("Official summary absent or changed")
    month = MONTHS.get(match[1].lower())
    pub_month = MONTHS.get(pub[2].lower())
    if not month or not pub_month or not (int(match[2]) <= int(pub[3]) <= int(match[2]) + 1):
        raise ValueError("Unexpected report period")
    exports, imports, balance = (Decimal(match[i].replace(".", "")) for i in (3, 4, 5))
    if exports <= 0 or imports <= 0 or abs(exports - imports - balance) > 1:
        raise ValueError("Unreconciled published balance")
    return {
        "period": f"{match[2]}-{month:02d}-01",
        "publication_date": f"{pub[3]}-{pub_month:02d}-{int(pub[1]):02d}",
        "exports_musd_rounded": str(exports),
        "imports_musd_rounded": str(imports),
        "balance_musd_rounded": str(balance),
        "rounding_residual_musd": str(balance - exports + imports),
        "status": "read_only_review_required",
        "writes_to_supabase": False
    }

def fetch(url=URL):
    if not allowed(url):
        raise ValueError("Unapproved INDEC URL")
    opener = build_opener(SafeRedirects(), HTTPSHandler(context=ssl.create_default_context()))
    with opener.open(Request(url, headers={"User-Agent":"EconomiaCriolla-COMEX-ReadOnly/1.0"}), timeout=25) as response:
        if not allowed(response.geturl()):
            raise ValueError("Unapproved final URL")
        mime = response.headers.get("Content-Type", "").lower()
        payload = response.read(LIMIT + 1)
    if "html" not in mime or len(payload) > LIMIT:
        raise ValueError("Unexpected format or size")
    return payload

if __name__ == "__main__":
    payload = fetch()
    print(json.dumps({**parse(payload), "source_url": URL, "sha256": hashlib.sha256(payload).hexdigest()}, ensure_ascii=False, sort_keys=True))
