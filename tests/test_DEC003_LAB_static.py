"""Static checks only: NOT proof PostgreSQL DDL works; never run in production."""
import unittest
from pathlib import Path

SQL=(Path(__file__).resolve().parents[1]/"sql"/"DEC003_LAB_NO_PRODUCCION.sql").read_text()

class SchemaDesignTests(unittest.TestCase):
    def test_schema_isolation(self):self.assertIn("CREATE SCHEMA ec0073_lab;",SQL)
    def test_three_tables(self):
        for t in ("ingesta_lotes","observaciones","revisiones"):
            with self.subTest(table=t):self.assertIn("CREATE TABLE ec0073_lab."+t,SQL)
    def test_append_only(self):self.assertEqual(SQL.count("BEFORE UPDATE OR DELETE ON"),3)
    def test_rls_force(self):self.assertEqual(SQL.count("FORCE ROW LEVEL SECURITY"),3)
    def test_rls_enabled(self):self.assertEqual(SQL.count("ENABLE ROW LEVEL SECURITY"),3)
    def test_no_web_grants(self):self.assertNotIn("GRANT ",SQL)
    def test_no_public_policies(self):self.assertNotIn("CREATE POLICY",SQL)
    def test_unique_records(self):self.assertIn("UNIQUE(lote_id,ticker,registro_fuente,version_fuente)",SQL)
    def test_unique_hash(self):self.assertIn("hash_carga text NOT NULL UNIQUE",SQL)
    def test_no_publishing(self):self.assertIn("CHECK (autorizado_publicar = false)",SQL)
    def test_price_checks(self):self.assertIn("precio numeric(20,8) NOT NULL CHECK (precio > 0)",SQL)
    def test_revisions(self):self.assertIn("UNIQUE(observacion_id,revision_num)",SQL)
    def test_schema_transaction(self):self.assertTrue(SQL.strip().endswith("COMMIT;"))
    def test_no_production_table_mutation(self):
        for p in ("public.historial_bonos","DROP TABLE","TRUNCATE TABLE"):
            with self.subTest(p=p):self.assertNotIn(p,SQL)

if __name__=="__main__":unittest.main()
