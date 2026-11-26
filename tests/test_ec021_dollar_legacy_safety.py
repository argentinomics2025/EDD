"""Verify the retired legacy workflow cannot run shared-key writes."""
import unittest
from pathlib import Path

WORKFLOW = (Path(__file__).resolve().parents[1] / ".github/workflows/robot_dolar.yml")

class TestRetiredLegacyDollar(unittest.TestCase):
    def test_workflow_is_retired(self):
        content = WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn("schedule:", content)
        self.assertNotIn("SUPABASE_KEY", content)
        self.assertNotIn("scripts/actualizar_dolar.py", content)
        self.assertIn("if: ${{ false }}", content)
