"""Static safety checks for legacy robot before activating its existing schedule."""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts" / "actualizar_dolar.py"
WORKFLOW = ROOT / ".github" / "workflows" / "robot_dolar.yml"


class TestLegacyDollarSafety(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_valid_python(self):
        compile(self.source, str(SOURCE), "exec")
        ast.parse(self.source)

    def test_validate_before_first_mutation(self):
        self.assertIn("validate(data)", self.source)
        self.assertLess(self.source.index("validate(data)"),
                        self.source.index("supabase.table('economic_indicators').upsert("))

    def test_all_write_errors_raise(self):
        self.assertIn("raise RuntimeError(f\"Error actualizando pizarra", self.source)
        self.assertIn("raise RuntimeError(f\"Error actualizando historial", self.source)
        self.assertIn("raise RuntimeError(\"Error de red", self.source)
        self.assertIn("raise RuntimeError(\"Error General", self.source)

    def test_reduced_schedule(self):
        self.assertIn("0 14,17,20 * * 1-5", self.workflow)
        self.assertNotIn("*/30 14-21", self.workflow)

    def test_single_writer_concurrency(self):
        self.assertIn("group: ec021-dollar-legacy-writer", self.workflow)
        self.assertIn("cancel-in-progress: false", self.workflow)


if __name__ == "__main__":
    unittest.main()
