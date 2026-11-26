import unittest
from datetime import datetime,timezone
from scripts.ec021_dollar_safe_writer import validate,TICKERS
NOW=datetime(2026,11,26,16,0,tzinfo=timezone.utc)
def rows():
    return [{"casa":h,"compra":100+i,"venta":105+i,"fechaActualizacion":"2026-11-26T12:00:00-03:00"} for i,h in enumerate(TICKERS)]
class Tests(unittest.TestCase):
    def test_complete(self):
        self.assertEqual(len(validate(rows(),NOW)),7)
    def test_missing(self):
        with self.assertRaises(ValueError):validate(rows()[:-1],NOW)
    def test_duplicate(self):
        with self.assertRaises(ValueError):validate(rows()+rows()[:1],NOW)
    def test_nan(self):
        x=rows();x[0]["venta"]="NaN"
        with self.assertRaises(ValueError):validate(x,NOW)
    def test_buy_above_sell(self):
        x=rows();x[0]["compra"]=1000
        with self.assertRaises(ValueError):validate(x,NOW)
    def test_no_timezone(self):
        x=rows();x[0]["fechaActualizacion"]="2026-11-26T12:00:00"
        with self.assertRaises(ValueError):validate(x,NOW)
    def test_future(self):
        x=rows();x[0]["fechaActualizacion"]="2026-11-27T12:00:00-03:00"
        with self.assertRaises(ValueError):validate(x,NOW)
    def test_old(self):
        x=rows();x[0]["fechaActualizacion"]="2026-11-15T12:00:00-03:00"
        with self.assertRaises(ValueError):validate(x,NOW)
    def test_mixed_day(self):
        x=rows();x[0]["fechaActualizacion"]="2026-11-25T12:00:00-03:00"
        with self.assertRaises(ValueError):validate(x,NOW)
