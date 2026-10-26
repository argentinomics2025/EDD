"""Regressions from exact source-cell snapshots; separate optional original-XLS tests."""
import copy
import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import pandas as pd
from scripts import bot_ica as countries, bot_ica_rubros as rubros, ica_common as common
from scripts import ica_xls_layout as layout
from scripts.validate_ica_fixture import validate_local

ROOT = Path(__file__).parent / 'fixtures' / 'ica'
SPECS = {
    '2026-01': ('c10', 'c12', 'c19', 28, 16, 7057.25998206, 5070.29157643, 94.19150118),
    '2026-02': ('c12', 'c14', 'c21', 29, 18, 5962.28931127, 5174.26188015, 95.67913309),
}


class OfficialCellTests(unittest.TestCase):
    def setUp(self):
        guard = patch('socket.socket.connect', side_effect=AssertionError('No network'))
        guard.start(); self.addCleanup(guard.stop)
        self.fixtures = {p: json.loads((ROOT / (p+'-cells.json')).read_text()) for p in SPECS}

    def frame(self, period, sheet):
        return pd.DataFrame(copy.deepcopy(self.fixtures[period]['sheets'][sheet]))

    def test_countries_exact_union_totals_and_partial_rows(self):
        for p, (e, i, c, count, partial, exp, imp, resto) in SPECS.items():
            with self.subTest(period=p):
                frame=self.frame(p,c); records=countries.parse_countries(frame,p)
                self.assertEqual(len(records),count)
                self.assertEqual(sum('saldo_comercial' not in r for r in records),partial)
                common.validate_records(records,('fecha_informe','pais'))
                self.assertNotIn('Resto',[r['pais'] for r in records])
                audit=frame.attrs['ica_audit']['sections']
                self.assertEqual(audit[0]['national_total'],exp)
                self.assertEqual(audit[1]['national_total'],imp)
                self.assertEqual(len(audit[0]['observations']),20)
                self.assertEqual(len(audit[1]['observations']),20)
                for a in audit:
                    self.assertLess(abs(float(a['reconciliation']['delta_million_usd'])),0.000001)

    def test_rubros_counts_and_remainder_not_a_child(self):
        for p,(e,i,c,count,partial,exp,imp,resto) in SPECS.items():
            for sheet,flow,parents,total,expected_count in [(e,'Exportacion',rubros.EXPORTS,exp,51),
                                                           (i,'Importacion',rubros.IMPORTS,imp,27)]:
                with self.subTest(period=p,flow=flow):
                    df=self.frame(p,sheet)
                    rows=rubros.extraer_datos_rubros(df,flow,parents,p)
                    self.assertEqual(len(rows),expected_count)
                    self.assertEqual(len(df.attrs['ica_audit']['evidence']),len(rows))
                    self.assertEqual(df.attrs['ica_audit']['national_total']['value'],total)
                    remainder=[r for r in rows if r['rubro_principal']=='Resto']
                    if flow=='Importacion':
                        self.assertEqual(remainder[0]['valor_usd'],resto)
                        self.assertEqual(remainder[0]['subrubro'],'TOTAL')
                        self.assertEqual(df.attrs['ica_audit']['evidence'][-1]['role'],'aggregate_remainder')
                    else:self.assertEqual(remainder,[])

    def test_named_sheets_are_not_required(self):
        fixture=self.fixtures['2026-02']
        frames={'renamed_exports':pd.DataFrame(fixture['sheets']['c12']),
                'renamed_imports':pd.DataFrame(fixture['sheets']['c14']),
                'renamed_countries':pd.DataFrame(fixture['sheets']['c21'])}
        workbook=Mock();workbook.sheet_names=list(frames)
        with patch('pandas.read_excel',side_effect=lambda wb,name=None,**kwargs:frames[name or kwargs['sheet_name']].copy()):
            found=rubros.find_sheet(workbook,rubros.EXPORTS,'2026-02')
            self.assertEqual(found.attrs['ica_sheet_name'],'renamed_exports')
            self.assertEqual(countries.detectar_pestana_totales(workbook,'2026-02'),'renamed_countries')

    def test_wrong_month_is_rejected(self):
        for p,(e,i,c,*_) in SPECS.items():
            wrong='2026-02' if p=='2026-01' else '2026-01'
            with self.assertRaises(ValueError):countries.parse_countries(self.frame(p,c),wrong)
            with self.assertRaises(ValueError):rubros.extraer_datos_rubros(self.frame(p,e),'Exportacion',rubros.EXPORTS,wrong)

    def test_monthly_not_accumulated_and_not_previous_year(self):
        df=self.frame('2026-02','c12')
        rows=rubros.extraer_datos_rubros(df,'Exportacion',rubros.EXPORTS,'2026-02')
        self.assertEqual(rows[0]['valor_usd'],1749.75063598)
        self.assertNotEqual(rows[0]['valor_usd'],3838.38255594)
        self.assertNotEqual(rows[0]['valor_usd'],1617.36344713)
        df.iat[3,3]='2025*'
        with self.assertRaises(ValueError):rubros.extraer_datos_rubros(df,'Exportacion',rubros.EXPORTS,'2026-02')

    def test_monthly_unit_is_required_in_selected_column(self):
        df=self.frame('2026-02','c12');df.iat[4,3]='Miles de USD'
        with self.assertRaises(ValueError):rubros.extraer_datos_rubros(df,'Exportacion',rubros.EXPORTS,'2026-02')

    def test_unknown_parent_does_not_drop_money(self):
        df=self.frame('2026-01','c10');df.iat[6,1]='Productos primarios (XX)'
        with self.assertRaises(ValueError):rubros.extraer_datos_rubros(df,'Exportacion',rubros.EXPORTS,'2026-01')

    def test_orphan_child_and_unclassified_row_fail(self):
        df=self.frame('2026-01','c10');df.iat[7,1]='Otra categoría'
        with self.assertRaises(ValueError):rubros.extraer_datos_rubros(df,'Exportacion',rubros.EXPORTS,'2026-01')

    def test_missing_remainder_or_money_fails(self):
        df=self.frame('2026-01','c12');df.iat[33,3]=None
        with self.assertRaises(ValueError):rubros.extraer_datos_rubros(df,'Importacion',rubros.IMPORTS,'2026-01')
        df=self.frame('2026-01','c19');df.iat[7,1]=None
        with self.assertRaises(ValueError):countries.parse_countries(df,'2026-01')

    def test_missing_country_rank_row_fails_reconciliation(self):
        df=self.frame('2026-01','c19').drop(index=7).reset_index(drop=True)
        with self.assertRaises(ValueError):countries.parse_countries(df,'2026-01')

    def test_duplicate_country_and_amount_after_remainder_rejected(self):
        df=self.frame('2026-01','c19');df.iat[8,0]=df.iat[7,0]
        with self.assertRaises(ValueError):countries.parse_countries(df,'2026-01')
        df=self.frame('2026-01','c19');df.iat[28,1]=2
        with self.assertRaises(ValueError):countries.parse_countries(df,'2026-01')

    def test_no_rounding_of_country_balance_to_cents_of_millions(self):
        rows=countries.parse_countries(self.frame('2026-02','c21'),'2026-02')
        brazil=next(r for r in rows if r['pais']=='Brasil')
        self.assertEqual(brazil['saldo_comercial'],-222.47464694)
        self.assertNotEqual(brazil['saldo_comercial'],-222.47)

    def test_wrong_month_candidate_skipped_but_ambiguity_rejected(self):
        wb=Mock();wb.sheet_names=['jan','feb']
        frames={'jan':self.frame('2026-01','c10'),'feb':self.frame('2026-02','c12')}
        with patch('pandas.read_excel',side_effect=lambda wb,name,**kw:frames[name].copy()):
            self.assertEqual(rubros.find_sheet(wb,rubros.EXPORTS,'2026-02').attrs['ica_sheet_name'],'feb')
            frames['jan']=frames['feb'].copy()
            with self.assertRaises(ValueError):rubros.find_sheet(wb,rubros.EXPORTS,'2026-02')


class OriginalWorkbookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for target in ['socket.socket.connect', 'scripts.ica_common.download',
                       'scripts.ica_common.publish', 'scripts.ica_common.persist']:
            guard=patch(target,side_effect=AssertionError('No network or persistence in original XLS tests'))
            guard.start(); cls.addClassCleanup(guard.stop)
        roots=[Path(os.environ.get('ICA_OFFICIAL_FIXTURES_DIR','/workspace/attachments'))]
        cls.files={p.name:p for root in roots if root.exists() for p in root.rglob('*.xls')}
        names=['ica_cuadros_19_02_26.xls','ica_cuadros_19_03_26.xls']
        if not all(n in cls.files for n in names):
            raise unittest.SkipTest('Original XLS not available; use ICA_OFFICIAL_FIXTURES_DIR (no downloads)')
        cls.reports={}
        for p,fixture_path in [('2026-01','2026-01-cells.json'),('2026-02','2026-02-cells.json')]:
            fixture=json.loads((ROOT/fixture_path).read_text())
            path=cls.files[fixture['source_file']]
            if hashlib.sha256(path.read_bytes()).hexdigest()!=fixture['source_sha256']:
                raise AssertionError('Original XLS checksum changed')
            for kind in ['countries','rubros']:
                cls.reports[p,kind]=validate_local(path,kind,fixture['source_sha256'],p)

    def test_four_original_structural_validations(self):
        for (p,kind),report in self.reports.items():
            with self.subTest(period=p,kind=kind):
                self.assertTrue(report['parser_pass'])
                self.assertIsNone(report['reference_match'])
                self.assertFalse(report['writes_enabled'])
                self.assertEqual(report['source_metadata']['statistical_period'],p)

    def test_edition_is_read_from_index_not_filename(self):
        self.assertEqual(self.reports['2026-01','rubros']['source_metadata']['source_edition_date'],'2026-02-19')
        self.assertEqual(self.reports['2026-02','rubros']['source_metadata']['source_edition_date'],'2026-03-19')
        self.assertNotEqual(self.reports['2026-01','rubros']['dataset_id'],self.reports['2026-02','rubros']['dataset_id'])

    def test_january_editions_coexist_without_replacement(self):
        original=self.reports['2026-01','rubros']['source_metadata']['national_series_observations'][0]
        revised=self.reports['2026-02','rubros']['source_metadata']['national_series_observations'][0]
        self.assertEqual(original['statistical_period'],revised['statistical_period'])
        self.assertEqual(original['values_million_usd']['exportaciones'],7057.25998206)
        self.assertEqual(revised['values_million_usd']['exportaciones'],7245.29604746)
        self.assertNotEqual(original['source_edition_date'],revised['source_edition_date'])

    def test_original_precision_and_display_are_separate(self):
        cell=self.reports['2026-01','rubros']['cell_precision'][0]
        self.assertEqual(cell['stored_value'],2056.55148452)
        self.assertEqual(cell['display_numeric_value'],'2057')
        self.assertEqual(cell['stored_minus_display'],'-0.44851548')
        self.assertEqual(cell['excel_number_format'],'#,##0')

    def test_originals_unchanged_after_validation(self):
        for p in SPECS:
            fixture=json.loads((ROOT/(p+'-cells.json')).read_text())
            self.assertEqual(hashlib.sha256(self.files[fixture['source_file']].read_bytes()).hexdigest(),fixture['source_sha256'])

    def test_all_source_amounts_have_precision_and_edition(self):
        for (p,kind),report in self.reports.items():
            self.assertEqual(len(report['cell_precision']),88 if kind=='countries' else 80)
            for cell in report['cell_precision']:
                self.assertEqual(cell['statistical_period'],p)
                self.assertEqual(cell['dataset_id'],report['dataset_id'])
                self.assertIsNotNone(cell['display_numeric_value'])
                self.assertEqual(cell['source_edition_date'],report['source_metadata']['source_edition_date'])

    def test_snapshots_match_raw_xlrd_cells_not_parser_output(self):
        import xlrd
        for p in SPECS:
            fixture=json.loads((ROOT/(p+'-cells.json')).read_text())
            book=xlrd.open_workbook(self.files[fixture['source_file']])
            try:
                for name,expected in fixture['sheets'].items():
                    sheet=book.sheet_by_name(name)
                    actual=[[None if sheet.cell(r,c).ctype in (xlrd.XL_CELL_EMPTY,xlrd.XL_CELL_BLANK)
                             else sheet.cell_value(r,c) for c in range(sheet.ncols)]
                            for r in range(sheet.nrows)]
                    self.assertEqual(actual,expected,(p,name))
            finally:book.release_resources()

    def test_independent_coordinate_inventory_covers_every_rubro_amount_once(self):
        # Fixed ranges were inspected in the original documents, not derived
        # from the parser's selection. Includes master total, parents and children.
        from collections import Counter
        for p,(exports,imports,*_) in SPECS.items():
            report=self.reports[p,'rubros']
            expected={(exports,r,4) for r in range(6,58)} | {(imports,r,4) for r in range(7,35)}
            actual=Counter((c['sheet'],c['row'],c['column']) for c in report['cell_precision'])
            self.assertEqual(set(actual),expected)
            self.assertTrue(all(count==1 for count in actual.values()))
            self.assertEqual(len(report['records']),78)
            resto=[r for r in report['records'] if r['rubro_principal']=='Resto']
            self.assertEqual(len(resto),1)
            self.assertEqual(resto[0]['subrubro'],'TOTAL')

    def test_independent_country_reference_does_not_fill_missing_imports(self):
        import xlrd
        path=self.files['ica_cuadros_19_02_26.xls']
        book=xlrd.open_workbook(path)
        try:
            balance_sheet=book.sheet_by_name('c16')
            self.assertEqual(balance_sheet.cell_value(15,0),'Perú')
            self.assertEqual(balance_sheet.cell_value(15,3),30.34493893)
            peru=next(r for r in self.reports['2026-01','countries']['records'] if r['pais']=='Peru')
            self.assertEqual(peru['exportaciones'],balance_sheet.cell_value(15,1))
            self.assertNotIn('importaciones',peru)
            self.assertNotIn('saldo_comercial',peru)
        finally:book.release_resources()
