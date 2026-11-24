"""Unit tests for IPC cloud monitor and dedicated PostgreSQL writer. No external calls."""
import copy
import os
import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from scripts.ec0215_ipc_cloud_ingest import (
    ENDPOINT, PROJECT, ROLE, apply_with_connection, run, snapshot_http, validate_pg_dsn,
)

SOURCE = {
    "source": "INDEC", "status": "read_only_no_publication",
    "writes_to_supabase": False, "sha256": "c" * 64,
    "latest": [
        {"date": "2026-08-01", "monthly_pct": "1.7"},
        {"date": "2026-09-01", "monthly_pct": "1.9"},
        {"date": "2026-10-01", "monthly_pct": "2.2"},
        {"date": "2026-11-01", "monthly_pct": "2.5"},
    ],
}
STORED = [
    (date(2026, 10, 1), Decimal("2.2")),
    (date(2026, 9, 1), Decimal("1.9")),
    (date(2026, 8, 1), Decimal("1.7")),
    (date(2026, 7, 1), Decimal("2.1")),
]


class Response:
    def __init__(self, data):
        self.data = data
    def raise_for_status(self):
        pass
    def json(self):
        return self.data


class Http:
    def __init__(self, rows):
        self.rows = rows
    def get(self, endpoint, **kw):
        assert endpoint == ENDPOINT
        assert kw["params"]["select"] == "date,value"
        assert kw["params"]["limit"] == "4"
        return Response(self.rows)


class Cursor:
    def __init__(self, role=ROLE, db_rows=None, conflict=False, conflicting=False):
        self.role, self.rows = role, list(db_rows if db_rows is not None else STORED)
        self.conflict, self.conflicting = conflict, conflicting
        self.query = None
        self.calls = []
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def execute(self, sql, params=()):
        self.query = sql
        self.calls.append((sql, params))
        if sql.startswith("INSERT") and not self.conflict:
            d, v = params
            self.rows.append((date.fromisoformat(d), Decimal(v)))
        if sql.startswith("INSERT") and self.conflicting:
            self.rows.append((date(2026,11,1), Decimal("9.9")))
    def fetchone(self):
        if "current_user::text" in self.query:
            return self.role, self.role, True, True, False, False, False
        if self.query.startswith("INSERT"):
            return None if self.conflict else (date(2026,11,1),Decimal("2.5"))
        raise RuntimeError("unexpected fetchone")
    def fetchall(self):
        if self.query.startswith("SELECT date, value") and "ORDER BY date DESC" in self.query:
            return sorted(self.rows, reverse=True)[:4]
        if self.query.startswith("SELECT date,value FROM") and "WHERE date" in self.query:
            return [(d, v) for d, v in self.rows if d == date(2026,11,1)]
        raise RuntimeError("unexpected fetchall")


class Conn:
    def __init__(self, cur): self.cur = cur
    def cursor(self): return self.cur


class TestCloudIngest(unittest.TestCase):
    def test_project_scoped_direct_and_pooler(self):
        for dsn in [
            f"postgresql://{ROLE}:secret@db.{PROJECT}.supabase.co:5432/postgres",
            f"postgresql://{ROLE}.{PROJECT}:secret@aws-0-us-east-2.pooler.supabase.com:5432/postgres",
        ]:
            self.assertEqual(validate_pg_dsn(dsn), dsn)
    def test_rejects_admin_role_and_other_projects(self):
        for dsn in [
            f"postgresql://postgres:secret@db.{PROJECT}.supabase.co:5432/postgres",
            f"postgresql://{ROLE}:secret@db.unrelated.supabase.co:5432/postgres",
            "postgresql://x:secret@attacker.example.com:5432/postgres",
            "",
        ]:
            with self.assertRaises(ValueError):
                validate_pg_dsn(dsn)
    def test_requires_public_key(self):
        with self.assertRaises(RuntimeError):
            snapshot_http("sb_secret_NOT_FOR_READ", http=Http([]))
    def test_public_snapshot(self):
        rows = [{"date": "2026-10-01", "value": "2.2"},{"date":"2026-09-01","value":"1.9"}]
        self.assertEqual(snapshot_http("sb_publishable_test", http=Http(rows)), rows)
    def test_no_write_monitor(self):
        rows = [{"date": d.isoformat(), "value": str(v)} for d,v in STORED]
        with patch("scripts.ec0215_ipc_cloud_ingest.read_official_csv", return_value=b"test"), patch(
            "scripts.ec0215_ipc_cloud_ingest.parse_national_monthly", return_value=SOURCE
        ), patch.dict(os.environ, {"EC0215_IPC_READ_KEY": "sb_publishable_test"}, clear=True):
            result = run(http=Http(rows))
        self.assertFalse(result["applied"])
        self.assertEqual(result["mode"],"read_only_monitor")
        self.assertEqual(result["insert_only"][0]["date"],"2026-11-01")
    def test_write_kill_switch(self):
        rows = [{"date": d.isoformat(), "value": str(v)} for d,v in STORED]
        with patch("scripts.ec0215_ipc_cloud_ingest.read_official_csv", return_value=b"test"), patch(
            "scripts.ec0215_ipc_cloud_ingest.parse_national_monthly", return_value=SOURCE
        ), patch.dict(os.environ, {"EC0215_IPC_READ_KEY": "sb_publishable_test"}, clear=True):
            with self.assertRaisesRegex(RuntimeError,"disabled"):
                run(apply=True, http=Http(rows))
    def test_scoped_insert_success(self):
        cur=Cursor()
        result=apply_with_connection(SOURCE, Conn(cur))
        self.assertTrue(result["applied"])
        self.assertEqual(result["status"],"requires_authorized_writer")
        self.assertEqual(len([q for q,_ in cur.calls if q.startswith("INSERT")]),1)
        self.assertFalse(any(q.strip().upper().startswith("UPDATE ") for q,_ in cur.calls))
    def test_invalid_role_prevents_writes(self):
        cur=Cursor(role="service_role")
        with self.assertRaisesRegex(RuntimeError,"isolated IPC"):
            apply_with_connection(SOURCE, Conn(cur))
        self.assertEqual(len([q for q,_ in cur.calls if q.startswith("INSERT")]),0)
    def test_existing_month_no_insert(self):
        src=copy.deepcopy(SOURCE)
        src["latest"]=src["latest"][:3]
        cur=Cursor()
        result=apply_with_connection(src, Conn(cur))
        self.assertFalse(result["applied"])
        self.assertEqual(len([q for q,_ in cur.calls if q.startswith("INSERT")]),0)
    def test_conflict_different_value_is_error(self):
        cur=Cursor(conflict=True, conflicting=True)
        with self.assertRaisesRegex(RuntimeError,"different value"):
            apply_with_connection(SOURCE, Conn(cur))


if __name__ == "__main__":
    unittest.main()
