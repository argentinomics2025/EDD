"""COMEX source regressions: published totals, auditable discrepancies, unchanged DB fields."""
import copy
import csv
from decimal import Decimal
import hashlib
from io import StringIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts import bot_comex as comex, ica_common as common
from scripts.validate_ica_fixture import validate_local

FIXTURE=Path(__file__).parent/'fixtures'/'comex'/'source-rows.json'
LEGACY_FIELDS={'fecha','expo_primarios','expo_moa','expo_moi','expo_energia',
               'exportaciones_usd_millions','importaciones_usd_millions','impo_bienes_capital',
               'impo_bienes_intermedios','impo_combustibles','impo_piezas_accesorios',
               'impo_bienes_consumo','impo_vehiculos','saldo_usd_millions'}


def encode(rows, header=None):
    buffer=StringIO(); writer=csv.DictWriter(buffer,fieldnames=header or list(rows[0]))
    writer.writeheader();writer.writerows(rows)
    return buffer.getvalue().encode('utf-8')


class ComexOfflineTests(unittest.TestCase):
    def setUp(self):
        guard=patch('socket.socket.connect',side_effect=AssertionError('No network'))
        guard.start();self.addCleanup(guard.stop)
        self.fixture=json.loads(FIXTURE.read_text())
        self.rows=[r['values_as_published'] for r in self.fixture['selected_source_rows']]
        self.content=encode(self.rows,self.fixture['header'])
        self.report=comex.read_csv_offline(self.content)
        self.by_date={r['fecha']:r for r in self.report['records']}
        self.checks={r['period']:r for r in self.report['economic_checks']}

    def test_october_2016_published_total_is_not_replaced(self):
        row=self.by_date['2016-10-01'];check=self.checks['2016-10-01']
        self.assertEqual(row['exportaciones_usd_millions'],4729)
        self.assertEqual(check['export_components']['computed_sum'],'4728.0')
        self.assertEqual(Decimal(check['export_components']['delta']),-1)
        self.assertEqual(row['saldo_usd_millions'],-54)
        self.assertTrue(check['published_balance']['within_numeric_tolerance'])
        self.assertFalse(check['export_components']['adjustment_applied'])

    def test_january_2015_import_difference_is_reported_not_fixed(self):
        check=self.checks['2015-01-01']['import_components_with_resto']
        self.assertEqual(Decimal(check['delta']),Decimal('33.882706987800796'))
        self.assertEqual(check['cause'],'not_attributed')
        self.assertFalse(check['adjustment_applied'])
        raw=next(r for r in self.rows if r['indice_tiempo']=='2015-01-01')
        self.assertEqual(self.by_date['2015-01-01']['importaciones_usd_millions'],float(raw['ica_importaciones_totales']))

    def test_january_2026_published_values(self):
        row=self.by_date['2026-01-01']
        self.assertEqual(row['exportaciones_usd_millions'],7245.29604746)
        self.assertEqual(row['importaciones_usd_millions'],5056.67015725)
        self.assertEqual(row['saldo_usd_millions'],float('2188.6258902100008'))
        self.assertNotEqual(row['exportaciones_usd_millions'],7057.25998206)

    def test_february_2026_does_not_force_match_to_march_xls(self):
        row=self.by_date['2026-02-01']
        self.assertEqual(row['exportaciones_usd_millions'],5963.33901811)
        self.assertEqual(row['importaciones_usd_millions'],5166.57388213)
        self.assertEqual(row['saldo_usd_millions'],float('796.7651359800002'))
        self.assertNotEqual(row['exportaciones_usd_millions'],5962.28931127)
        self.assertIsNone(self.report['source_edition_date'])
        self.assertEqual(self.report['methodological_cause'],'not_verified')

    def test_january_editions_remain_distinct_from_csv(self):
        root=Path(__file__).parent/'fixtures'/'ica'
        jan=json.loads((root/'2026-01-cells.json').read_text())['sheets']
        feb=json.loads((root/'2026-02-cells.json').read_text())['sheets']
        original=Decimal(str(jan['c10'][5][3]))
        later_january=Decimal(str(feb['c12'][5][6]))-Decimal(str(feb['c12'][5][3]))
        source=next(r for r in self.rows if r['indice_tiempo']=='2026-01-01')
        self.assertEqual(Decimal(source['ica_expo_totales'])-original,Decimal('188.03606540'))
        self.assertEqual(Decimal(source['ica_expo_totales']),later_january)
        self.assertIsNone(self.report['source_edition_date'])
        self.assertEqual(self.report['methodological_cause'],'not_verified')

    def test_february_xls_differences_not_erased(self):
        root=Path(__file__).parent/'fixtures'/'ica'
        sheets=json.loads((root/'2026-02-cells.json').read_text())['sheets']
        source=next(r for r in self.rows if r['indice_tiempo']=='2026-02-01')
        self.assertEqual(Decimal(source['ica_expo_totales'])-Decimal(str(sheets['c12'][5][3])),Decimal('1.04970684'))
        self.assertEqual(Decimal(source['ica_importaciones_totales'])-Decimal(str(sheets['c14'][6][3])),Decimal('-7.68799802'))
        self.assertEqual(Decimal(source['ica_saldo_comercial'])-Decimal('788.02743112'),Decimal('8.7377048600002'))

    def test_all_source_fields_and_resto_survive_offline(self):
        self.assertEqual([r['values_as_published'] for r in self.report['source_records']],self.rows)
        self.assertEqual(self.report['source_records'][0]['values_as_published']['ica_importaciones_resto'],self.rows[0]['ica_importaciones_resto'])
        self.assertEqual(set(self.report['column_disposition']),set(self.fixture['header']))
        self.assertIn('offline_only',self.report['column_disposition']['ica_importaciones_resto'])

    def test_existing_publication_field_set_unchanged(self):
        for row in self.report['records']:
            self.assertEqual(set(row),LEGACY_FIELDS)
            self.assertNotIn('ica_importaciones_resto',row)
            self.assertNotIn('economic_checks',row)
        self.assertEqual(comex.parse_csv(self.content),self.report['records'])

    def test_published_balance_mismatch_fails_instead_of_adjustment(self):
        rows=copy.deepcopy(self.rows);rows[0]['ica_saldo_comercial']='100000'
        with self.assertRaises(ValueError):comex.parse_csv(encode(rows))

    def test_no_fallback_if_published_total_missing(self):
        rows=copy.deepcopy(self.rows)
        for row in rows:del row['ica_expo_totales']
        with self.assertRaises(ValueError):comex.parse_csv(encode(rows))
        rows=copy.deepcopy(self.rows);rows[0]['ica_expo_totales']=''
        with self.assertRaises(ValueError):comex.parse_csv(encode(rows))

    def test_invalid_offline_only_values_cannot_be_silently_discarded(self):
        for value in ['', 'NaN','Infinity','-1']:
            rows=copy.deepcopy(self.rows);rows[0]['ica_importaciones_resto']=value
            with self.subTest(value=value),self.assertRaises(ValueError):comex.read_csv_offline(encode(rows))

    def test_duplicate_dates_headers_and_truncated_rows_fail(self):
        with self.assertRaises(ValueError):comex.parse_csv(encode(self.rows+[self.rows[0]]))
        with self.assertRaises(ValueError):comex.parse_csv(b'indice_tiempo,indice_tiempo\n2026-01-01,2026-01-01\n')
        lines=self.content.decode().splitlines();lines[1]=lines[1].rsplit(',',1)[0]
        with self.assertRaises(ValueError):comex.parse_csv('\n'.join(lines).encode())

    def test_unknown_extra_column_preserved_but_not_interpreted(self):
        rows=copy.deepcopy(self.rows)
        for row in rows:row['unreviewed_metadata']='literal source value'
        report=comex.read_csv_offline(encode(rows))
        self.assertEqual(report['column_disposition']['unreviewed_metadata'],'preserved_unclassified_source_column')
        self.assertNotIn('unreviewed_metadata',report['records'][0])
        self.assertEqual(report['source_records'][0]['values_as_published']['unreviewed_metadata'],'literal source value')

    def test_offline_reader_never_calls_publication(self):
        with patch.object(comex,'publish',side_effect=AssertionError('No upload')):
            comex.read_csv_offline(self.content)
        with self.assertRaises(RuntimeError):common.ensure_writes_verified()

    def test_runner_exposes_source_audit_without_certifying_economics(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'source.csv';path.write_bytes(self.content)
            report=validate_local(path,'csv',hashlib.sha256(self.content).hexdigest())
        self.assertTrue(report['parser_pass'])
        self.assertIsNone(report['reference_match'])
        self.assertFalse(report['writes_enabled'])
        self.assertEqual(len(report['csv_evidence']['source_records']),4)
        self.assertEqual(len(report['csv_evidence']['economic_checks']),4)
        self.assertEqual(report['csv_evidence']['source_edition_date'],None)


class OriginalComexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for target in ['socket.socket.connect','scripts.ica_common.download','scripts.ica_common.publish','scripts.ica_common.persist']:
            guard=patch(target,side_effect=AssertionError('No network or persistence'))
            guard.start();cls.addClassCleanup(guard.stop)
        fixture=json.loads(FIXTURE.read_text());cls.fixture=fixture
        root=Path(os.environ.get('ICA_OFFICIAL_FIXTURES_DIR','/workspace/attachments'))
        files=list(root.rglob(fixture['source_file'])) if root.exists() else []
        if not files:raise unittest.SkipTest('Original CSV not available; no download attempted')
        cls.path=files[0];cls.content=cls.path.read_bytes()
        if hashlib.sha256(cls.content).hexdigest()!=fixture['source_sha256']:raise AssertionError('CSV hash changed')
        cls.report=comex.read_csv_offline(cls.content)

    def test_exact_original_rows_match_snapshot_not_parser_generated_values(self):
        raw=list(csv.DictReader(StringIO(self.content.decode())))
        for sample in self.fixture['selected_source_rows']:
            self.assertEqual(raw[sample['source_row']-2],sample['values_as_published'])

    def test_full_series_preserved_and_checked(self):
        raw=list(csv.DictReader(StringIO(self.content.decode('utf-8-sig'))))
        self.assertEqual([r['values_as_published'] for r in self.report['source_records']],raw)
        for line,(source,evidence,record) in enumerate(zip(raw,self.report['source_records'],self.report['records']),2):
            self.assertEqual(evidence['source_row'],line)
            self.assertEqual(set(record),LEGACY_FIELDS)
            self.assertEqual(record['exportaciones_usd_millions'],float(source['ica_expo_totales']))
            self.assertEqual(record['saldo_usd_millions'],float(source['ica_saldo_comercial']))
            expected={dest:source[col] if col=='indice_tiempo' else float(source[col])
                      for col,dest in comex.MAPPING.items()}
            self.assertEqual(record,expected)
        self.assertEqual(len(self.report['records']),417)
        self.assertEqual(len(self.report['source_records']),417)
        self.assertEqual(len(self.report['economic_checks']),417)
        self.assertEqual(self.report['coverage']['date_range'],['1992-01-01','2026-09-01'])
        self.assertEqual(self.report['coverage']['missing_months'],[])
        self.assertTrue(all(c['published_balance']['within_numeric_tolerance'] for c in self.report['economic_checks']))
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(),self.fixture['source_sha256'])
