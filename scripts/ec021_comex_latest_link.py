"""EC-021 COMEX: discover official INDEC ICA XLS editions, read only."""
from html.parser import HTMLParser
from urllib.request import Request, urlopen
from urllib.parse import urljoin,urlsplit
import re
import ssl
import json

INDEX="https://www.indec.gob.ar/indec/web/Nivel4-Tema-3-2-40"
HOST="www.indec.gob.ar"
NAME=re.compile(r"ica_cuadros_(\d{2})_(\d{2})_(\d{2})\.xls",re.I)

class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls=[]
    def handle_starttag(self,tag,attrs):
        if tag=="a":
            for k,v in attrs:
                if k=="href" and v:self.urls.append(v)

def main():
    with urlopen(Request(INDEX,headers={"User-Agent":"EconomiaCriolla-COMEX-ReadOnly/1.0"}), timeout=25,context=ssl.create_default_context()) as res:
        if urlsplit(res.geturl()).hostname != HOST:raise ValueError("Unapproved redirect")
        payload=res.read(2*1024*1024+1)
    if not payload or len(payload)>2*1024*1024:raise ValueError("Invalid HTML")
    parsed=Links();parsed.feed(payload.decode("utf-8-sig",errors="replace"))
    found=[]
    for href in parsed.urls:
        url=urljoin(INDEX,href)
        u=urlsplit(url);m=NAME.search(u.path)
        if u.scheme=="https" and u.hostname==HOST and m:
            found.append({"url":url,"year":int("20"+m[3]),"month":int(m[2]),"day":int(m[1])})
    found.sort(key=lambda x:(x["year"],x["month"],x["day"]),reverse=True)
    print(json.dumps({"official_index":INDEX,"links_checked":len(parsed.urls),"latest_xls":found[:3],"writes_to_supabase":False},ensure_ascii=False))
    if not found:raise ValueError("No official XLS link in index; fail closed")

if __name__=="__main__":main()
