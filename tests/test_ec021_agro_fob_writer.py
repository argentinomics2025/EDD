import copy
import unittest
from scripts.ec021_agro_fob_writer import decide,AgroFOBError
from scripts.ec021_agro_magyp_fob_reader import SOURCE,CODES

DATE="2026-11-27"
DATA=[
    {"fecha":DATE,"serie":"soja_fob_granel","posicion":"12019000190C","precio_usd_tn":493.0,"circular":"2109","embarque_desde":"2026-11-01","embarque_hasta":"2027-04-01","fuente":SOURCE},
    {"fecha":DATE,"serie":"maiz_fob_granel","posicion":"10059010120A","precio_usd_tn":211.0,"circular":"2109","embarque_desde":"2026-11-01","embarque_hasta":"2026-12-01","fuente":SOURCE},
    {"fecha":DATE,"serie":"trigo_pan_fob_granel","posicion":"10019900110W","precio_usd_tn":220.0,"circular":"2109","embarque_desde":"2026-11-01","embarque_hasta":"2026-11-01","fuente":SOURCE},
    {"fecha":DATE,"serie":"girasol_fob","posicion":"12060090910Y","precio_usd_tn":587.0,"circular":"2109","embarque_desde":"2026-11-01","embarque_hasta":"2026-11-01","fuente":SOURCE},
]


class FOBWriterDecisions(unittest.TestCase):
    def fails(self,batch=None,db=None,last=None,date=DATE):
        with self.assertRaises(AgroFOBError):
            decide(batch if batch is not None else DATA,
                   db if db is not None else [],last,date)
    def test_no_change_exact(self):
        self.assertEqual(decide(DATA,copy.deepcopy(DATA),DATE,DATE),"no_change")
    def test_identical_decimal_formats(self):
        rows=copy.deepcopy(DATA);rows[0]["precio_usd_tn"]="493.00"
        self.assertEqual(decide(DATA,rows,DATE,DATE),"no_change")
    def test_insert_on_next_business_day(self):
        self.assertEqual(decide(DATA,[],"2026-11-26",DATE),"insert")
    def test_insert_after_weekend(self):
        self.assertEqual(decide(DATA,[],"2026-11-24",DATE),"insert")
    def test_source_revision_rejected(self):
        rows=copy.deepcopy(DATA);rows[0]["precio_usd_tn"]=494
        self.fails(db=rows,last=DATE)
    def test_window_revision_rejected(self):
        rows=copy.deepcopy(DATA);rows[0]["embarque_hasta"]="2027-05-01"
        self.fails(db=rows,last=DATE)
    def test_circular_revision_rejected(self):
        rows=copy.deepcopy(DATA);rows[0]["circular"]="2108"
        self.fails(db=rows,last=DATE)
    def test_partial_db_rejected(self):
        self.fails(db=DATA[:3],last=DATE)
    def test_partial_source_rejected(self):
        self.fails(batch=DATA[:3],last="2026-11-26")
    def test_wrong_tariff_rejected(self):
        rows=copy.deepcopy(DATA);rows[0]["posicion"]="12019000299C"
        self.fails(batch=rows,last="2026-11-26")
    def test_wrong_date_rejected(self):
        self.fails(last="2026-11-26",date="2026-11-28")
    def test_source_older_rejected(self):
        self.fails(last="2026-11-28")
    def test_large_gap_rejected(self):
        self.fails(last="2026-11-01")
    def test_unapproved_bootstrap_rejected(self):
        self.fails()
    def test_duplicate_identity_rejected(self):
        rows=copy.deepcopy(DATA);rows[1]["serie"]=rows[0]["serie"]
        self.fails(batch=rows,last="2026-11-26")


if __name__=="__main__": unittest.main()
