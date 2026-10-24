"""Publica exclusivamente socios comerciales; sin borrar países existentes."""
import re
import pandas as pd
try:
    from .ica_common import (normalize, country_identity, number, period, validate_sheet, validate_value_column, download,
                             read_workbook, excel_arguments, publish, cli)
except ImportError:
    from ica_common import (normalize, country_identity, number, period, validate_sheet, validate_value_column, download,
                            read_workbook, excel_arguments, publish, cli)

try:
    from . import ica_xls_layout as xls_layout
except ImportError:
    import ica_xls_layout as xls_layout

EXCLUDED = {'total', 'resto', 'mercosur', 'union europea', 'asean', 'magreb',
            'usmca', 'pais', 'paises', 's/d', 'moi', 'moa', 'pp', 'cye'}


def country_name(value):
    if pd.isna(value):
        return None
    name = re.split(r'\(|\*', str(value))[0].strip()
    normalized = normalize(name)
    if (normalized in EXCLUDED or normalized.startswith(('fuente:', 'nota:', 'notas:'))
            or not 2 < len(name) < 60):
        return None
    return country_identity(name)


def detectar_pestana_totales(workbook, selected_period=None):
    candidates = []
    for sheet in workbook.sheet_names:
        df = pd.read_excel(workbook, sheet_name=sheet, nrows=15, header=None)
        text = normalize(' '.join(str(v) for v in df.to_numpy().flat))
        if 'principales paises' in text and 'segun exportaciones, importaciones, saldo e intercambio' in text:
            if selected_period is not None:
                try:
                    xls_layout.monthly_title(df, selected_period)
                except ValueError:
                    continue
            candidates.append(sheet)
    if len(candidates) != 1:
        raise ValueError('No se identificó una única hoja de socios comerciales')
    return candidates[0]


def parse_countries(df, selected_period):
    if xls_layout.countries_title(df):
        return xls_layout.parse_countries(df, selected_period)
    validate_sheet(df, selected_period)
    if len(df.columns) < 6:
        raise ValueError('Faltan columnas de socios')
    for column in (1, 5):
        validate_value_column(df, column, selected_period)
    sides = []
    for name_col, value_col in [(0, 1), (4, 5)]:
        values = {}
        for _, row in df.iloc[5:].iterrows():
            name = country_name(row[name_col])
            if not name:
                if pd.isna(row[name_col]) and not pd.isna(row[value_col]):
                    raise ValueError('Importe sin país identificado')
                continue
            if pd.isna(row[value_col]):
                raise ValueError('Importe faltante para un país; cero debe ser explícito')
            key = normalize(name)
            if key in values:
                raise ValueError('País duplicado')
            amount = number(row[value_col], localized=True)
            if amount < 0:
                raise ValueError('Flujo negativo')
            values[key] = (name, amount)
        sides.append(values)
    exports, imports = sides
    if not exports or not imports:
        raise ValueError('Ranking vacío o archivo incompleto')
    _, label = period(selected_period)
    records = []
    for key in sorted(exports.keys() | imports.keys()):
        row = {'pais': (exports.get(key) or imports[key])[0], 'fecha_informe': label}
        if key in exports:
            row['exportaciones'] = exports[key][1]
        if key in imports:
            row['importaciones'] = imports[key][1]
        if key in exports and key in imports:
            row['saldo_comercial'] = round(exports[key][1] - imports[key][1], 2)
        records.append(row)
    # Partial rows are observations for dry-run only, NOT a database contract.
    # Missing keys mean unobserved in this ranking, never a zero or an SQL NULL.
    return records


def main(argv=None):
    args = excel_arguments(__doc__).parse_args(argv)
    period(args.period)
    workbook = read_workbook(download(args.excel_url, 'www.indec.gob.ar'))
    try:
        sheet = detectar_pestana_totales(workbook, args.period)
        records = parse_countries(pd.read_excel(workbook, sheet, header=None), args.period)
    finally:
        workbook.close()
    if args.write and any('saldo_comercial' not in row for row in records):
        raise ValueError('Cobertura asimétrica: publicación bloqueada hasta validar Excel y contrato de datos')
    publish('socios_comerciales', records, ('fecha_informe', 'pais'), args.write,
            reviewed_sha256=args.reviewed_sha256)


if __name__ == '__main__':
    raise SystemExit(cli(main))
