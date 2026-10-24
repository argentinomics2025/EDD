"""Carga exclusivamente series oficiales; sin estimaciones ni borrados."""
import argparse
from io import StringIO
import csv
from datetime import date
from decimal import Decimal, InvalidOperation
import math
try:
    from .ica_common import download, publish, cli, review_arguments
except ImportError:
    from ica_common import download, publish, cli, review_arguments

CSV_URL = 'https://infra.datos.gob.ar/catalog/sspm/dataset/74/distribution/74.3/download/intercambio-comercial-argentino-mensual.csv'
MAPPING = {
    'indice_tiempo': 'fecha',
    'ica_expo_totales': 'exportaciones_usd_millions',
    'ica_exportacion_productos_primarios': 'expo_primarios',
    'ica_exportacion_manufacturas_origen_agropecuario': 'expo_moa',
    'ica_exportacion_manufacturas_origen_industrial': 'expo_moi',
    'ica_exportacion_combustible_energia': 'expo_energia',
    'ica_importaciones_totales': 'importaciones_usd_millions',
    'ica_importaciones_bienes_capital': 'impo_bienes_capital',
    'ica_importaciones_bienes_intermedios': 'impo_bienes_intermedios',
    'ica_importaciones_combustibles_lubricantes': 'impo_combustibles',
    'ica_importaciones_piezas_accesorios_bienes_capital': 'impo_piezas_accesorios',
    'ica_importaciones_bienes_consumo': 'impo_bienes_consumo',
    'ica_importaciones_vehiculos_automotores_pasajeros': 'impo_vehiculos',
    'ica_saldo_comercial': 'saldo_usd_millions'
}


# Offline evidence only. None of these columns are added to publication records.
OFFLINE_COLUMNS = {
    'ica_importaciones_resto': 'aggregate_remainder_not_country',
    'ica_bienes_capital_partes_piezas': 'overlapping_aggregate_not_additive',
    'ica_bienes_intermedios_combustibles_lubricantes': 'overlapping_aggregate_not_additive',
    'ica_importaciones_bs_consumo_vehiculos_automotor_pasajeros': 'aggregate_scope_requires_metadata',
}
SOURCE_COLUMNS = tuple(MAPPING) + tuple(OFFLINE_COLUMNS)
EXPORT_COMPONENTS = ('ica_exportacion_productos_primarios', 'ica_exportacion_manufacturas_origen_agropecuario',
                     'ica_exportacion_manufacturas_origen_industrial', 'ica_exportacion_combustible_energia')
IMPORT_COMPONENTS = ('ica_importaciones_bienes_capital', 'ica_importaciones_bienes_intermedios',
                     'ica_importaciones_combustibles_lubricantes', 'ica_importaciones_piezas_accesorios_bienes_capital',
                     'ica_importaciones_bienes_consumo', 'ica_importaciones_vehiculos_automotores_pasajeros')
# Observed precision: up to eight decimal places plus tiny serialized float residues.
# Only the published total-total-balance identity is gated by this numeric bound.
BALANCE_NUMERIC_TOLERANCE = Decimal('0.00000001')


def read_csv_offline(content):
    """Preserve source strings and discrepancies separately from the unchanged DB field set.

    Reports are not upload payloads. Edition and historical methodology are unknown.
    """
    rows = list(csv.reader(StringIO(content.decode('utf-8-sig')), strict=True))
    if len(rows) < 2 or len(rows[0]) != len(set(rows[0])) or set(SOURCE_COLUMNS) - set(rows[0]):
        raise ValueError('CSV vacío, encabezados duplicados o columnas requeridas ausentes')
    header = rows[0]
    records, source_records, checks, seen = [], [], [], set()
    for line, cells in enumerate(rows[1:], 2):
        if len(cells) != len(header):
            raise ValueError(f'Cantidad de campos incorrecta en fila {line}')
        raw = dict(zip(header, cells))
        when = raw['indice_tiempo']
        try:
            parsed_date = date.fromisoformat(when)
        except ValueError as exc:
            raise ValueError('Fecha inválida') from exc
        if (parsed_date.isoformat() != when or parsed_date.day != 1 or parsed_date > date.today()
                or when in seen):
            raise ValueError('Fecha no mensual, futura o duplicada')
        seen.add(when)
        values = {}
        for col in SOURCE_COLUMNS:
            if col == 'indice_tiempo':
                continue
            try:
                value = Decimal(raw[col])
            except InvalidOperation as exc:
                raise ValueError(f'Importe inválido en {when}: {col}') from exc
            if not value.is_finite() or not math.isfinite(float(value)):
                raise ValueError('Importe no finito o no representable')
            if col != 'ica_saldo_comercial' and value < 0:
                raise ValueError('Flujo negativo')
            values[col] = value
        def total(columns):
            return sum((values[c] for c in columns), Decimal(0))
        def comparison(components, published):
            delta = components - published
            return {'computed_sum': str(components), 'published_total': str(published),
                    'delta': str(delta), 'discrepancy_recorded': delta != 0,
                    'cause': 'not_attributed', 'adjustment_applied': False}
        balance_sum = values['ica_expo_totales'] - values['ica_importaciones_totales']
        balance = comparison(balance_sum, values['ica_saldo_comercial'])
        balance['within_numeric_tolerance'] = abs(Decimal(balance['delta'])) <= BALANCE_NUMERIC_TOLERANCE
        if not balance['within_numeric_tolerance']:
            raise ValueError(f'Saldo publicado incoherente con totales en {when}; no se ajustaron valores')
        check = {'period': when,
                 'export_components': comparison(total(EXPORT_COMPONENTS), values['ica_expo_totales']),
                 'import_components_without_resto': comparison(total(IMPORT_COMPONENTS), values['ica_importaciones_totales']),
                 'import_components_with_resto': comparison(total(IMPORT_COMPONENTS + ('ica_importaciones_resto',)), values['ica_importaciones_totales']),
                 'published_balance': balance}
        for label, components, target in [
            ('capital_parts', ('ica_importaciones_bienes_capital', 'ica_importaciones_piezas_accesorios_bienes_capital'), 'ica_bienes_capital_partes_piezas'),
            ('intermediate_energy', ('ica_importaciones_bienes_intermedios', 'ica_importaciones_combustibles_lubricantes'), 'ica_bienes_intermedios_combustibles_lubricantes'),
            ('consumption_vehicles_resto_observed', ('ica_importaciones_bienes_consumo', 'ica_importaciones_vehiculos_automotores_pasajeros', 'ica_importaciones_resto'), 'ica_importaciones_bs_consumo_vehiculos_automotor_pasajeros')]:
            check[label] = comparison(total(components), values[target])
        record = {dest: when if col == 'indice_tiempo' else float(values[col]) for col, dest in MAPPING.items()}
        records.append(record)
        source_records.append({'source_row': line, 'period': when, 'values_as_published': raw})
        checks.append(check)
    minimum, maximum = min(seen), max(seen)
    cursor, last = date.fromisoformat(minimum), date.fromisoformat(maximum)
    missing_months = []
    while cursor <= last:
        if cursor.isoformat() not in seen:
            missing_months.append(cursor.isoformat())
        cursor = date(cursor.year + (cursor.month == 12), 1 if cursor.month == 12 else cursor.month + 1, 1)
    return {'records': records, 'source_records': source_records, 'economic_checks': checks,
            'columns': header,
            'column_disposition': {col: ('mapped_existing_field:' + MAPPING[col] if col in MAPPING else
                                        'offline_only:' + OFFLINE_COLUMNS[col] if col in OFFLINE_COLUMNS else
                                        'preserved_unclassified_source_column') for col in header},
            'coverage': {'rows': len(records), 'date_range': [minimum, maximum], 'missing_months': missing_months,
                         'ascending': [r['fecha'] for r in records] == sorted(seen)},
            'source_edition_date': None, 'methodological_cause': 'not_verified',
            'unit_context': 'million_USD_consistent_with_selected_XLS_not_certified_for_entire_series',
            'balance_numeric_tolerance_source_units': str(BALANCE_NUMERIC_TOLERANCE),
            'persistence_field_set_changed': False}


def parse_csv(content):
    """Compatibility view: original output fields, now using the published export total."""
    return read_csv_offline(content)['records']


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = review_arguments(parser).parse_args(argv)
    records = parse_csv(download(CSV_URL, 'infra.datos.gob.ar'))
    publish('datos_comex', records, ('fecha',), args.write, reviewed_sha256=args.reviewed_sha256)


if __name__ == '__main__':
    raise SystemExit(cli(main))
