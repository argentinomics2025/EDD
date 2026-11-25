"""EC-021 read-only connection probe unit tests, no real DB or secrets."""
import unittest
from unittest.mock import patch
from scripts.ec021_ripte_connection_probe import probe
from scripts.ec021_ripte_scoped_writer import PROJECT, ROLE
from tests.test_ec021_ripte_scoped_writer import Cursor, HTTP, SOURCE

class ReadOnlyCursor(Cursor):
    def __init__(self):
        super().__init__(stored=SOURCE)
        self.last_readonly = False
    def execute(self, sql, params=()):
        if sql == "SET TRANSACTION READ ONLY":
            self.last_readonly = True
        else:
            super().execute(sql, params)
    def fetchone(self):
        if "current_setting" in self.last:
            return ("on",)
        return super().fetchone()

class ReadOnlyConn:
    def __init__(self):
        self.c = ReadOnlyCursor()
        self.rolled_back = False
    def __enter__(self): return self
    def __exit__(self,*unused): return False
    def cursor(self): return self.c
    def rollback(self): self.rolled_back = True

class ReadOnlyProbeTests(unittest.TestCase):
    def test_role_and_snapshot_only(self):
        conn=ReadOnlyConn()
        direct=f"postgresql://{ROLE}:placeholder@db.{PROJECT}.supabase.co:5432/postgres"
        with patch.dict("os.environ",{"EC021_RIPTE_DB_DSN":direct}), \
             patch("scripts.ec021_ripte_connection_probe.read_source",return_value=(SOURCE,"abc")), \
             patch("scripts.ec021_ripte_connection_probe.public_snapshot",return_value=SOURCE):
            result=probe(connect=lambda *args,**kwargs:conn)
        self.assertEqual(result["status"],"connection_verified")
        self.assertTrue(result["read_only_transaction"])
        self.assertFalse(result["writes_to_supabase"])
        self.assertTrue(conn.rolled_back)
        self.assertTrue(conn.c.last_readonly)
        self.assertFalse(any(q.strip().upper().startswith(("DELETE","UPDATE","INSERT")) for q,_ in conn.c.queries))

    def test_missing_credential_rejected(self):
        with patch.dict("os.environ",{},clear=True), \
             patch("scripts.ec021_ripte_connection_probe.read_source",return_value=(SOURCE,"abc")):
            with self.assertRaises(ValueError):
                probe()

if __name__=="__main__":
    unittest.main()
