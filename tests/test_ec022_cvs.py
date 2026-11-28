import unittest
from unittest.mock import patch
import xlrd
from scripts.ec022_cvs import parse, MONTHS

class Cell:
    def __init__(self, value):
        self.value = value
        self.ctype = xlrd.XL_CELL_EMPTY if value == "" else (xlrd.XL_CELL_NUMBER if isinstance(value, (int, float)) else xlrd.XL_CELL_TEXT)

class Sheet:
    def __init__(self):
        self.rows = [[""] * 13 for _ in range(36)]
        self.rows[1][0] = "31 de octubre de 2016=100"
        self.rows[3][1] = "Año 2020"
        self.rows[4][1:] = list(MONTHS)
        for day in range(1, 32):
            self.rows[4 + day][0] = day
        self.rows[5][1] = 100.0
        self.rows[6][1] = 100.1
        self.nrows = len(self.rows)
    def cell(self, row, col): return Cell(self.rows[row][col])
    def cell_value(self, row, col): return self.rows[row][col]

class Book:
    datemode = 0
    def __init__(self): self.sheets = {n: Sheet() for n in ("publicacion_IS", "publicacion_SR")}
    def sheet_names(self): return list(self.sheets)
    def sheet_by_name(self, name): return self.sheets[name]

class CvsTests(unittest.TestCase):
    def test_both_series(self):
        with patch("scripts.ec022_cvs.xlrd.open_workbook", return_value=Book()):
            result = parse(b"official workbook")
        self.assertEqual(len(result["series"]["cvs_registrado"]), 2)
        self.assertEqual(result["series"]["cvs_total"][0]["date"], "2020-01-01")
    def test_gap_rejected(self):
        book = Book()
        book.sheets["publicacion_SR"].rows[6][1] = ""
        book.sheets["publicacion_SR"].rows[7][1] = 101.0
        with patch("scripts.ec022_cvs.xlrd.open_workbook", return_value=book):
            with self.assertRaises(ValueError): parse(b"x")
    def test_wrong_base_rejected(self):
        book = Book()
        book.sheets["publicacion_IS"].rows[1][0] = "another base"
        with patch("scripts.ec022_cvs.xlrd.open_workbook", return_value=book):
            with self.assertRaises(ValueError): parse(b"x")
