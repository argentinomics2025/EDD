import copy
import json
import unittest
from unittest.mock import patch

from scripts.ec0215_ipc_writer_guarded import inspect_and_maybe_apply, EXPECTED_DB

SOURCE = {
    "source":"INDEC", "status":"read_only_no_publication", "writes_to_supabase":False,
    "sha256":"a"*64,
    "latest":[{"date":"2026-07-01","monthly_pct":"2.1"},
              {"date":"2026-08-01","monthly_pct":"1.7"},
              {"date":"2026-09-01","monthly_pct":"1.9"},
              {"date":"2026-10-01","monthly_pct":"2.2"}],
}

class Resp:
    def __init__(self, data): self.data = data
    def json(self): return self.data
    def raise_for_status(self): pass

class FakeHttp:
    def __init__(self):
        self.rows = [{"date":v["date"],"value":v["monthly_pct"]} for v in SOURCE["latest"]]
        self.posts = 0
    def get(self, *args, **kwargs):
        return Resp(sorted(self.rows, key=lambda r:r["date"], reverse=True)[:4])
    def post(self, *args, **kwargs):
        self.posts += 1
        for new in json.loads(kwargs["data"]):
            if not any(old["date"] == new["date"] for old in self.rows):
                self.rows.append(new)
        return Resp([])

class GuardedWriterTests(unittest.TestCase):
    def test_no_new_month_is_noop(self):
        http=FakeHttp()
        r=inspect_and_maybe_apply(SOURCE,url=EXPECTED_DB,read_key="example",http=http)
        self.assertEqual(r["status"],"no_change")
        self.assertEqual(http.posts,0)

    def test_new_month_preview_never_writes(self):
        http=FakeHttp()
        src=copy.deepcopy(SOURCE)
        src["latest"]=src["latest"][1:]+[{"date":"2026-11-01","monthly_pct":"2.5"}]
        r=inspect_and_maybe_apply(src,url=EXPECTED_DB,read_key="example",http=http)
        self.assertEqual(len(r["insert_only"]),1)
        self.assertFalse(r["applied"])
        self.assertEqual(http.posts,0)

    def test_wrong_project_rejected(self):
        with self.assertRaisesRegex(ValueError, "another Supabase"):
            inspect_and_maybe_apply(SOURCE,url="https://unrelated.supabase.co",read_key="example",http=FakeHttp())

    def test_writer_flag_without_approval_rejected(self):
        http=FakeHttp()
        src=copy.deepcopy(SOURCE)
        src["latest"]=src["latest"][1:]+[{"date":"2026-11-01","monthly_pct":"2.5"}]
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(RuntimeError,"disabled"):
                inspect_and_maybe_apply(src,url=EXPECTED_DB,read_key="example",write_key="fake",apply=True,http=http)
        self.assertEqual(http.posts,0)

    def test_synthetic_write_then_idempotent_noop(self):
        http=FakeHttp()
        src=copy.deepcopy(SOURCE)
        src["latest"]=src["latest"][1:]+[{"date":"2026-11-01","monthly_pct":"2.5"}]
        with patch.dict("os.environ",{"EC0215_PRODUCTION_APPROVAL":"IPC_INSERT_ONLY_APPROVED"}):
            first=inspect_and_maybe_apply(src,url=EXPECTED_DB,read_key="example",write_key="fake",apply=True,http=http)
            second=inspect_and_maybe_apply(src,url=EXPECTED_DB,read_key="example",write_key="fake",apply=True,http=http)
        self.assertTrue(first["applied"])
        self.assertFalse(second["applied"])
        self.assertEqual(http.posts,1)

if __name__ == "__main__":
    unittest.main()
