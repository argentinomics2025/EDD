"""PR #1 regressions: asymmetric rankings, pre-connect redirect guard, hard write lock."""
from email.message import Message
from io import BytesIO, StringIO
import contextlib
import unittest
from unittest.mock import Mock, MagicMock, patch
from urllib.request import BaseHandler, HTTPRedirectHandler, Request, build_opener
from urllib.error import HTTPError
from urllib.response import addinfourl
import pandas as pd
from scripts import ica_common as common, bot_ica as countries


class ReviewTests(unittest.TestCase):
    def setUp(self):
        # No mocking of ensure_writes_verified in this class.
        guard = patch('socket.socket.connect', side_effect=AssertionError('Network forbidden'))
        guard.start()
        self.addCleanup(guard.stop)

    def sheet(self):
        return pd.DataFrame([
            ['Enero 2026 millones de dólares', 'Enero 2026', None, None, None, 'Enero 2026'],
            [None] * 6, [None] * 6, [None] * 6, [None] * 6,
            ['Brasil', 10, None, None, 'Brasil', 7],
            ['China', 4, None, None, 'India', 2],
        ])

    def test_different_rankings_keep_union_without_zeros(self):
        records = countries.parse_countries(self.sheet(), '2026-01')
        by_country = {row['pais']: row for row in records}
        self.assertEqual(set(by_country), {'Brasil', 'China', 'India'})
        self.assertEqual(by_country['Brasil']['saldo_comercial'], 3)
        self.assertEqual(by_country['China']['exportaciones'], 4)
        self.assertNotIn('importaciones', by_country['China'])
        self.assertNotIn('saldo_comercial', by_country['China'])
        self.assertNotIn('exportaciones', by_country['India'])
        self.assertEqual(by_country['India']['importaciones'], 2)
        self.assertNotIn('saldo_comercial', by_country['India'])

    def test_blank_ranking_cells_are_not_observations(self):
        df = self.sheet(); df.iloc[6, 4] = None; df.iloc[6, 5] = None
        records = countries.parse_countries(df, '2026-01')
        self.assertEqual({r['pais'] for r in records}, {'Brasil', 'China'})

    def test_named_country_missing_amount_still_fails(self):
        df = self.sheet(); df.iloc[6, 1] = None
        with self.assertRaises(ValueError): countries.parse_countries(df, '2026-01')

    def test_amount_without_country_fails(self):
        df = self.sheet(); df.iloc[6, 0] = None
        with self.assertRaises(ValueError): countries.parse_countries(df, '2026-01')

    def test_asymmetric_write_never_reaches_publisher(self):
        with patch.object(countries, 'download', return_value=b'fixture'), \
             patch.object(countries, 'read_workbook', return_value=Mock()), \
             patch.object(countries, 'detectar_pestana_totales', return_value='sheet'), \
             patch.object(countries.pd, 'read_excel', return_value=self.sheet()), \
             patch.object(countries, 'publish') as publish:
            with self.assertRaisesRegex(ValueError, 'Cobertura asimétrica'):
                countries.main(['--period', '2026-01', '--excel-url', 'https://www.indec.gob.ar/test.xls', '--write'])
        publish.assert_not_called()

    def redirect(self, location, status=302):
        class RecordingTransport(BaseHandler):
            handler_order = 100
            def __init__(self): self.visited = []
            def https_open(self, request):
                self.visited.append(request.full_url)
                headers = Message()
                if len(self.visited) == 1:
                    headers['Location'] = location
                    response = addinfourl(BytesIO(b''), headers, request.full_url, status)
                    response.msg = 'Redirect'
                else:
                    response = addinfourl(BytesIO(b'fixture'), headers, request.full_url, 200)
                    response.msg = 'OK'
                return response
            http_open = https_open
        transport = RecordingTransport()
        opener = build_opener(common.OfficialRedirectHandler('www.indec.gob.ar'), transport)
        return opener, transport

    def assert_redirect_blocked(self, location, code):
        opener, transport = self.redirect(location, code)
        # Python 3.10 has neither http_error_308 nor 308 redirect_request support:
        # it fails closed in urllib before our destination guard is invoked.
        # 3.12 handles 308, so our guard rejects the destination with ValueError.
        unsupported_308 = code == 308 and not hasattr(HTTPRedirectHandler, 'http_error_308')
        expected = HTTPError if unsupported_308 else ValueError
        with self.assertRaises(expected) as raised:
            opener.open('https://www.indec.gob.ar/start')
        if unsupported_308:
            self.assertEqual(raised.exception.code, 308)
            self.assertEqual(raised.exception.url, 'https://www.indec.gob.ar/start')
            raised.exception.close()
        # The security invariant is identical: no second request, even with 308.
        self.assertEqual(transport.visited, ['https://www.indec.gob.ar/start'])

    def test_external_redirect_rejected_before_target_contact(self):
        for code in [301, 302, 303, 307, 308]:
            with self.subTest(status=code):
                self.assert_redirect_blocked('https://evil.example/file.xls', code)

    def test_http_downgrade_rejected_before_target_contact(self):
        for code in [301, 302, 303, 307, 308]:
            with self.subTest(status=code):
                self.assert_redirect_blocked('http://www.indec.gob.ar/file.xls', code)

    def test_official_308_respects_native_runtime_support(self):
        opener, transport = self.redirect('/file.xls', 308)
        if hasattr(HTTPRedirectHandler, 'http_error_308'):
            with opener.open('https://www.indec.gob.ar/start') as response:
                self.assertEqual(response.read(), b'fixture')
            self.assertEqual(transport.visited, ['https://www.indec.gob.ar/start',
                                                'https://www.indec.gob.ar/file.xls'])
        else:
            with self.assertRaises(HTTPError) as raised:
                opener.open('https://www.indec.gob.ar/start')
            self.assertEqual(raised.exception.code, 308)
            raised.exception.close()
            self.assertEqual(transport.visited, ['https://www.indec.gob.ar/start'])

    def test_credentials_or_alternate_port_redirect_rejected(self):
        for url in ['https://user:pass@www.indec.gob.ar/file', 'https://www.indec.gob.ar:8443/file']:
            opener, transport = self.redirect(url)
            with self.assertRaises(ValueError): opener.open('https://www.indec.gob.ar/start')
            self.assertEqual(len(transport.visited), 1)

    def test_relative_official_redirect_allowed(self):
        opener, transport = self.redirect('/file.xls')
        with opener.open('https://www.indec.gob.ar/start') as response:
            self.assertEqual(response.read(), b'fixture')
        self.assertEqual(transport.visited, ['https://www.indec.gob.ar/start', 'https://www.indec.gob.ar/file.xls'])

    def test_download_uses_restricted_opener(self):
        opener = MagicMock()
        response = opener.open.return_value.__enter__.return_value
        response.url = 'https://www.indec.gob.ar/file'; response.read.return_value = b'fixture'
        with patch.object(common, 'build_opener', return_value=opener) as factory:
            self.assertEqual(common.download(response.url, 'www.indec.gob.ar'), b'fixture')
        self.assertIsInstance(factory.call_args.args[0], common.OfficialRedirectHandler)

    def test_valid_hash_cannot_unlock_publish(self):
        records = [{'fecha': '2026-01-01'}]; client = Mock()
        digest = common.payload_digest('datos_comex', records, ('fecha',))
        with self.assertRaisesRegex(RuntimeError, 'escrituras bloqueadas'):
            common.publish('datos_comex', records, ('fecha',), True, client, reviewed_sha256=digest)
        self.assertEqual(client.mock_calls, [])

    def test_direct_persist_also_locked(self):
        client = Mock()
        with self.assertRaises(RuntimeError):
            common.persist(client, 'datos_comex', [{'fecha': '2026-01-01'}], ('fecha',))
        self.assertEqual(client.mock_calls, [])

    def test_dry_run_still_available_under_hard_lock(self):
        client = Mock()
        with contextlib.redirect_stdout(StringIO()) as output:
            common.publish('datos_comex', [{'fecha': '2026-01-01'}], ('fecha',), client=client)
        self.assertIn('dry-run', output.getvalue())
        self.assertEqual(client.mock_calls, [])
