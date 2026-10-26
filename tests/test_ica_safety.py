"""Regression tests for reviewed payloads, identities and hierarchy assumptions."""
import contextlib
from io import StringIO
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
import pandas as pd
from scripts import ica_common as common, bot_ica as countries, bot_ica_rubros as rubros


class SafetyTests(unittest.TestCase):
    def setUp(self):
        gate = patch.object(common, 'ensure_writes_verified')
        gate.start()
        self.addCleanup(gate.stop)
        self.network = patch('socket.socket.connect', side_effect=AssertionError('Network forbidden'))
        self.network.start()
        self.addCleanup(self.network.stop)

    def records(self):
        return [{'fecha': '2026-01-01', 'exportaciones_usd_millions': 12}]

    def test_review_digest_stable_across_row_order(self):
        records = self.records() + [{'fecha': '2026-02-01', 'exportaciones_usd_millions': 15}]
        self.assertEqual(common.payload_digest('datos_comex', records, ('fecha',)),
                         common.payload_digest('datos_comex', list(reversed(records)), ('fecha',)))

    def test_write_requires_reviewed_hash(self):
        client = Mock()
        for digest in [None, '0' * 64]:
            with self.subTest(digest=digest), self.assertRaises(ValueError):
                common.publish('datos_comex', self.records(), ('fecha',), True,
                               client, reviewed_sha256=digest)
        self.assertEqual(client.mock_calls, [])

    def test_review_binds_payload_table_and_keys(self):
        records = self.records()
        digest = common.payload_digest('datos_comex', records, ('fecha',))
        records[0]['exportaciones_usd_millions'] = 13
        client = Mock()
        with self.assertRaises(ValueError):
            common.publish('datos_comex', records, ('fecha',), True, client,
                           reviewed_sha256=digest)
        with self.assertRaises(ValueError):
            common.publish('other', self.records(), ('fecha',), True, client,
                           reviewed_sha256=digest)
        self.assertEqual(client.mock_calls, [])

    def test_explicit_reviewed_write_still_cannot_overwrite_history(self):
        records = self.records()
        client = Mock()
        digest = common.payload_digest('datos_comex', records, ('fecha',))
        with contextlib.redirect_stdout(StringIO()):
            common.publish('datos_comex', records, ('fecha',), True, client,
                           reviewed_sha256=digest)
        client.table.return_value.upsert.assert_called_once_with(
            records, on_conflict='fecha', ignore_duplicates=True)

    def test_dry_run_reports_reviewable_records_and_hash(self):
        output = StringIO(); client = Mock()
        with contextlib.redirect_stdout(output):
            common.publish('datos_comex', self.records(), ('fecha',), client=client)
        self.assertIn('exportaciones_usd_millions', output.getvalue())
        self.assertIn(common.payload_digest('datos_comex', self.records(), ('fecha',)), output.getvalue())
        self.assertEqual(client.mock_calls, [])

    def test_duplicates_case_whitespace_accents_and_known_aliases(self):
        for left, right in [('Brasil', ' BRASIL '), ('Estados Unidos', 'Estados   Unidos'),
                            ('Estados Unidos', 'Estados Unidos de América'),
                            ('Vietnam', 'Viet Nam'), ('Países Bajos', 'paises bajos')]:
            records = [{'fecha_informe': 'Enero 2026', 'pais': name} for name in [left, right]]
            with self.subTest(names=(left, right)), self.assertRaises(ValueError):
                common.validate_records(records, ('fecha_informe', 'pais'))

    def test_rubro_duplicates_normalized(self):
        records = [{'fecha_informe': 'Enero 2026', 'tipo_flujo': 'Exportacion',
                    'rubro_principal': 'PP', 'subrubro': name} for name in ['Cereales', ' CEREALES ']]
        with self.assertRaises(ValueError):
            common.validate_records(records, ('fecha_informe', 'tipo_flujo', 'rubro_principal', 'subrubro'))

    def test_canonical_country_alias_stable_between_runs(self):
        self.assertEqual(common.country_identity(' VIET NAM '), common.country_identity('Vietnam'))
        self.assertEqual(common.country_identity('Brasil'), common.country_identity('BRASIL'))
        self.assertNotEqual(common.country_identity('Congo'), common.country_identity('República Democrática del Congo'))

    def country_sheet(self, value):
        return pd.DataFrame([
            ['Enero 2026 millones de dólares', 'Enero 2026', None, None, None, 'Enero 2026'],
            [None] * 6, [None] * 6, [None] * 6, [None] * 6,
            ['Brasil', value, None, None, 'Brasil', value],
        ])

    def test_zero_is_valid_missing_is_not(self):
        result = countries.parse_countries(self.country_sheet(0), '2026-01')
        self.assertEqual(result[0]['exportaciones'], 0)
        for value in [None, '', '-', 's/d']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                countries.parse_countries(self.country_sheet(value), '2026-01')

    def hierarchy(self, amounts):
        return [{'rubro_principal': 'PP', 'subrubro': 'TOTAL', 'valor_usd': 10},
                *[{'rubro_principal': 'PP', 'subrubro': str(i), 'valor_usd': value}
                  for i, value in enumerate(amounts)]]

    def test_rounding_tolerance_boundary(self):
        rubros.validate_hierarchy(self.hierarchy([11]))
        with self.assertRaises(ValueError):
            rubros.validate_hierarchy(self.hierarchy([11.01]))

    def test_do_not_assume_exhaustive_or_disjoint(self):
        rubros.validate_hierarchy(self.hierarchy([8, 8]))
        with self.assertRaises(ValueError):
            rubros.validate_hierarchy(self.hierarchy([8, 8]), disjoint=True)
        rubros.validate_hierarchy(self.hierarchy([2, 3]), disjoint=True)
        with self.assertRaises(ValueError):
            rubros.validate_hierarchy(self.hierarchy([2, 3]), disjoint=True, exhaustive=True)
        rubros.validate_hierarchy(self.hierarchy([5, 5]), disjoint=True, exhaustive=True)

    def test_wrong_or_mixed_units_fail(self):
        for label in ['Enero 2026 miles de dólares', 'Enero 2026 millones de pesos',
                      'Enero 2026 millones de dólares y miles de dólares']:
            df = self.country_sheet(1); df.iloc[0, 0] = label
            with self.subTest(units=label), self.assertRaises(ValueError):
                countries.parse_countries(df, '2026-01')

    def test_workflow_write_gates_and_shell_syntax(self):
        import subprocess
        for name in ['bot_comex.yml', 'bot_ica_rubros.yml', 'prueba_ica.yml']:
            text = (Path(__file__).resolve().parents[1] / '.github/workflows' / name).read_text()
            self.assertIn("github.event_name == 'workflow_dispatch' && inputs.write", text)
            self.assertIn('--reviewed-sha256 "$REVIEWED_SHA256"', text)
            # Execute only the shell gate with a stub Python, never an actual robot.
            script = text.split('        run: |\n', 1)[1]
            script = '\n'.join(line[10:] for line in script.splitlines())
            script = 'python() { printf "%s\\n" "$@"; }\n' + script
            base = {'APPLY': 'false', 'REVIEWED_SHA256': '', 'ICA_PERIOD': '2026-01',
                    'ICA_EXCEL_URL': 'https://www.indec.gob.ar/fixture.xls'}
            result = subprocess.run(['/bin/bash', '-c', script], env=base, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn('--write', result.stdout)
            base['APPLY'] = 'true'
            result = subprocess.run(['/bin/bash', '-c', script], env=base, text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            base['REVIEWED_SHA256'] = 'a' * 64
            result = subprocess.run(['/bin/bash', '-c', script], env=base, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('--write', result.stdout)

    def test_no_success_on_write_failure(self):
        client = Mock()
        client.table.return_value.upsert.return_value.execute.side_effect = RuntimeError('failed')
        output = StringIO()
        digest = common.payload_digest('datos_comex', self.records(), ('fecha',))
        with contextlib.redirect_stdout(output), self.assertRaises(RuntimeError):
            common.publish('datos_comex', self.records(), ('fecha',), True, client,
                           reviewed_sha256=digest)
        self.assertNotIn('OK:', output.getvalue())
        client.table.return_value.delete.assert_not_called()

    def test_truncated_excel_fails(self):
        with self.assertRaises(Exception):
            common.read_workbook(bytes.fromhex('d0cf11e0a1b11ae1'))
