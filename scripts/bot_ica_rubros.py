"""Publica solo rubros. Totales y países pertenecen a sus robots respectivos."""
import pandas as pd
try:
    from .ica_common import (normalize, number, period, validate_sheet, validate_value_column, download,
                             read_workbook, excel_arguments, publish, cli)
except ImportError:
    from ica_common import (normalize, number, period, validate_sheet, validate_value_column, download,
                            read_workbook, excel_arguments, publish, cli)

EXPORTS = {'productos primarios': 'Productos primarios (PP)',
           'manufacturas de origen agropecuario': 'Manufacturas de origen agropecuario (MOA)',
           'manufacturas de origen industrial': 'Manufacturas de origen industrial (MOI)',
           'combustibles y energia': 'Combustibles y energía (CyE)'}
IMPORTS = {'bienes de capital': 'Bienes de capital (BK)',
           'bienes intermedios': 'Bienes intermedios (BI)',
           'combustibles y lubricantes': 'Combustibles y lubricantes (CyL)',
           'piezas y accesorios para bienes de capital': 'Piezas y accesorios para bienes de capital (PyA)',
           'bienes de consumo': 'Bienes de consumo (BC)',
           'vehiculos automotores de pasajeros': 'Vehículos automotores de pasajeros (VA)'}


# Source values are in millions of USD. Allow at most one million difference
# between independently rounded parent/child (0.5 + 0.5), never a percentage.
# No sum of children is assumed: they may be overlapping or non-exhaustive.
ROUNDING_UNIT = 1.0


def validate_hierarchy(records, *, disjoint=False, exhaustive=False):
    totals = {r['rubro_principal']: r['valor_usd'] for r in records if r['subrubro'] == 'TOTAL'}
    children = {}
    for row in records:
        if row['subrubro'] == 'TOTAL':
            continue
        parent, value = row['rubro_principal'], row['valor_usd']
        if parent not in totals or value > totals[parent] + ROUNDING_UNIT:
            raise ValueError('Subrubro superior al total más tolerancia de redondeo')
        children.setdefault(parent, []).append(value)
    # Enable these checks only with a reviewed source partition specification.
    if exhaustive and not disjoint:
        raise ValueError('Una partición exhaustiva requiere estructura disjunta confirmada')
    for parent, values in children.items():
        tolerance = (len(values) + 1) * ROUNDING_UNIT / 2
        delta = sum(values) - totals[parent]
        if disjoint and delta > tolerance:
            raise ValueError('Suma de subtotales disjuntos superior al total')
        if exhaustive and abs(delta) > tolerance:
            raise ValueError('Partición exhaustiva incoherente')
    if exhaustive and set(children) != set(totals):
        raise ValueError('Faltan subtotales de una partición exhaustiva')


def extraer_datos_rubros(df, flow, parents, selected_period):
    validate_sheet(df, selected_period)
    if len(df.columns) < 4:
        raise ValueError('Faltan columnas de rubros')
    validate_value_column(df, 3, selected_period)
    _, label = period(selected_period)
    records, found = [], set()
    parent = None
    for _, row in df.iterrows():
        title = normalize(row[1]) if not pd.isna(row[1]) else ''
        child = str(row[2]).strip() if not pd.isna(row[2]) else ''
        matched = next((key for key in parents if title == key), None)
        if matched:
            if matched in found:
                raise ValueError('Rubro principal duplicado')
            found.add(matched)
            parent = parents[matched]
            child = 'TOTAL'
        elif title:
            # An unknown parent must not attach children to the previous one.
            parent = None
            continue
        elif not parent or not child or 'total' in normalize(child):
            continue
        value = number(row[3], localized=True)
        if value < 0:
            raise ValueError('Rubro negativo')
        records.append({'rubro_principal': parent, 'subrubro': child, 'valor_usd': value,
                        'tipo_flujo': flow, 'fecha_informe': label})
    if found != set(parents):
        raise ValueError('Faltan rubros principales esperados')
    validate_hierarchy(records)
    return records


def find_sheet(workbook, parents, selected_period):
    matches = []
    for sheet in workbook.sheet_names:
        df = pd.read_excel(workbook, sheet, header=None)
        if len(df.columns) < 4:
            continue
        labels = {normalize(v) for v in df.iloc[:, 1].dropna()}
        if set(parents).issubset(labels):
            # Some reports contain both current and accumulated tables.
            # Do not choose one silently when detection is ambiguous.
            validate_sheet(df, selected_period)
            matches.append(df)
    if len(matches) != 1:
        raise ValueError('No se identificó una única hoja mensual de rubros')
    return matches[0]


def main(argv=None):
    args = excel_arguments(__doc__).parse_args(argv)
    period(args.period)
    workbook = read_workbook(download(args.excel_url, 'www.indec.gob.ar'))
    try:
        records = []
        for flow, parents in [('Exportacion', EXPORTS), ('Importacion', IMPORTS)]:
            records.extend(extraer_datos_rubros(find_sheet(workbook, parents, args.period),
                                              flow, parents, args.period))
    finally:
        workbook.close()
    publish('comex_rubros', records,
            ('fecha_informe', 'tipo_flujo', 'rubro_principal', 'subrubro'), args.write,
            reviewed_sha256=args.reviewed_sha256)


if __name__ == '__main__':
    raise SystemExit(cli(main))
