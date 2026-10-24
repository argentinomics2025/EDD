"""Offline tests. All real socket connections are forbidden."""
import copy
from io import StringIO
import unittest
from unittest.mock import Mock, patch
import pandas as pd
from scripts import ica_common as common
from scripts import bot_comex as comex
from scripts import bot_ica as countries
from scripts import bot_ica_rubros as rubros


class ICATests(unittest.TestCase):
    def setUp(self):
        gate = patch.object(common, 'ensure_writes_verified')
        gate.start()
        self.addCleanup(gate.stop)
        self.network = patch('socket.socket.connect', side_effect=AssertionError('Network forbidden'))
        self.network.start()
        self.addCleanup(self.network.stop)

    def sheet(self):
        return pd.DataFrame([
            ['Enero 2026 - millones de dólares', 'Enero 2026', None, None, None, 'Enero 2026'],
            [None] * 6, [None] * 6, [None] * 6, [None] * 6,
            ['Brasil', 12, None, None, 'Brasil', 7],
            ['Países Bajos', 4, None, None, 'Países Bajos', 2],
        ])

    def csv(self):
        data = {key: [1] for key in comex.SOURCE_COLUMNS}
        data['indice_tiempo'] = ['2026-01-01']
        data['ica_expo_totales'] = [4]
        data['ica_importaciones_totales'] = [3]
        data['ica_saldo_comercial'] = [1]
        return pd.DataFrame(data)

    def encode(self, df):
        return df.to_csv(index=False).encode()

    def test_numbers(self):
        self.assertEqual(common.number('1.234,5', localized=True), 1234.5)
        self.assertEqual(common.number(12000000), 12000000)
        self.assertEqual(common.number(0), 0)
        for value in [None, '', 's/d', '-', float('nan'), float('inf')]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                common.number(value)

    def test_period(self):
        self.assertEqual(common.period('2026-01'), ('2026-01-01', 'Enero 2026'))
        for value in ['2026-13', '01-2026', '2999-01']:
            with self.assertRaises(ValueError):
                common.period(value)

    def test_wrong_period_or_units(self):
        with self.assertRaises(ValueError):
            common.validate_sheet(self.sheet(), '2026-02')
        df = self.sheet(); df.iloc[0, 0] = 'Enero 2026 - dólares'
        with self.assertRaises(ValueError):
            common.validate_sheet(df, '2026-01')

    def test_html_not_excel(self):
        with self.assertRaises(ValueError):
            common.read_workbook(b'<html>503</html>')

    def test_countries_preserve_name_and_balance(self):
        rows = countries.parse_countries(self.sheet(), '2026-01')
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]['pais'], 'Países Bajos')
        self.assertEqual(rows[0]['saldo_comercial'], 5)

    def test_missing_country_counterpart_is_not_zero(self):
        df = self.sheet(); df.iloc[6, 4] = None
        with self.assertRaises(ValueError):
            countries.parse_countries(df, '2026-01')

    def test_wrong_value_column_period(self):
        df = self.sheet(); df.iloc[0, 1] = 'Enero 2025'
        with self.assertRaises(ValueError):
            countries.parse_countries(df, '2026-01')
        df.iloc[0, 1] = 'Enero 2026 acumulado'
        with self.assertRaises(ValueError):
            countries.parse_countries(df, '2026-01')

    def test_country_pipeline_offline(self):
        workbook = Mock()
        with patch.object(countries, 'download', return_value=b'fixture'), \
             patch.object(countries, 'read_workbook', return_value=workbook), \
             patch.object(countries, 'detectar_pestana_totales', return_value='socios'), \
             patch.object(countries.pd, 'read_excel', return_value=self.sheet()), \
             patch.object(countries, 'publish') as write:
            countries.main(['--period', '2026-01', '--excel-url', 'https://www.indec.gob.ar/test.xls'])
        self.assertEqual(write.call_args.args[0], 'socios_comerciales')
        self.assertFalse(write.call_args.args[3])
        workbook.close.assert_called_once()

    def test_bad_source_blocks_publication(self):
        with patch.object(comex, 'download', return_value=b'<html>error</html>'), \
             patch.object(comex, 'publish') as write:
            with self.assertRaises(ValueError):
                comex.main(['--write'])
        write.assert_not_called()

    def test_duplicate_country(self):
        df = self.sheet(); df.iloc[6, 0] = 'Brasil'
        with self.assertRaises(ValueError):
            countries.parse_countries(df, '2026-01')

    def test_csv_only_official_rows(self):
        rows = comex.parse_csv(self.encode(self.csv()))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['fecha'], '2026-01-01')
        self.assertEqual(rows[0]['exportaciones_usd_millions'], 4)

    def test_csv_invalid(self):
        base = self.csv()
        bad = []
        bad.append(base.drop(columns=['ica_importaciones_totales']))
        missing = base.copy(); missing.loc[0, 'ica_importaciones_totales'] = None; bad.append(missing)
        balance = base.copy(); balance.loc[0, 'ica_saldo_comercial'] = 100; bad.append(balance)
        bad.append(pd.concat([base, base]))
        wrong_date = base.copy(); wrong_date.loc[0, 'indice_tiempo'] = '2026-01-02'; bad.append(wrong_date)
        for df in bad:
            with self.subTest(columns=list(df.columns)), self.assertRaises(ValueError):
                comex.parse_csv(self.encode(df))

    def test_rubros_require_complete_parents_and_keep_zero(self):
        parents = {'productos primarios': 'PP'}
        df = pd.DataFrame([
            ['Enero 2026 millones de dólares', None, None, 'Enero 2026'],
            [None, 'Productos primarios', None, '1.234,5'],
            [None, None, 'Cereales', 0],
        ])
        rows = rubros.extraer_datos_rubros(df, 'Exportacion', parents, '2026-01')
        self.assertEqual([r['valor_usd'] for r in rows], [1234.5, 0])
        with self.assertRaises(ValueError):
            rubros.extraer_datos_rubros(df, 'Exportacion', rubros.EXPORTS, '2026-01')

    def test_rubros_pipeline_writes_only_rubros(self):
        def fixture(parents):
            return pd.DataFrame([
                ['Enero 2026 millones de dólares', None, None, 'Enero 2026'],
                *[[None, key, None, 10] for key in parents],
            ])
        workbook = Mock()
        with patch.object(rubros, 'download', return_value=b'fixture'), \
             patch.object(rubros, 'read_workbook', return_value=workbook), \
             patch.object(rubros, 'find_sheet', side_effect=[fixture(rubros.EXPORTS), fixture(rubros.IMPORTS)]), \
             patch.object(rubros, 'publish') as write:
            rubros.main(['--period', '2026-01', '--excel-url', 'https://www.indec.gob.ar/test.xls', '--write'])
        write.assert_called_once()
        self.assertEqual(write.call_args.args[0], 'comex_rubros')
        self.assertEqual(len(write.call_args.args[1]), 10)
        self.assertTrue(write.call_args.args[3])
        workbook.close.assert_called_once()

    def test_validation_before_writes(self):
        client = Mock()
        for rows in [[], [{'fecha': 'x'}, {'fecha': 'x'}]]:
            with self.assertRaises(ValueError):
                common.persist(client, 'datos_comex', rows, ('fecha',))
        client.table.assert_not_called()

    def test_dry_run_does_not_create_client(self):
        with patch.dict('os.environ', {}, clear=True), patch('builtins.__import__', wraps=__import__) as imports:
            common.publish('datos_comex', [{'fecha': '2026-01-01'}], ('fecha',))
        self.assertFalse(any(c.args[0] == 'supabase' for c in imports.call_args_list))

    def test_failure_never_deletes_existing_data(self):
        # Stateful adapter model: SDK request failure leaves stored rows intact.
        # This checks the client contract; real PostgreSQL rollback needs integration.
        class Store:
            def __init__(self):
                self.rows = [{'fecha': '2025-01-01', 'valor': 42},
                             {'fecha': '2026-01-01', 'valor': 8, 'other': 99}]
                self.fail = True
                self.calls = 0

            def table(self, name):
                return self

            def upsert(self, rows, on_conflict, ignore_duplicates):
                self.pending = copy.deepcopy(rows)
                self.calls += 1
                return self

            def execute(self):
                if self.fail:
                    raise RuntimeError('request failed')
                updated = {row['fecha']: copy.deepcopy(row) for row in self.rows}
                for row in self.pending:
                    updated.setdefault(row['fecha'], row)
                self.rows = list(updated.values())

        client = Store()
        snapshot = copy.deepcopy(client.rows)
        incoming = [{'fecha': '2026-01-01', 'valor': 9}]
        with self.assertRaises(RuntimeError):
            common.persist(client, 'datos_comex', incoming, ('fecha',))
        self.assertEqual(client.rows, snapshot)
        self.assertEqual(client.calls, 1)
        client.fail = False
        common.persist(client, 'datos_comex', incoming, ('fecha',))
        successful = copy.deepcopy(client.rows)
        common.persist(client, 'datos_comex', incoming, ('fecha',))
        self.assertEqual(client.rows, successful)
        self.assertEqual(client.rows[0], snapshot[0])
        self.assertEqual(client.rows[1]['other'], 99)
        self.assertEqual(client.rows[1]['valor'], 8)

    def test_single_upsert_preserves_unrelated_fields(self):
        client = Mock()
        row = {'fecha': '2026-01-01', 'expo_primarios': 4}
        common.persist(client, 'datos_comex', [row], ('fecha',))
        client.table.return_value.upsert.assert_called_once_with([row], on_conflict='fecha', ignore_duplicates=True)
        client.table.return_value.upsert.return_value.execute.assert_called_once()

    def test_large_load_rejected_before_any_write(self):
        client = Mock()
        with self.assertRaises(ValueError):
            common.persist(client, 'datos_comex', [{'fecha': str(i)} for i in range(5001)], ('fecha',))
        client.table.assert_not_called()

    def test_cli_nonzero_and_no_sensitive_exception_output(self):
        output = StringIO()
        with patch('sys.stderr', output):
            self.assertEqual(common.cli(Mock(side_effect=RuntimeError('secret value'))), 1)
        self.assertNotIn('secret value', output.getvalue())
        self.assertEqual(common.cli(Mock()), 0)

    def test_comex_pipeline_offline(self):
        with patch.object(comex, 'download', return_value=self.encode(self.csv())), patch.object(comex, 'publish') as write:
            comex.main([])
        write.assert_called_once()
        self.assertFalse(write.call_args.args[3])
        self.assertEqual(write.call_args.args[0], 'datos_comex')

    def test_download_errors_propagate(self):
        with patch.object(common, 'build_opener') as factory:
            factory.return_value.open.side_effect = TimeoutError
            with self.assertRaises(TimeoutError):
                common.download('https://www.indec.gob.ar/data.xls', 'www.indec.gob.ar')
        for url in ['http://www.indec.gob.ar/a', 'https://example.org/a']:
            with self.assertRaises(ValueError):
                common.download(url, 'www.indec.gob.ar')


if __name__ == '__main__':
    unittest.main()
