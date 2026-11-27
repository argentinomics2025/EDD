import unittest
from unittest.mock import patch
import xlrd
from scripts.ec022_bcra_uva import parse

class InvalidBook:
    def sheet_names(self): return ['Other']

class Cell:
    def __init__(self,value):
        self.value=value
        self.ctype=xlrd.XL_CELL_NUMBER if isinstance(value,(float,int)) else xlrd.XL_CELL_TEXT

class Sheet:
    ncols=6
    nrows=29
    values={(17,3):'UVA',(18,3):'Hipotecarios',(19,3):'Total',(21,3):'Monto',(21,4):'Tasa',
            (25,2):'prefecha',(25,3):'pasvar49',(25,4):'pasvar50',
            (27,2):202601,(27,3):0,(27,4):0,(28,2):202602,(28,3):120,(28,4):6.5}
    def cell_value(self,r,c): return self.values.get((r,c),'')
    def cell(self,r,c): return Cell(self.cell_value(r,c))

class Book:
    def sheet_names(self): return ['Datos']
    def sheet_by_name(self,name): return Sheet()

class UvaTests(unittest.TestCase):
    def test_rejects_unrecognized_workbook(self):
        with patch('scripts.ec022_bcra_uva.xlrd.open_workbook',return_value=InvalidBook()):
            with self.assertRaises(ValueError): parse(b'bad')
    def test_uva_scope_and_source_zero(self):
        with patch('scripts.ec022_bcra_uva.xlrd.open_workbook',return_value=Book()):
            result=parse(b'xls')
        self.assertEqual(result['scope'],'mortgages_uva')
        self.assertTrue(result['observations'][0]['zero_amount_rate_not_interpreted'])
        self.assertEqual(result['observations'][1]['annual_nominal_rate_percent'],'6.5')
