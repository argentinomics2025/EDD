import unittest
from unittest.mock import patch
from scripts.ec022_indec_historicos import parse_cvs, parse_salarios
from scripts.ec022_ripte_pdf import parse

class PdfPage:
    def extract_text(self, **kwargs):
        return ('1994\nJulio  $ 874,87   -   100\n'
                'Agosto $ 893,00   2,1%   102\n')

class PdfReader:
    pages=[PdfPage()]

class HistoricalSourceTests(unittest.TestCase):
    def test_ripte_preserves_published_missing_variation(self):
        with patch('scripts.ec022_ripte_pdf.PdfReader',return_value=PdfReader()):
            rows=parse(b'pdf','source')['observations']
        self.assertIsNone(rows[0]['monthly_percent'])
        self.assertEqual(rows[1]['monthly_percent'],'2.1')
    def test_ripte_rejects_inconsistent_change(self):
        class BadPage:
            def extract_text(self, **kwargs):
                return '1994\nJulio $ 100,00   -   100\nAgosto $ 200,00   1,0%   102\n'
        class BadReader: pages=[BadPage()]
        with patch('scripts.ec022_ripte_pdf.PdfReader',return_value=BadReader()):
            with self.assertRaises(ValueError): parse(b'pdf','source')
    def test_historic_xls_rejects_wrong_identity(self):
        class WrongBook:
            def sheet_names(self): return ['wrong']
            def sheets(self): return []
        with patch('scripts.ec022_indec_historicos.xlrd.open_workbook',return_value=WrongBook()):
            with self.assertRaises(ValueError): parse_cvs(b'xls')
            with self.assertRaises(ValueError): parse_salarios(b'xls')
