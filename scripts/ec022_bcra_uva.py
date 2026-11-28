"""Parse BCRA monthly UVA mortgage flows and rates; never writes to a DB."""
import hashlib
from datetime import date
from decimal import Decimal
import xlrd

SOURCE='https://www.bcra.gob.ar/archivos/Pdfs/PublicacionesEstadisticas/preser_uva.xls'

def parse(raw):
    book=xlrd.open_workbook(file_contents=raw)
    if 'Datos' not in book.sheet_names(): raise ValueError('Missing BCRA data sheet')
    sheet=book.sheet_by_name('Datos')
    if (sheet.ncols < 6 or 'UVA' not in str(sheet.cell_value(17,3))
        or sheet.cell_value(18,3) != 'Hipotecarios' or sheet.cell_value(19,3) != 'Total'
        or sheet.cell_value(21,3) != 'Monto' or sheet.cell_value(21,4) != 'Tasa'
        or [sheet.cell_value(25,i) for i in (2,3,4)] != ['prefecha','pasvar49','pasvar50']):
        raise ValueError('Unexpected BCRA UVA schema')
    rows=[]
    for i in range(27,sheet.nrows):
        if sheet.cell(i,2).ctype != xlrd.XL_CELL_NUMBER: raise ValueError('Invalid UVA period')
        code=int(sheet.cell_value(i,2));year,month=divmod(code,100)
        if month == 13 and sheet.cell_value(i,3) == '' and sheet.cell_value(i,4) == '':
            continue  # BCRA's blank annual separator, not an observation.
        period=date(year,month,1)
        # The BCRA notes identify new UVA loans only from May 2016. Earlier
        # placeholders in the workbook do not establish zero disbursements.
        if period < date(2016,5,1):
            continue
        if rows:
            previous=date.fromisoformat(rows[-1]['date'])
            if (period.year-previous.year)*12+period.month-previous.month != 1:
                raise ValueError('Missing or duplicated UVA month')
        if any(sheet.cell(i,j).ctype != xlrd.XL_CELL_NUMBER for j in (3,4)):
            raise ValueError('Invalid UVA value')
        amount=Decimal(str(sheet.cell_value(i,3)));rate=Decimal(str(sheet.cell_value(i,4)))
        if not amount.is_finite() or not rate.is_finite() or amount<0 or rate<0:
            raise ValueError('Invalid UVA value')
        rows.append({'date':period.isoformat(),'amount_thousand_ars':str(amount),
                     'annual_nominal_rate_percent':str(rate),
                     'zero_amount_rate_not_interpreted':amount==0})
    if not rows: raise ValueError('Empty UVA history')
    return {'source':SOURCE,'sha256':hashlib.sha256(raw).hexdigest(),
            'scope':'mortgages_uva','rate_kind':'annual_nominal_percent',
            'amount_unit':'thousand_ARS','frequency':'monthly','observations':rows,
            'writes_to_supabase':False}
