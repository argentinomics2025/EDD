"""Publica exclusivamente socios comerciales; sin borrar países existentes."""
import re
import pandas as pd
try:
    from .ica_common import (normalize, country_identity, number, period, validate_sheet, validate_value_column, download,
                             read_workbook, excel_arguments, publish, cli)
except ImportError:
    from ica_common import (normalize, country_identity, number, period, validate_sheet, validate_value_column, download,
                            read_workbook, excel_arguments, publish, cli)

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


def detectar_pestana_totales(workbook):
    candidates = []
    for sheet in workbook.sheet_names:
        df = pd.read_excel(workbook, sheet_name=sheet, nrows=15, header=None)
        text = normalize(' '.join(str(v) for v in df.to_numpy().flat))
        if 'principales paises' in text and 'segun exportaciones, importaciones, saldo e intercambio' in text:
            candidates.append(sheet)
    if len(candidates) != 1:
        raise ValueError('No se identificó una única hoja de socios comerciales')
    return candidates[0]


def parse_countries(df, selected_period):
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
    # Never infer a zero for a country absent from the opposite ranking.
    if not exports or exports.keys() != imports.keys():
        raise ValueError('Cobertura de países incompleta: faltan contrapartidas')
    _, label = period(selected_period)
    return [{'pais': exports[k][0], 'fecha_informe': label,
             'exportaciones': exports[k][1], 'importaciones': imports[k][1],
             'saldo_comercial': round(exports[k][1] - imports[k][1], 2)}
            for k in sorted(exports)]


def main(argv=None):
    args = excel_arguments(__doc__).parse_args(argv)
    period(args.period)
    workbook = read_workbook(download(args.excel_url, 'www.indec.gob.ar'))
    try:
        sheet = detectar_pestana_totales(workbook)
        records = parse_countries(pd.read_excel(workbook, sheet, header=None), args.period)
    finally:
        workbook.close()
    publish('socios_comerciales', records, ('fecha_informe', 'pais'), args.write,
            reviewed_sha256=args.reviewed_sha256)


if __name__ == '__main__':
    raise SystemExit(cli(main))
