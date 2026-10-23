"""EC-015: read-only local fixture inspection; no downloads, CLI robots or database."""
import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd
from . import ica_common as common
from . import bot_comex, bot_ica, bot_ica_rubros

KEYS = {
    'csv': ('fecha',),
    'countries': ('fecha_informe', 'pais'),
    'rubros': ('fecha_informe', 'tipo_flujo', 'rubro_principal', 'subrubro'),
}


def validate_local(path, kind, sha256, selected_period=None, reference_path=None):
    if kind not in KEYS:
        raise ValueError('Tipo de fixture desconocido')
    path = Path(path)
    if not path.is_file() or path.stat().st_size > 30_000_000:
        raise ValueError('Se requiere un archivo local de hasta 30 MB')
    content = path.read_bytes()
    actual_hash = hashlib.sha256(content).hexdigest()
    if actual_hash != sha256:
        raise ValueError('SHA256 del archivo no coincide con la adquisición revisada')
    report = {'kind': kind, 'source_sha256': actual_hash, 'source_authenticity': 'not_verified',
              'period': selected_period, 'schema_verified': False, 'writes_enabled': False}
    if kind == 'csv':
        if selected_period is not None:
            raise ValueError('CSV valida la serie completa; no filtra períodos')
        records = bot_comex.parse_csv(content)
        report['columns'] = list(pd.read_csv(path, nrows=0).columns)
        report['date_range'] = [min(r['fecha'] for r in records), max(r['fecha'] for r in records)]
    else:
        common.period(selected_period or '')
        workbook = common.read_workbook(content)
        try:
            report['sheets'] = []
            for name in workbook.sheet_names:
                frame = pd.read_excel(workbook, name, header=None)
                report['sheets'].append({'name': name, 'shape': list(frame.shape),
                    'first_15_rows': [[None if pd.isna(v) else str(v) for v in row]
                                      for row in frame.head(15).to_numpy()]})
            if kind == 'countries':
                sheet = bot_ica.detectar_pestana_totales(workbook)
                report['selected_sheet'] = sheet
                records = bot_ica.parse_countries(pd.read_excel(workbook, sheet, header=None), selected_period)
            else:
                records = []
                for flow, parents in [('Exportacion', bot_ica_rubros.EXPORTS),
                                      ('Importacion', bot_ica_rubros.IMPORTS)]:
                    frame = bot_ica_rubros.find_sheet(workbook, parents, selected_period)
                    records.extend(bot_ica_rubros.extraer_datos_rubros(frame, flow, parents, selected_period))
        finally:
            workbook.close()
    common.validate_records(records, KEYS[kind])
    report['parser_pass'] = True
    report['records'] = records
    report['rows'] = len(records)
    report['partial_countries'] = [r['pais'] for r in records if kind == 'countries' and
                                   ('exportaciones' not in r or 'importaciones' not in r)]
    report['reference_match'] = None
    if reference_path:
        reference = json.loads(Path(reference_path).read_text(encoding='utf-8'))
        for key in ('kind', 'period', 'source_sha256'):
            if reference.get(key) != report[key]:
                raise ValueError('Referencia no corresponde al archivo/tipo/período revisado')
        common.validate_records(reference['records'], KEYS[kind])
        actual = sorted(records, key=lambda r: tuple(r[k] for k in KEYS[kind]))
        expected = sorted(reference['records'], key=lambda r: tuple(r[k] for k in KEYS[kind]))
        # Numeric equality accepts 10 and 10.0; no automatic rounding/relaxation.
        if actual != expected:
            raise ValueError('Diferencia frente a referencia independiente; revisar filas y valores')
        report['reference_match'] = True
    report['compatibility'] = 'pending_official_metadata_and_schema_review'
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', required=True, type=Path)
    parser.add_argument('--kind', required=True, choices=KEYS)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--period')
    parser.add_argument('--reference', type=Path)
    args = parser.parse_args(argv)
    try:
        report = validate_local(args.file, args.kind, args.sha256, args.period, args.reference)
    except Exception as exc:
        print(json.dumps({'parser_pass': False, 'error_type': type(exc).__name__, 'detail': str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2))
    # No oracle is a pending check, never a passing semantic validation.
    return 0 if report['reference_match'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
