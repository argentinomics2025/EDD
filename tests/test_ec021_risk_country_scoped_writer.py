"""EC-021 risk-country scoped writer synthetic tests, no credentials or DB writes."""
import unittest
from datetime import date,timedelta
from unittest.mock import patch
from scripts.ec021_risk_country_scoped_writer import (
    PROJECT,ROLE,plan,validate_dsn,write_in_transaction,run
)
from scripts.ec021_risk_country_readonly import RiskSourceError

def series(n=30,start=date(2026,11,1)):
    return {(start+timedelta(days=i)).isoformat():800+i for i in range(n)}

class Cursor:
    def __init__(self,stored,headline,permissions=True):
        self.stored=stored
        self.headline=headline
        self.permissions=permissions
        self.queries=[]
        self.one=None
        self.many=[]
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def execute(self,sql,args=()):
        self.queries.append((sql,args))
        if "has_column_privilege" in sql:
            perms=(True,True,False,False,True,True,False,False,False,True,True)
            if not self.permissions: perms=(True,True,True,False,True,True,False,False,False,True,True)
            self.one=(ROLE,ROLE,*perms)
        elif "SELECT fecha,valor FROM public.historial_riesgo_pais ORDER BY" in sql:
            self.many=[(d,v) for d,v in sorted(self.stored.items(),reverse=True)[:30]]
        elif "SELECT sell_value FROM public.economic_indicators" in sql:
            self.one=(self.headline,)
        elif sql.strip().startswith("INSERT INTO public.historial_riesgo_pais"):
            self.one=(args[0],args[1])
        elif "UPDATE public.economic_indicators" in sql:
            self.many=[(args[0],)]
    def fetchone(self):return self.one
    def fetchall(self):return self.many

class Conn:
    def __init__(self,cur):self.cur=cur
    def cursor(self):return self.cur

class PlanTests(unittest.TestCase):
    def test_no_change(self):
        s=series()
        self.assertEqual(plan(s,s,829,today=date(2026,12,1)),[])
    def test_one_day_insert_only(self):
        s=series(21)
        stored=series(20)
        self.assertEqual(plan(s,stored,819,today=date(2026,12,1)),[{"fecha":"2026-11-21","valor":820}])
    def test_revision_rejected(self):
        s=series(21);old=series(20);old["2026-11-19"]=777
        with self.assertRaisesRegex(RiskSourceError,"Historical revision"):
            plan(s,old,819,today=date(2026,12,1))
    def test_headline_mismatch_rejected(self):
        with self.assertRaisesRegex(RiskSourceError,"Headline"):
            plan(series(21),series(20),700,today=date(2026,12,1))
    def test_multiple_new_days_rejected(self):
        with self.assertRaisesRegex(RiskSourceError,"More than one"):
            plan(series(22),series(20),819,today=date(2026,12,1))
    def test_future_day_rejected(self):
        with self.assertRaisesRegex(RiskSourceError,"date"):
            plan(series(21),series(20),819,today=date(2026,11,20))
    def test_gap_over_seven_days_rejected(self):
        old=series(20)
        s={**old,"2026-11-29":1000}
        with self.assertRaisesRegex(RiskSourceError,"date"):
            plan(s,old,819,today=date(2026,12,1))
    def test_dsn_strict_role(self):
        valid=f"postgresql://{ROLE}.{PROJECT}:test@aws-1-us-east-2.pooler.supabase.com:5432/postgres"
        self.assertEqual(validate_dsn(valid),valid)
        for bad in ("",f"postgresql://postgres:pw@db.{PROJECT}.supabase.co:5432/postgres",
                    f"postgresql://ec021_ripte_writer.{PROJECT}:pw@aws-1-us-east-2.pooler.supabase.com:5432/postgres",
                    "postgresql://x:pw@evil.example.com:5432/postgres"):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                validate_dsn(bad)
    def test_scoped_write_both_tables_atomic(self):
        cursor=Cursor(series(20),819)
        result=write_in_transaction(series(21),Conn(cursor))
        self.assertEqual(result["status"],"inserted")
        self.assertTrue(result["applied"])
        writes=[x[0].strip() for x in cursor.queries
                if x[0].strip().startswith(("INSERT","UPDATE","DELETE"))]
        self.assertEqual(len(writes),2)
        self.assertTrue(writes[0].startswith("INSERT INTO public.historial_riesgo_pais"))
        self.assertTrue(writes[1].startswith("UPDATE public.economic_indicators"))
        self.assertFalse(any("DELETE" in x for x in writes))
    def test_no_op_idempotent(self):
        cursor=Cursor(series(30),829)
        result=write_in_transaction(series(30),Conn(cursor))
        self.assertEqual(result["status"],"no_change")
        self.assertFalse(any(x[0].strip().startswith(("INSERT","UPDATE")) for x in cursor.queries))
    def test_unrestricted_role_rejected(self):
        cur=Cursor(series(20),819,permissions=False)
        with self.assertRaisesRegex(RuntimeError,"role not verified"):
            write_in_transaction(series(21),Conn(cur))
    def test_kill_switch(self):
        class HTTP:
            def get(self,*a,**kw):raise AssertionError("No source fetch should be needed for this test")
        # Gate must refuse apply even when all read-only validations pass.
        from scripts import ec021_risk_country_scoped_writer as w
        with patch.object(w,"fetch_json",return_value=([{"fecha":d,"valor":v} for d,v in series().items()],"sha")), \
             patch.object(w,"public_rows",return_value=series()), \
             patch.object(w,"public_summary",return_value=829), \
             patch.dict("os.environ",{},clear=True):
             with self.assertRaisesRegex(RuntimeError,"kill switch"):
                 run(apply=True,http=HTTP())

if __name__=="__main__":
    unittest.main()
