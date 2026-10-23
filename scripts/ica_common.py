"""ICA primitives: pure validation, explicit publication and non-destructive writes."""
import argparse
from datetime import date
from decimal import Decimal, InvalidOperation
from io import BytesIO
import hashlib
import hmac
import json
import math
import os
import re
import sys
import unicodedata
from urllib.parse import urlparse
from urllib.request import Request, urlopen

MONTHS = ('enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre').split()
MAX_RECORDS = 5000


def normalize(value):
    text = unicodedata.normalize('NFKD', str(value).lower())
    return ' '.join(''.join(c for c in text if not unicodedata.combining(c)).split())


# Explicit aliases only: never fuzzy-match different countries.
COUNTRY_ALIASES = {
    'brasil': 'Brasil', 'china': 'China', 'paises bajos': 'Países Bajos',
    'estados unidos': 'Estados Unidos', 'estados unidos de america': 'Estados Unidos',
    'ee. uu.': 'Estados Unidos', 'viet nam': 'Vietnam', 'vietnam': 'Vietnam',
}


def country_identity(value):
    key = normalize(value)
    return COUNTRY_ALIASES.get(key, key.title())


def identity_value(field, value):
    if not isinstance(value, str):
        return value
    if field == 'pais':
        return normalize(country_identity(value))
    return normalize(value)


def payload_digest(table, records, keys):
    ordered = sorted(records, key=lambda row: tuple(str(row[k]) for k in keys))
    payload = json.dumps({'table': table, 'keys': list(keys), 'records': ordered},
                         sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def review_arguments(parser):
    parser.add_argument('--reviewed-sha256', help='SHA256 del payload validado y revisado previamente')
    return parser


def period(value):
    if not re.fullmatch(r'\d{4}-\d{2}', value):
        raise ValueError('El período debe ser YYYY-MM')
    first = date.fromisoformat(value + '-01')
    if first > date.today().replace(day=1):
        raise ValueError('No se admiten períodos futuros')
    return first.isoformat(), MONTHS[first.month - 1].capitalize() + f' {first.year}'


def number(value, *, localized=False):
    """Missing/invalid is an error, never an economic zero. Units stay unchanged."""
    if isinstance(value, bool) or value is None:
        raise ValueError(f'Número inválido: {value!r}')
    if isinstance(value, str):
        value = value.strip().replace('\xa0', '').replace(' ', '')
        if localized and ',' in value:
            value = value.replace('.', '').replace(',', '.')
        elif localized and re.fullmatch(r'-?\d{1,3}(\.\d{3})+', value):
            value = value.replace('.', '')
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f'Número inválido: {value!r}') from exc
    if not result.is_finite():
        raise ValueError('Número no finito')
    return float(result)


def download(url, host):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname != host or parsed.username or parsed.password:
        raise ValueError('La fuente debe ser HTTPS en el dominio oficial permitido')
    with urlopen(Request(url, headers={'User-Agent': 'EconomiaCriolla-ICA/1.0'}), timeout=30) as response:
        final = urlparse(response.url)
        if final.scheme != 'https' or final.hostname != host:
            raise ValueError('Redirección fuera de la fuente oficial')
        content = response.read(30_000_001)
    if not content or len(content) > 30_000_000:
        raise ValueError('Archivo vacío o demasiado grande')
    return content


def read_workbook(content):
    import pandas as pd
    # A legacy .xls must have an OLE signature; do not parse error HTML as Excel.
    if not content.startswith(bytes.fromhex('d0cf11e0a1b11ae1')):
        raise ValueError('La descarga no es un Excel XLS válido')
    return pd.ExcelFile(BytesIO(content), engine='xlrd')


def validate_sheet(df, selected_period):
    _, label = period(selected_period)
    text = normalize(' '.join(str(v) for v in df.head(15).to_numpy().flat))
    if normalize(label) not in text:
        raise ValueError('El encabezado no confirma el período solicitado')
    if re.search(r'(?:miles (?:de )?(?:dolares|usd)|millones (?:de )?pesos)', text):
        raise ValueError('Unidades mixtas o incompatibles en el encabezado')
    if not re.search(r'millones (?:de )?(?:dolares|usd)', text):
        raise ValueError('El encabezado no confirma millones de dólares')


def validate_value_column(df, column, selected_period):
    """Do not use an old-year or accumulated column merely because the sheet matches."""
    _, label = period(selected_period)
    header = normalize(' '.join(str(v) for v in df.iloc[:5, column]))
    if normalize(label) not in header or 'acumulad' in header:
        raise ValueError('La columna de valores no confirma el mes estadístico')


def validate_records(records, keys):
    if not records or len(records) > MAX_RECORDS:
        raise ValueError('Cantidad de registros vacía o fuera del límite atómico')
    seen = set()
    for row in records:
        identity = tuple(identity_value(k, row[k]) for k in keys)
        if any(v is None or v == '' for v in identity) or identity in seen:
            raise ValueError('Clave vacía o duplicada')
        seen.add(identity)
        for value in row.values():
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError('Valor no finito')


def persist(client, table, records, keys):
    validate_records(records, keys)
    # Exactly one PostgREST statement per robot: no DELETE, no partial batches.
    # Missing UNIQUE constraints cause an error rather than a destructive fallback.
    client.table(table).upsert(records, on_conflict=','.join(keys), ignore_duplicates=True).execute()


def publish(table, records, keys, write=False, client=None, *, reviewed_sha256=None):
    validate_records(records, keys)
    digest = payload_digest(table, records, keys)
    if not write:
        print(json.dumps({'mode': 'dry-run', 'table': table, 'rows': len(records),
                          'sha256': digest, 'records': records}, ensure_ascii=False, allow_nan=False))
        return
    if not reviewed_sha256 or not hmac.compare_digest(digest, reviewed_sha256):
        raise ValueError('Se requiere el SHA256 exacto del payload revisado; no se escribió nada')
    if client is None:
        url, key = os.environ.get('SUPABASE_URL'), os.environ.get('SUPABASE_KEY')
        if not url or not key:
            raise ValueError('Faltan SUPABASE_URL y/o SUPABASE_KEY')
        from supabase import create_client
        client = create_client(url, key)
    persist(client, table, records, keys)
    print(f'OK: solicitud insert-only confirmada para {table}; filas existentes conservadas. '
          'No se afirma cantidad insertada ni actualización de históricos.')


def excel_arguments(description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('--period', required=True, help='Mes estadístico YYYY-MM, no fecha de publicación')
    parser.add_argument('--excel-url', required=True, help='URL HTTPS oficial del XLS publicado')
    parser.add_argument('--write', action='store_true', help='Aplicar; por defecto solo valida')
    return review_arguments(parser)


def cli(main):
    try:
        main()
    except Exception as exc:
        # Do not print SDK exception messages: they can contain request credentials.
        print(f'ERROR ICA ({type(exc).__name__}); carga no confirmada. Revisar fuente/configuración.', file=sys.stderr)
        return 1
    return 0
