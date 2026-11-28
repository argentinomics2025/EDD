"""Read INDEC historical workbooks, retaining their distinct April 2012 base."""
import calendar
import hashlib
import re
from datetime import date, timedelta
from decimal import Decimal
import xlrd
from scripts.ec022_cvs import MONTHS

BASE_URL = "https://sitioanterior.indec.gob.ar/ftp/cuadros/sociedad/"

def _positive(value):
    result = Decimal(str(value))
    if not result.is_finite() or result <= 0:
        raise ValueError("Invalid INDEC index")
    return str(result)

def parse_cvs(raw):
    book = xlrd.open_workbook(file_contents=raw)
    names = book.sheet_names()
    if names != ['CVS Diarios base abril 2012=100']:
        raise ValueError('Unexpected historic CVS workbook')
    sheet = book.sheet_by_index(0)
    if 'abril de 2012=100' not in str(sheet.cell_value(0, 0)):
        raise ValueError('Unexpected historic CVS base')
    values = {}
    years = set()
    for row in range(sheet.nrows):
        match = re.fullmatch(r'A.o\s+(\d{4})', str(sheet.cell_value(row, 1)))
        if not match: continue
        year = int(match.group(1))
        if year in years or row+32 >= sheet.nrows: raise ValueError('Invalid CVS year block')
        years.add(year)
        for month, expected in enumerate(MONTHS, 1):
            head = str(sheet.cell_value(row+1, month)).strip().lower()
            if head == '':
                if any(sheet.cell_value(row+1+d, month) != '' for d in range(1,32)):
                    raise ValueError('Values under empty CVS header')
            elif head != expected and not (head == 'setiembre' and month == 9):
                raise ValueError('Invalid historic CVS header')
        for day in range(1,32):
            if sheet.cell_value(row+1+day,0) != day: raise ValueError('Invalid day row')
            for month in range(1,13):
                cell=sheet.cell(row+1+day,month)
                if cell.value == '': continue
                if cell.ctype != xlrd.XL_CELL_NUMBER or day > calendar.monthrange(year,month)[1]:
                    raise ValueError('Invalid CVS cell')
                d=date(year,month,day)
                if d in values: raise ValueError('Duplicate CVS date')
                values[d]=_positive(cell.value)
    dates=sorted(values)
    if not dates or any(b-a != timedelta(days=1) for a,b in zip(dates,dates[1:])):
        raise ValueError('Historic CVS gap')
    return {'series':'CVS_HISTORICO','source':BASE_URL+'serie_cvs_diarios_2012.xls',
            'base':'2012-04=100','sha256':hashlib.sha256(raw).hexdigest(),
            'observations':[{'date':d.isoformat(),'value':values[d]} for d in dates]}

def parse_salarios(raw):
    book=xlrd.open_workbook(file_contents=raw)
    matches=[s for s in book.sheets() if 'Serie hist' in s.name]
    if len(matches)!=1: raise ValueError('Unexpected salary workbook')
    sheet=matches[0]
    if 'abril de 2012=100' not in str(sheet.cell_value(0,0)) or 'Nivel general' not in str(sheet.cell_value(4,4)):
        raise ValueError('Unexpected salary identity or base')
    rows=[]
    for index in range(7,sheet.nrows):
        cell=sheet.cell(index,0)
        if cell.ctype != xlrd.XL_CELL_DATE: continue
        y,m,d,*_=xlrd.xldate_as_tuple(cell.value,book.datemode)
        if d != 1 or sheet.cell(index,4).ctype != xlrd.XL_CELL_NUMBER:
            raise ValueError('Invalid historic salary row')
        period=date(y,m,1)
        if rows:
            previous=date.fromisoformat(rows[-1]['date'])
            if (period.year-previous.year)*12+period.month-previous.month != 1:
                raise ValueError('Historic salary gap')
        rows.append({'date':period.isoformat(),'value':_positive(sheet.cell_value(index,4))})
    if not rows: raise ValueError('Empty salary history')
    return {'series':'IS_NIVEL_GENERAL_HISTORICO','source':BASE_URL+'serie_is_2012.xls',
            'base':'2012-04=100','sha256':hashlib.sha256(raw).hexdigest(),'observations':rows}
