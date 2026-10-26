"""Read-only layouts evidenced by the January/February 2026 ICA workbooks.

No publication, HTTP or database functions. All audit coordinates are 1-based.
"""
from decimal import Decimal
import re
import pandas as pd
try:
    from .ica_common import MONTHS, normalize, number, period, country_identity
except ImportError:
    from ica_common import MONTHS, normalize, number, period, country_identity


def text(value):
    return '' if pd.isna(value) else normalize(value)


def monthly_title(df, selected_period):
    first, _ = period(selected_period)
    month = MONTHS[int(first[5:7]) - 1]
    title = ' '.join(text(v) for v in df.iloc[:2, 0])
    if not re.search(r'\b' + month + r'\s+(?:de\s+)?' + first[:4] + r'\b', title):
        raise ValueError('Título no confirma el período estadístico solicitado')
    return title


def parent_aliases(parents):
    aliases = {}
    for key, display in parents.items():
        for alias in (normalize(key), normalize(display)):
            if alias in aliases and aliases[alias] != display:
                raise ValueError('Alias de rubro ambiguo')
            aliases[alias] = display
    return aliases


def parent_column(df, parents):
    aliases = parent_aliases(parents)
    candidates = []
    for col in range(len(df.columns)):
        found = {aliases[text(v)] for v in df.iloc[:, col] if text(v) in aliases}
        if found == set(parents.values()):
            candidates.append(col)
    if len(candidates) != 1:
        raise ValueError('No se identificó una única columna de padres oficiales')
    return candidates[0]


def monthly_column(df, selected_period):
    first, _ = period(selected_period)
    month, year = MONTHS[int(first[5:7]) - 1], first[:4]
    candidates = []
    for col in range(len(df.columns)):
        for row in range(min(6, len(df))):
            if text(df.iat[row, col]) != month:
                continue  # Never select an accumulated block by a substring.
            following = [(r, text(df.iat[r, col])) for r in range(row+1, min(row+3, len(df)))]
            if not any(re.fullmatch(year + r'[e*]?', v) for _, v in following):
                continue
            units = [(r, text(df.iat[r, col])) for r in range(row+1, min(row+4, len(df)))]
            unit_rows = [r for r, v in units if v in ('millones de usd', 'millones de dolares')]
            if len(unit_rows) == 1:
                candidates.append((col, unit_rows[0]))
    if len(candidates) != 1:
        raise ValueError('Bloque mensual/año/unidad ausente o ambiguo')
    return candidates[0]


def amount(value):
    result = number(value, localized=True)
    if result < 0:
        raise ValueError('Flujo negativo')
    return result


def reconcile(values, total, context):
    # Evidence: stored figures carry 8 decimal places, with tiny binary residues.
    # One last decimal per operand, not an economic percentage or display rounding.
    delta = sum((Decimal(str(v)) for v in values), Decimal(0)) - Decimal(str(total))
    tolerance = Decimal('0.00000001') * (len(values) + 1)
    if abs(delta) > tolerance:
        raise ValueError('Total incoherente: ' + context)
    return {'delta_million_usd': str(delta), 'tolerance_million_usd': str(tolerance)}


def parse_rubros(df, flow, parents, selected_period):
    monthly_title(df, selected_period)
    aliases = parent_aliases(parents)
    pcol = parent_column(df, parents)
    vcol, unitrow = monthly_column(df, selected_period)
    if pcol == 0 or pcol+1 >= vcol:
        raise ValueError('Estructura padre/hijo/importe no reconocida')
    childcol = pcol+1  # Documented adjacent hierarchy in these two editions.
    records, evidence, ignored = [], [], []
    found, total, remainder, current = set(), None, False, None
    _, label = period(selected_period)
    for row in range(unitrow+1, len(df)):
        p, child = text(df.iat[row, pcol]), df.iat[row, childcol]
        left = text(df.iat[row, pcol-1])
        raw = df.iat[row, vcol]
        if pd.isna(raw):
            # Notes/blank separators are classified explicitly, not economic rows.
            if p or text(child) or (left and not left.startswith(('nota:', 'fuente:'))):
                raise ValueError('Fila económica sin importe')
            ignored.append({'row': row+1, 'reason': 'note' if left else 'blank'})
            continue
        value = amount(raw)
        if left in ('total', 'total general') and not p and not text(child):
            if total is not None:
                raise ValueError('Total nacional duplicado')
            total = {'value': value, 'row': row+1, 'column': vcol+1}
            continue
        if p in aliases and not text(child):
            current = aliases[p]
            if current in found:
                raise ValueError('Padre duplicado')
            found.add(current)
            sub, role = 'TOTAL', 'parent_total'
        elif p == 'resto' and flow == 'Importacion' and not text(child):
            if remainder:
                raise ValueError('Resto agregado duplicado')
            remainder = True; current = 'Resto'; sub, role = 'TOTAL', 'aggregate_remainder'
        elif not p and text(child) and current and current != 'Resto':
            sub, role = str(child).strip(), 'subrubro'
        else:
            raise ValueError(f'Fila económica no clasificada: fila {row+1}')
        records.append({'rubro_principal': current, 'subrubro': sub, 'valor_usd': value,
                        'tipo_flujo': flow, 'fecha_informe': label})
        evidence.append({'record_index': len(records)-1, 'row': row+1, 'column': vcol+1, 'role': role})
    if found != set(parents.values()) or total is None:
        raise ValueError('Padres o total nacional incompletos')
    if flow == 'Importacion' and not remainder:
        raise ValueError('Falta Resto agregado de importaciones en el layout validado')
    parent_values = [r['valor_usd'] for r in records if r['subrubro']=='TOTAL']
    check = reconcile(parent_values, total['value'], flow)
    totals = {r['rubro_principal']: r['valor_usd'] for r in records if r['subrubro']=='TOTAL'}
    for r in records:
        if r['subrubro'] != 'TOTAL' and Decimal(str(r['valor_usd'])) > Decimal(str(totals[r['rubro_principal']])) + Decimal('0.00000002'):
            raise ValueError('Subrubro superior a su padre')
    df.attrs['ica_audit'] = {'flow': flow, 'value_column': vcol+1, 'national_total': total,
                             'reconciliation': check, 'evidence': evidence, 'excluded_rows': ignored,
                             'subrubros_sum_exhaustive': 'not_assumed'}
    return records


def ranking_sections(df):
    candidates = []
    labels = ('exportaciones', 'importaciones', 'saldo', 'intercambio')
    for row in range(min(6, len(df)-1)):
        positions = []
        for label in labels:
            cols = [c for c in range(len(df.columns)) if text(df.iat[row,c])==label]
            if len(cols)!=1:
                break
            positions.append(cols[0])
        if len(positions)==4 and all(text(df.iat[row+1,c])=='pais' and
                text(df.iat[row+1,c+1]) in ('millones de usd','millones de dolares')
                for c in positions if c+1<len(df.columns)) and all(c+1<len(df.columns) for c in positions):
            candidates.append((row+1, positions))
    if len(candidates)!=1:
        raise ValueError('Secciones de ranking/unidades ausentes o ambiguas')
    return candidates[0]


def parse_countries(df, selected_period):
    monthly_title(df, selected_period)
    headerrow, positions = ranking_sections(df)
    sections, audit = [], []
    for flow, col in zip(('exportaciones','importaciones','saldo','intercambio'), positions):
        totals=[r for r in range(headerrow+1,len(df)) if text(df.iat[r,col])=='total']
        rests=[r for r in range(headerrow+1,len(df)) if text(df.iat[r,col])=='resto']
        if len(totals)!=1 or len(rests)!=1 or totals[0]>=rests[0]:
            raise ValueError('Límites Total/Resto ausentes o ambiguos')
        begin,end=totals[0],rests[0]
        total=number(df.iat[begin,col+1],localized=True)
        rest=number(df.iat[end,col+1],localized=True)
        if flow!='saldo' and (total<0 or rest<0):
            raise ValueError('Total o Resto de flujo negativo')
        values={}; rows=[]
        for row in range(begin+1,end):
            rawname, raw=df.iat[row,col],df.iat[row,col+1]
            if pd.isna(rawname) or not text(rawname) or pd.isna(raw):
                raise ValueError('Ranking con observación incompleta')
            name=country_identity(rawname)
            if text(rawname) in ('total','resto') or name in values:
                raise ValueError('País duplicado o agregado dentro del ranking')
            value=number(raw,localized=True)
            if flow!='saldo' and value<0:
                raise ValueError('Flujo negativo')
            values[name]=value
            rows.append({'country': name, 'source_name': str(rawname), 'row': row+1, 'column': col+2})
        if not values:
            raise ValueError('Ranking vacío')
        for row in list(range(headerrow+1,begin))+list(range(end+1,len(df))):
            if not pd.isna(df.iat[row,col+1]):
                raise ValueError('Importe fuera de los límites auditados del ranking')
        check=reconcile(list(values.values())+[rest],total,flow)
        sections.append(values)
        audit.append({'flow':flow,'national_total':total,'remainder':rest,
                      'reconciliation':check,'observations':rows,'remainder_role':'aggregate_not_country',
                      'total_cell':{'row':begin+1,'column':col+2},
                      'remainder_cell':{'row':end+1,'column':col+2}})
    exports,imports,balances,_=sections
    reconcile([audit[0]['national_total'],-audit[1]['national_total']],audit[2]['national_total'],'saldo nacional')
    _,label=period(selected_period)
    records=[]
    for name in sorted(exports.keys()|imports.keys()):
        record={'pais':name,'fecha_informe':label}
        if name in exports:record['exportaciones']=exports[name]
        if name in imports:record['importaciones']=imports[name]
        if name in exports and name in imports:
            # Decimal arithmetic, no rounding to the displayed integer or 2 decimals.
            balance=Decimal(str(exports[name]))-Decimal(str(imports[name]))
            record['saldo_comercial']=float(balance)
            if name in balances:reconcile([exports[name],-imports[name]],balances[name],'saldo '+name)
        records.append(record)
    df.attrs['ica_audit']={'sections':audit,'partial_rows':sum('saldo_comercial' not in r for r in records)}
    return records


def rubros_title(df, flow):
    title = ' '.join(text(v) for v in df.iloc[:2, 0])
    if flow == 'Exportacion':
        return 'exportaciones por grandes rubros y principales subrubros' in title
    return 'importaciones, segun usos economicos' in title


def countries_title(df):
    return 'principales paises segun exportaciones, importaciones, saldo e intercambio' in text(df.iat[0,0])


def workbook_provenance(content, selected_period):
    """Edition from the index, not the file name; retain previous-month revisions."""
    from datetime import datetime
    import xlrd
    book = xlrd.open_workbook(file_contents=content)
    try:
        index = book.sheet_by_index(0)
        title = str(index.cell_value(0, 0))
        dates = re.findall(r'\((\d{2}/\d{2}/\d{4})\)', title)
        if len(dates) != 1:
            raise ValueError('Edición del archivo ausente o ambigua en el índice')
        edition = datetime.strptime(dates[0], '%d/%m/%Y').date().isoformat()
        national = []
        for sheet in book.sheets():
            if not sheet.nrows or not re.match(r'^cuadro 1\.', normalize(sheet.cell_value(0,0))):
                continue
            columns = {}
            for flow in ('exportaciones','importaciones','saldo'):
                cells = [(r,c) for r in range(min(4,sheet.nrows)) for c in range(sheet.ncols)
                         if normalize(sheet.cell_value(r,c))==flow]
                if len(cells)!=1:
                    raise ValueError('Cuadro nacional ambiguo')
                _,col = cells[0]
                years = {re.fullmatch(r'(\d{4})[e*]?',normalize(sheet.cell_value(r,col))).group(1)
                         for r in range(min(9,sheet.nrows))
                         if re.fullmatch(r'(\d{4})[e*]?',normalize(sheet.cell_value(r,col)))}
                if len(years)!=1:
                    raise ValueError('Año de serie nacional ambiguo')
                columns[flow]=(col, years.pop())
            if len({y for _,y in columns.values()})!=1:
                raise ValueError('Años no comparables en serie nacional')
            year=columns['exportaciones'][1]
            for row in range(sheet.nrows):
                label=normalize(sheet.cell_value(row,1))
                if label not in MONTHS:
                    continue
                values={flow:sheet.cell_value(row,col) for flow,(col,_) in columns.items()}
                if all(v=='' for v in values.values()):
                    continue
                values={flow:number(value) for flow,value in values.items()}
                reconcile([values['exportaciones'],-values['importaciones']],values['saldo'],'serie nacional')
                national.append({'statistical_period':f'{year}-{MONTHS.index(label)+1:02}',
                                 'source_edition_date':edition,'sheet':sheet.name,'row':row+1,
                                 'values_million_usd':values,
                                 'columns':{flow:col+1 for flow,(col,_) in columns.items()}})
        return {'source_edition_date':edition,'index_title':title,'statistical_period':selected_period,
                'national_series_observations':national,
                'revision_policy':'coexisting_editions_no_automatic_replacement'}
    finally:
        book.release_resources()


def cell_precision(content, cells):
    """Preserve stored doubles/repr and separate supported numeric display rounding.

    Locale-dependent separators and Excel layout rendering are not reconstructed.
    """
    from decimal import ROUND_HALF_UP
    import xlrd
    if not cells:
        return []
    book=xlrd.open_workbook(file_contents=content,formatting_info=True)
    try:
        result=[]
        for source in cells:
            sheet=book.sheet_by_name(source['sheet'])
            cell=sheet.cell(source['row']-1,source['column']-1)
            fmt=book.format_map[book.xf_list[cell.xf_index].format_key].format_str
            item=dict(source,stored_value=cell.value,stored_repr=repr(cell.value),excel_number_format=fmt,
                      display_numeric_value=None,stored_minus_display=None,
                      display_rendering='not_reconstructed')
            if isinstance(cell.value,(int,float)) and fmt in ('#,##0', '#,##0_ ;\\-#,##0\\ '):
                stored=Decimal(str(cell.value)); displayed=stored.quantize(Decimal('1'),rounding=ROUND_HALF_UP)
                item.update(display_numeric_value=str(displayed),stored_minus_display=str(stored-displayed),
                            display_rendering='integer_numeric_part_only_locale_not_assumed')
            result.append(item)
        return result
    finally:
        book.release_resources()
