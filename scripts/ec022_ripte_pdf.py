"""Parse the original RIPTE monthly amount and published percent from PDF text."""
import hashlib
import io
import re
from datetime import date
from decimal import Decimal
from pypdf import PdfReader

MONTHS={m:i+1 for i,m in enumerate('enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre'.split())}
MONTHS['setiembre']=9
PATTERN=re.compile(r'^\s*('+'|'.join(MONTHS)+r')\s+\$\s*([\d. ,]+?)\s{2,}(-?[\d.,]+%|-)\s',re.I)

def number(value):
    return Decimal(value.replace(' ','').replace('.','').replace(',','.').replace('%',''))

def parse(raw,source):
    reader=PdfReader(io.BytesIO(raw))
    year=None
    rows=[]
    for page in reader.pages:
        text=page.extract_text(extraction_mode='layout') or ''
        for line in text.splitlines():
            m=re.fullmatch(r'\s*(19\d\d|20\d\d)\s*',line)
            if m: year=int(m.group(1)); continue
            month_match=re.match(r'^\s*('+'|'.join(MONTHS)+r')\b',line,re.I)
            if not month_match: continue
            match=PATTERN.match(line)
            if not match or year is None: raise ValueError('Unrecognized RIPTE PDF row')
            period=date(year,MONTHS[match.group(1).lower()],1)
            amount=number(match.group(2))
            change=None if match.group(3)=='-' else number(match.group(3))
            if not amount.is_finite() or amount<=0 or (change is not None and not change.is_finite()):
                raise ValueError('Invalid RIPTE value')
            if rows:
                prior=date.fromisoformat(rows[-1]['date'])
                if (period.year-prior.year)*12+period.month-prior.month != 1: raise ValueError('RIPTE PDF gap or duplicate')
                expected=(amount/Decimal(rows[-1]['value'])-1)*100
                if change is not None and abs(expected-change)>Decimal('0.15'):
                    raise ValueError(f'RIPTE amount/change mismatch at {period}: calculated={expected}, published={change}')
            rows.append({'date':period.isoformat(),'value':str(amount),'monthly_percent':None if change is None else str(change)})
    if not rows: raise ValueError('No RIPTE PDF observations')
    return {'source':source,'sha256':hashlib.sha256(raw).hexdigest(),'frequency':'monthly',
            'unit':'ARS','observations':rows,'writes_to_supabase':False}
