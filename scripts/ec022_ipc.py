"""Read the INDEC national CPI level and its published monthly change."""
import csv
import hashlib
import io
from datetime import date
from decimal import Decimal, InvalidOperation

SOURCE = "https://www.indec.gob.ar/ftp/cuadros/economia/serie_ipc_divisiones.csv"
HEADER = ['Codigo','Descripcion','Clasificador','Periodo','Indice_IPC','v_m_IPC','v_i_a_IPC','Region']

def parse(raw):
    reader = csv.DictReader(io.StringIO(raw.decode('cp1252')), delimiter=';')
    if reader.fieldnames != HEADER:
        raise ValueError('Unexpected IPC schema')
    rows = []
    last = None
    for row in reader:
        if None in row or any(v is None for v in row.values()):
            raise ValueError('Malformed IPC row')
        if row['Codigo'] != '0' or row['Region'] != 'Nacional':
            continue
        if row['Descripcion'] != 'NIVEL GENERAL':
            raise ValueError('Wrong IPC identity')
        try:
            period = row['Periodo']
            if len(period) != 6 or not period.isdigit(): raise ValueError('Invalid period')
            d = date(int(period[:4]),int(period[4:]),1)
            value = Decimal(row['Indice_IPC'].replace(',','.'))
            change = None if row['v_m_IPC'] == 'NA' else Decimal(row['v_m_IPC'].replace(',','.'))
        except (ValueError,InvalidOperation) as exc:
            raise ValueError('Invalid IPC observation') from exc
        if not value.is_finite() or value <= 0 or (change is not None and not change.is_finite()):
            raise ValueError('Invalid IPC value')
        if last:
            if (d.year-last[0].year)*12+d.month-last[0].month != 1:
                raise ValueError('Invalid IPC sequence')
            if change is None or abs((value/last[1]-1)*100-change) > Decimal('0.15'):
                raise ValueError('IPC level/change mismatch')
        rows.append({'date':d.isoformat(),'index':str(value),'monthly_percent':None if change is None else str(change)})
        last = (d,value)
    if not rows: raise ValueError('No national IPC observations')
    return {'source':SOURCE,'sha256':hashlib.sha256(raw).hexdigest(), 'frequency':'monthly',
            'base':'2016-12=100','observations':rows,'writes_to_supabase':False}
