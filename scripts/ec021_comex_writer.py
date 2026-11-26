"""EC-021 COMEX: guarded INSERT-only monthly publisher.

Safe by default: reads/validates official XLS, never contacts database unless
--commit AND EC021_COMEX_WRITES_ENABLED=true AND a dedicated DSN are provided.
Existing months and official historical revisions are NEVER overwritten.
"""
import argparse
from datetime import date, timedelta
from decimal import Decimal
import json
import os
import re
from ec021_comex_latest_link import inspect

COLUMNS = (
    "fecha", "exportaciones_usd_millions", "importaciones_usd_millions",
    "saldo_usd_millions", "expo_primarios", "expo_moa", "expo_moi",
    "expo_energia", "impo_bienes_capital", "impo_bienes_intermedios",
    "impo_combustibles", "impo_piezas_accesorios", "impo_bienes_consumo",
    "impo_vehiculos"
)
AMOUNT_COLS = COLUMNS[1:]
WRITER_ROLE = "ec021_comex_writer"

def prev_month(period):
    first=date.fromisoformat(period)
    previous=first-timedelta(days=1)
    return previous.replace(day=1)

def next_month(period):
    day=period if isinstance(period,date) else date.fromisoformat(period)
    return date(day.year+int(day.month==12),day.month%12+1,1)

def compare_existing(existing, incoming, edition_hash, saved_hash):
    """Strict idempotency; detect revisions rather than overwriting them."""
    if existing is None:
        return "insert"
    if any(Decimal(str(existing[key]))!=Decimal(str(incoming[key])) for key in AMOUNT_COLS):
        raise ValueError("Official revision conflicts with stored COMEX month: manual review needed")
    if saved_hash != edition_hash:
        raise ValueError("ICA XLS edition hash changed: retain histories and review new edition")
    return "no_change"

def insert_only(document, dsn):
    import psycopg
    from psycopg.types.json import Jsonb
    values=document["values"]
    period=date.fromisoformat(values["fecha"])
    edition_sha=document["sha256"]
    url_date=re.search(r"ica_cuadros_(\d{2})_(\d{2})_(\d{2})\.xls$",document["url"])
    if not url_date:
        raise ValueError("Unknown official ICA edition date")
    publication_date=date(2000+int(url_date[3]),int(url_date[2]),int(url_date[1]))
    if publication_date.year != period.year+int(period.month==12) or publication_date.month != (period.month%12+1):
        raise ValueError("Release-month/period mismatch")
    with psycopg.connect(dsn, connect_timeout=12, sslmode="require") as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute("SELECT current_user")
                actor=cur.fetchone()[0]
                if actor != WRITER_ROLE:
                    raise PermissionError("Must connect as dedicated EC021 COMEX INSERT-only role")
                cur.execute("SELECT pg_advisory_xact_lock(2026,1021)")
                cur.execute("SELECT "+",".join(COLUMNS)+" FROM public.datos_comex WHERE fecha=%s", (period,))
                record=cur.fetchone()
                current=dict(zip(COLUMNS,record)) if record else None
                if current:
                    cur.execute("SELECT file_sha256 FROM ec021_audit.comex_source_editions WHERE period=%s", (period,))
                    hashes=[r[0] for r in cur.fetchall()]
                    if len(hashes)!=1:
                        raise ValueError("Missing/duplicate source edition provenance")
                    state=compare_existing(current,values,edition_sha,hashes[0])
                    return {"status":state,"period":period.isoformat(),"applied":False,"db_role":actor}
                cur.execute("SELECT count(*),count(DISTINCT fecha),max(fecha) FROM public.datos_comex")
                count,unique,last=cur.fetchone()
                if count!=unique or not last or next_month(last)!=period:
                    raise ValueError("Gap or duplicate before next month: no insertion")
                cur.execute("SELECT 1 FROM ec021_audit.comex_source_editions WHERE period=%s", (period,))
                if cur.fetchone():
                    raise ValueError("Previous edition exists without matching published record")
                cur.execute("SELECT md5(string_agg(row_to_json(t)::text,'|' ORDER BY t.fecha)) FROM (SELECT * FROM public.datos_comex ORDER BY fecha) t")
                fingerprint=cur.fetchone()[0]
                if not fingerprint:
                    raise ValueError("Empty preinsert fingerprint")
                payload={"values":values,"previous_count":count,"previous_md5":fingerprint,
                         "source_sha256":edition_sha,"unit":"USD millions",
                         "import_resto_not_in_public_table":values["impo_resto_unstored"]}
                cur.execute("""
                    INSERT INTO ec021_audit.comex_source_editions
                    (period,file_sha256,source_url,publication_date,source_values,notes)
                    VALUES (%s,%s,%s,%s,%s,%s)
                """,(period,edition_sha,document["url"],publication_date,Jsonb(payload),
                    "EC-021 append-only; automated source validated c1/c3/c4. Historical revisions blocked."))
                cur.execute("INSERT INTO public.datos_comex ("+",".join(COLUMNS)+") VALUES ("+",".join(["%s"]*len(COLUMNS))+")",
                            (period,*(Decimal(values[k]) for k in AMOUNT_COLS)))
                cur.execute("SELECT count(*),count(DISTINCT fecha),max(fecha) FROM public.datos_comex")
                new_count,new_unique,new_latest=cur.fetchone()
                if new_count!=count+1 or new_count!=new_unique or new_latest!=period:
                    raise ValueError("COMEX post-insert cardinality mismatch; rollback")
                cur.execute("SELECT md5(string_agg(row_to_json(t)::text,'|' ORDER BY t.fecha)) FROM (SELECT * FROM public.datos_comex WHERE fecha<%s ORDER BY fecha) t",(period,))
                if cur.fetchone()[0]!=fingerprint:
                    raise ValueError("Historic COMEX hash changed; rollback")
                return {"status":"inserted","period":period.isoformat(),"applied":True,
                        "previous_count":count,"current_count":new_count,"db_role":actor}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--release-month",required=True)
    parser.add_argument("--commit",action="store_true")
    args=parser.parse_args()
    report=inspect(args.release_month)
    if not args.commit:
        print(json.dumps({"status":"source_verified_dry_run","period":report["period"],
                          "source_sha256":report["sha256"],"source":report["url"],
                          "writes_to_supabase":False},sort_keys=True))
        return
    if os.environ.get("EC021_COMEX_WRITES_ENABLED")!="true":
        raise PermissionError("EC021 COMEX writer disabled by kill switch")
    dsn=os.environ.get("EC021_COMEX_DB_DSN")
    if not dsn:
        raise PermissionError("Dedicated EC021_COMEX_DB_DSN missing")
    result=insert_only(report,dsn)
    print(json.dumps(result,sort_keys=True))

if __name__=="__main__":
    main()
