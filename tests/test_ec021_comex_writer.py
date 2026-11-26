import sys
import unittest
from decimal import Decimal
from datetime import date
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from ec021_comex_writer import compare_existing,prev_month,next_month,AMOUNT_COLS

class WriterUnitTests(unittest.TestCase):
    def setUp(self):
        self.row={key:Decimal("100.000") for key in AMOUNT_COLS}
        self.src={key:"100.000" for key in AMOUNT_COLS}
        self.sha="a"*64
    def test_idempotent_same_edition(self):
        self.assertEqual(compare_existing(self.row,self.src,self.sha,self.sha),"no_change")
    def test_missing_month_needs_insert(self):
        self.assertEqual(compare_existing(None,self.src,self.sha,None),"insert")
    def test_changed_value_fails_closed(self):
        self.src["exportaciones_usd_millions"]="100.001"
        with self.assertRaisesRegex(ValueError,"revision"):
            compare_existing(self.row,self.src,self.sha,self.sha)
    def test_changed_edition_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"hash changed"):
            compare_existing(self.row,self.src,self.sha,"b"*64)
    def test_month_rollover(self):
        self.assertEqual(prev_month("2027-01-01"),date(2026,12,1))
        self.assertEqual(next_month(date(2026,12,1)),date(2027,1,1))
        self.assertEqual(next_month(date(2026,10,1)),date(2026,11,1))
if __name__=="__main__":unittest.main()
