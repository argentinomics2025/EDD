"""Cutover invariants: no double writer, scoped secret, locked cron."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NEW = ROOT / ".github/workflows/ec021_bcra_safe_writer.yml"
OLD = ROOT / ".github/workflows/robot_bcra.yml"


class TestBCRACutover(unittest.TestCase):
    def test_old_robot_has_no_schedule_or_writer(self):
        old = OLD.read_text(encoding="utf-8")
        self.assertNotIn("  schedule:", old)
        self.assertNotIn("SUPABASE_KEY", old)
        self.assertNotIn("scripts/actualizar_bcra.py", old)
        self.assertIn("if: " + "$" + "{{ false }}", old)

    def test_new_writer_uses_only_dedicated_credential(self):
        new = NEW.read_text(encoding="utf-8")
        self.assertIn("secrets.EC021_BCRA_DB_DSN", new)
        self.assertIn("vars.EC021_BCRA_WRITES_ENABLED", new)
        self.assertNotIn("secrets.SUPABASE_KEY", new)
        self.assertIn("guarded_writer:", new)
        self.assertIn("ec021-bcra-dedicated-writer", new)

    def test_no_unguarded_scheduled_writes(self):
        new = NEW.read_text(encoding="utf-8")
        self.assertIn("cron: '0 23 * * *'", new)
        self.assertIn("vars.EC021_BCRA_WRITES_ENABLED == 'true'", new)
        self.assertIn("needs: preflight", new)
        self.assertIn("EC021_BCRA_IDEMPOTENT_REPLAY_PASS", new)


if __name__ == "__main__":
    unittest.main()
