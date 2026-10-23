"""Carga exclusivamente series oficiales; sin estimaciones ni borrados."""
import argparse
from io import StringIO
import pandas as pd
try:
    from .ica_common import download, number, publish, cli, review_arguments
except ImportError:
    from ica_common import download, number, publish, cli, review_arguments

CSV_URL = 'https://infra.datos.gob.ar/catalog/sspm/dataset/74/distribution/74.3/download/intercambio-comercial-argentino-mensual.csv'
MAPPING = {
    'indice_tiempo': 'fecha',
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


def parse_csv(content):
    df = pd.read_csv(StringIO(content.decode('utf-8-sig')))
    missing = set(MAPPING) - set(df.columns)
    if missing or df.empty:
        raise ValueError('CSV vacío o columnas requeridas ausentes')
    df = df[list(MAPPING)].rename(columns=MAPPING)
    dates = pd.to_datetime(df['fecha'], errors='raise')
    if dates.isna().any() or not dates.dt.is_month_start.all() or dates.duplicated().any():
        raise ValueError('Fechas inválidas o duplicadas')
    if (dates > pd.Timestamp.today().normalize()).any():
        raise ValueError('Fecha futura')
    df['fecha'] = dates.dt.strftime('%Y-%m-%d')
    for col in set(MAPPING.values()) - {'fecha'}:
        df[col] = df[col].map(number)
        if col != 'saldo_usd_millions' and (df[col] < 0).any():
            raise ValueError('Flujo negativo')
    df['exportaciones_usd_millions'] = df[['expo_primarios', 'expo_moa', 'expo_moi', 'expo_energia']].sum(axis=1)
    expected = df['exportaciones_usd_millions'] - df['importaciones_usd_millions']
    # Components published in millions can differ due to rounding.
    if ((expected - df['saldo_usd_millions']).abs() > 3).any():
        raise ValueError('Saldo incoherente con los flujos')
    return df.to_dict(orient='records')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = review_arguments(parser).parse_args(argv)
    records = parse_csv(download(CSV_URL, 'infra.datos.gob.ar'))
    publish('datos_comex', records, ('fecha',), args.write, reviewed_sha256=args.reviewed_sha256)


if __name__ == '__main__':
    raise SystemExit(cli(main))
