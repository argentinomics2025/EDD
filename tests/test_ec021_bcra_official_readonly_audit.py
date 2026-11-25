"""EC-021 BCRA official catalog read-only audit contract."""
import unittest
from datetime import date
from scripts.ec021_bcra_official_readonly_audit import compare, IDS

def fixtures():
    entries=[{"idVariable":i,"ultFechaInformada":"2026-11-24","ultValorInformado":float(1000+i)} for i in IDS]
    entries.extend([{"idVariable":i,"ultFechaInformada":"2026-11-24","ultValorInformado":100} for i in range(100,130)])
    saved=[{"id_variable":i,"fecha":"2026-11-24","valor":str(1000+i)} for i in IDS]
    return {"status":200,"results":entries},saved

class TestOfficialBCRA(unittest.TestCase):
    def test_matching_without_writes(self):
        data,db=fixtures()
        result=compare(data,db,today=date(2026,11,25))
        self.assertTrue(all(x["status"]=="matched" for x in result["variables"].values()))
        self.assertFalse(result["writes_to_supabase"])
    def test_source_ahead_is_reported_not_written(self):
        data,db=fixtures()
        db[0]["fecha"]="2026-11-23"
        result=compare(data,db,today=date(2026,11,25))
        self.assertEqual(result["variables"][str(db[0]["id_variable"])]["status"],"source_ahead")
        self.assertFalse(result["updates_histories"])
    def test_revision_flagged(self):
        data,db=fixtures()
        db[0]["valor"]=999
        result=compare(data,db,today=date(2026,11,25))
        self.assertEqual(result["variables"][str(db[0]["id_variable"])]["status"],"same_date_value_mismatch")
    def test_missing_id_fails_closed(self):
        data,db=fixtures()
        db.pop()
        with self.assertRaises(RuntimeError):compare(data,db,today=date(2026,11,25))
    def test_duplicate_catalog_id_fails_closed(self):
        data,db=fixtures()
        data["results"].append(dict(data["results"][0]))
        with self.assertRaises(RuntimeError):compare(data,db,today=date(2026,11,25))
    def test_future_date_fails_closed(self):
        data,db=fixtures()
        data["results"][0]["ultFechaInformada"]="2026-11-30"
        with self.assertRaises(RuntimeError):compare(data,db,today=date(2026,11,25))
    def test_nonfinite_fails_closed(self):
        data,db=fixtures()
        data["results"][0]["ultValorInformado"]="NaN"
        with self.assertRaises(RuntimeError):compare(data,db,today=date(2026,11,25))

if __name__=="__main__":unittest.main()
