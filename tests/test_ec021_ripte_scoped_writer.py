"""EC-021: synthetic tests for RIPTE source, permissions and one-month writer."""
import os
import unittest
from unittest.mock import patch
from datetime import date
from decimal import Decimal

from scripts.bot_ripte import parse_official, RipteValidationError
from scripts.ec021_ripte_scoped_writer import (
    PROJECT, ROLE, ENDPOINT, read_source, public_snapshot, validate_dsn,
    assert_writer_role, write_in_transaction, run,
)
from tests.test_ec021_ripte_safe import official_page, ROWS

SOURCE = parse_official(official_page(ROWS))
STORED = SOURCE[:-1]


class Resp:
    def __init__(self, data, is_html=False):
        self.content = data.encode() if is_html else b"[]"
        self.text = data if is_html else ""
        self.data = data if not is_html else None
    def raise_for_status(self):
        pass
    def json(self):
        return self.data


class HTTP:
    def __init__(self, stored=STORED):
        self.stored = list(stored)
    def get(self, url, **kwargs):
        if url.endswith("/ripte"):
            return Resp(official_page(ROWS), is_html=True)
        if url == ENDPOINT:
            assert kwargs["params"]["select"] == "fecha,var_ripte_mensual"
            assert kwargs["params"]["limit"] == "500"
            return Resp(self.stored)
        raise AssertionError("Unexpected URL")


class Cursor:
    def __init__(self, stored=STORED, role=ROLE, conflicting=False):
        self.stored = list(stored)
        self.role = role
        self.conflicting = conflicting
        self.queries = []
        self.last = ""
        self.inserted = None
    def __enter__(self): return self
    def __exit__(self, *unused): return False
    def execute(self, sql, params=()):
        self.last = sql
        self.queries.append((sql, params))
        if sql.lstrip().startswith("INSERT"):
            period, value = params
            if self.conflicting:
                self.stored.append({"fecha": period, "var_ripte_mensual": "9.9"})
                self.inserted = None
            else:
                self.stored.append({"fecha": period, "var_ripte_mensual": str(value)})
                self.inserted = (date.fromisoformat(period), value)
    def fetchone(self):
        if "current_user::text" in self.last:
            return self.role, self.role, True, True, False, False, False, False, True
        if self.last.lstrip().startswith("INSERT"):
            return self.inserted
        raise AssertionError("Unexpected fetchone")
    def fetchall(self):
        if "ORDER BY fecha" in self.last:
            return [(date.fromisoformat(x["fecha"]), Decimal(x["var_ripte_mensual"])) for x in self.stored]
        if "WHERE fecha=%s" in self.last:
            d=self.queries[-1][1][0]
            return [(date.fromisoformat(x["fecha"]), Decimal(x["var_ripte_mensual"])) for x in self.stored if x["fecha"]==d]
        raise AssertionError("Unexpected fetchall")


class Conn:
    def __init__(self, cursor): self.cursor_instance = cursor
    def cursor(self): return self.cursor_instance


class WriterTests(unittest.TestCase):
    def test_source_and_public_snapshot(self):
        source, sha = read_source(http=HTTP())
        self.assertEqual(source[-1]["fecha"], "2026-12-01")
        self.assertEqual(len(sha), 64)
        self.assertEqual(len(public_snapshot(http=HTTP())), 11)

    def test_reject_non_project_or_admin_dsn(self):
        bad = ["postgresql://postgres:pw@db."+PROJECT+".supabase.co:5432/postgres",
               "postgresql://"+ROLE+":pw@db.otherproject.supabase.co:5432/postgres",
               "postgresql://"+ROLE+":pw@attacker.example:5432/postgres", ""]
        for value in bad:
            with self.assertRaises(ValueError):
                validate_dsn(value)

    def test_valid_dedicated_dsn(self):
        direct=f"postgresql://{ROLE}:pass@db.{PROJECT}.supabase.co:5432/postgres"
        self.assertEqual(validate_dsn(direct), direct)
        pooler=f"postgresql://{ROLE}.{PROJECT}:pass@aws-0-us-east-2.pooler.supabase.com:6543/postgres"
        self.assertEqual(validate_dsn(pooler), pooler)

    def test_reader_never_writes(self):
        res=run(http=HTTP())
        self.assertEqual(res["mode"],"read_only_monitor")
        self.assertIs(res["writes_to_supabase"],False)

    def test_kill_switch_rejects_apply(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaisesRegex(RuntimeError,"disabled"):
                run(apply=True,http=HTTP())

    def test_role_rejects_wrong_identity(self):
        with self.assertRaisesRegex(RuntimeError,"privilege guard"):
            assert_writer_role(Cursor(role="service_role"))

    def test_scoped_insert_one_month(self):
        cur=Cursor()
        result=write_in_transaction(SOURCE,Conn(cur))
        self.assertTrue(result["applied"])
        self.assertEqual(len([q for q,_ in cur.queries if q.lstrip().startswith("INSERT")]),1)
        self.assertFalse(any(q.strip().upper().startswith(("DELETE","UPDATE")) for q,_ in cur.queries))

    def test_replay_is_noop(self):
        cur=Cursor(stored=SOURCE)
        result=write_in_transaction(SOURCE,Conn(cur))
        self.assertFalse(result["applied"])
        self.assertFalse(any(q.lstrip().startswith("INSERT") for q,_ in cur.queries))

    def test_bad_conflict_aborts(self):
        with self.assertRaisesRegex(RuntimeError,"conflicting row"):
            write_in_transaction(SOURCE,Conn(Cursor(conflicting=True)))

    def test_duplicate_month_is_blocked(self):
        dup=STORED+[{"fecha":STORED[0]["fecha"],"var_ripte_mensual":"9.9"}]
        with self.assertRaisesRegex(RipteValidationError,"Duplicate stored"):
            write_in_transaction(SOURCE,Conn(Cursor(stored=dup)))

    def test_multi_month_backfill_blocked(self):
        with self.assertRaisesRegex(RipteValidationError,"Multiple months"):
            write_in_transaction(SOURCE,Conn(Cursor(stored=SOURCE[:-2])))

    def test_public_snapshot_rejects_empty_or_huge(self):
        for stored in ([], SOURCE*40):
            with self.assertRaises(RipteValidationError):
                public_snapshot(http=HTTP(stored))


if __name__ == "__main__":
    unittest.main()
