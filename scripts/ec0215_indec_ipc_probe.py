"""EC-021.5: observe official INDEC IPC CSV without publishing any data.

Usage: python scripts/ec0215_indec_ipc_probe.py
Read-only: outputs the official file's metadata and SHA-256, not observations.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import ssl
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, HTTPSHandler

SOURCE_URL = "https://www.indec.gob.ar/ftp/cuadros/economia/serie_ipc_aperturas.csv"
ALLOWED_HOSTS = frozenset({"www.indec.gob.ar", "indec.gob.ar"})
MAX_BYTES = 10 * 1024 * 1024


class INDECRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        destination = urlsplit(newurl)
        if destination.scheme != "https" or destination.hostname not in ALLOWED_HOSTS:
            raise ValueError("INDEC source redirected outside official HTTPS hosts")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def inspect_source(url=SOURCE_URL, opener=None):
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in ALLOWED_HOSTS:
        raise ValueError("Only official INDEC HTTPS sources are permitted")
    if opener is None:
        opener = build_opener(INDECRedirects(), HTTPSHandler(context=ssl.create_default_context()))
    request = Request(url, headers={"User-Agent": "EconomiaCriolla-IPC-ReadOnly/1.0", "Accept": "text/csv,*/*;q=0.5"})
    with opener.open(request, timeout=20) as response:
        final = urlsplit(response.geturl())
        if final.scheme != "https" or final.hostname not in ALLOWED_HOSTS:
            raise ValueError("INDEC source changed host")
        data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("INDEC CSV exceeds size limit")
        content_type = response.headers.get("Content-Type", "").split(";")[0].lower()
        if content_type in {"text/html", "application/pdf"}:
            raise ValueError("INDEC response is not a CSV")
    if not data or b"\x00" in data:
        raise ValueError("INDEC response is empty or binary")
    try:
        decoded = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("INDEC CSV is not UTF-8; encoding requires review") from exc
    first_lines = decoded.splitlines()[:5]
    if not first_lines or not any(sep in first_lines[0] for sep in (",", ";", "\t")):
        raise ValueError("INDEC CSV header format requires review")
    try:
        dialect = csv.Sniffer().sniff("\n".join(first_lines), delimiters=",;\t")
        header = next(csv.reader(io.StringIO(decoded), dialect))
    except (csv.Error, StopIteration) as exc:
        raise ValueError("Cannot identify CSV columns") from exc
    if len(header) < 2 or any(not field.strip() for field in header):
        raise ValueError("INDEC CSV columns require review")
    return {
        "source": "INDEC (primary)",
        "url": url,
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "columns": header,
        "status": "observed_only_no_publication",
        "writes_to_supabase": False,
    }


if __name__ == "__main__":
    print(json.dumps(inspect_source(), ensure_ascii=False, sort_keys=True))
