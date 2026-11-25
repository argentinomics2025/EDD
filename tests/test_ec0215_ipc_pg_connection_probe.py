"""EC-021.5 IPC PG read-only probe tests, no secrets and no network."""
import os
import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import patch
from scripts.ec0215_ipc_pg_connection_probe import check
from scripts.ec0215_ipc_cloud_ingest import ROLE,PROJECT

DAYS=[(date(2026,10,1),Decimal("2.2")),(date(2026,9,1),Decimal("1.9")),
      (date(2026,8,1),Decimal("1.7")),(date(2026,7,1),Decimal("2.1"))]

class Cursor:
    def __init__(self,overprivileged=False):
        self.overprivileged=overprivileged
        self.queries=[]
        self.one=None
        self.many=None
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def execute(self,sql):
        self.queries.append(sql)
        if "has_column_privilege" in sql:
            self.one=(ROLE,ROLE,True,True,self.overprivileged,False,False)
        elif "SELECT date,value FROM public.datos_inflacion" in sql:
            self.many=DAYS
        elif "current_setting('transaction_read_only')" in sql:
            self.one=("on",)
        elif sql!="SET TRANSACTION READ ONLY":
            raise AssertionError(f"unexpected SQL: {sql}")
    def fetchone(self):return self.one
    def fetchall(self):return self.many

class Connection:
    def __init__(self,cursor):self.cur=cursor;self.rollback_called=False
    def __enter__(self):return self
    def __exit__(self,*a):return False
    def cursor(self):return self.cur
    def rollback(self):self.rollback_called=True

class TestIpcCredentialPreflight(unittest.TestCase):
    def test_read_only_success(self):
        cur=Cursor()
        conn=Connection(cur)
        dsn=f"postgresql://{ROLE}.{PROJECT}:mock-only@aws-1-us-east-2.pooler.supabase.com:5432/postgres"
        with patch.dict(os.environ,{"EC0215_IPC_DB_DSN":dsn},clear=True):
            result=check(connect=lambda *_args,**_kwargs:conn,
                         public_snapshot=[{"date":d.isoformat(),"value":str(v)} for d,v in DAYS])
        self.assertEqual(result["status"],"connection_verified")
        self.assertEqual(result["latest_month"],"2026-10-01")
        self.assertEqual(result["latest_pct"],"2.2")
        self.assertFalse(result["writes_to_supabase"])
        self.assertTrue(conn.rollback_called)
        self.assertEqual(cur.queries[0],"SET TRANSACTION READ ONLY")
        self.assertFalse(any(x.lstrip().upper().startswith(("INSERT","UPDATE","DELETE")) for x in cur.queries))
    def test_no_secret_rejected(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaises(ValueError):check()
    def test_overprivileged_connection_rejected(self):
        cur=Cursor(overprivileged=True)
        dsn=f"postgresql://{ROLE}.{PROJECT}:mock-only@aws-1-us-east-2.pooler.supabase.com:5432/postgres"
        with patch.dict(os.environ,{"EC0215_IPC_DB_DSN":dsn},clear=True):
            with self.assertRaisesRegex(RuntimeError,"isolated IPC"):
                check(connect=lambda *_args,**_kwargs:Connection(cur),public_snapshot=[])

if __name__=="__main__":
    unittest.main()
