"""EC-021 read-only credential probe tests; no network or database."""
import os
import unittest
from unittest.mock import patch

from scripts.ec021_risk_pg_connection_probe import check
from scripts.ec021_risk_country_scoped_writer import PROJECT, ROLE

class FakeCursor:
    def __init__(self, allow=True):
        self.allow=allow
        self.executions=[]
        self.single=None
        self.many=None
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def execute(self,query,*args):
        self.executions.append(query)
        if "has_column_privilege" in query:
            permissions=[True,True,False,False,True,True,False,False,False,True,True]
            if not self.allow:permissions[2]=True
            self.single=(ROLE,ROLE,*permissions)
        elif query.startswith("SELECT fecha, valor"):
            self.many=[("2026-11-24",1094),("2026-11-23",1035)]
        elif query.startswith("SELECT sell_value"):
            self.single=(1094,)
        elif "transaction_read_only" in query:
            self.single=("on",)
        elif query != "SET TRANSACTION READ ONLY":
            raise AssertionError("Unexpected SQL query")
    def fetchone(self):return self.single
    def fetchall(self):return self.many

class FakeConn:
    def __init__(self,cur):
        self.cur=cur
        self.rolled_back=False
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def cursor(self):return self.cur
    def rollback(self):self.rolled_back=True

class PGConnectionTests(unittest.TestCase):
    def test_read_only_connection_and_comparison(self):
        cur=FakeCursor()
        conn=FakeConn(cur)
        dsn=f"postgresql://{ROLE}.{PROJECT}:mock-password@aws-1-us-east-2.pooler.supabase.com:5432/postgres"
        with patch.dict(os.environ,{"EC021_RISK_DB_DSN":dsn}):
            result=check(connect=lambda *_a,**_kw:conn,
                read_rows=lambda:{"2026-11-23":1035,"2026-11-24":1094},
                read_summary=lambda:1094)
        self.assertEqual(result["status"],"connection_verified")
        self.assertFalse(result["writes_to_supabase"])
        self.assertTrue(conn.rolled_back)
        self.assertEqual(cur.executions[0],"SET TRANSACTION READ ONLY")
        self.assertFalse(any(q.lstrip().upper().startswith(("INSERT","UPDATE","DELETE","TRUNCATE")) for q in cur.executions))
    def test_reject_missing_secret(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaises(ValueError):
                check()
    def test_reject_overprivileged_role(self):
        cur=FakeCursor(allow=False)
        dsn=f"postgresql://{ROLE}.{PROJECT}:mock-password@aws-1-us-east-2.pooler.supabase.com:5432/postgres"
        with patch.dict(os.environ,{"EC021_RISK_DB_DSN":dsn}):
            with self.assertRaisesRegex(RuntimeError,"role not verified"):
                check(connect=lambda *_a,**_kw:FakeConn(cur))

if __name__=="__main__":
    unittest.main()
