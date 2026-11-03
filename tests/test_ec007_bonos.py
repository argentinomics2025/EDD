"""EC-007.2: isolated subprocess tests, no Selenium/network/Supabase access.

Run: python -m unittest discover -s tests -p 'test_ec007_bonos.py'
The child process installs all stubs BEFORE loading the production script.
"""
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROBOT = Path(__file__).resolve().parents[1] / "scripts" / "actualizar_bonos.py"
CANARY = "EC007_SYNTHETIC_CANARY_DO_NOT_LOG"
STUB = r'''
import os,runpy,sys,types
scenario=os.environ["EC007_SCENARIO"]
canary=os.environ["SUPABASE_KEY"]
class Cell:
 def __init__(self,text):self.text=text
class Row:
 def __init__(self,ticker="AL30",price="100",changes=("1","2","3")):
  self.cells=[Cell(v) for v in (ticker,price,*changes)]
 def find_elements(self,*args):return self.cells
class BrokenRow:
 def find_elements(self,*args):raise RuntimeError("DOM failed "+canary)
class Driver:
 def get(self,url):
  if scenario in ("selenium","selenium_quit"):raise RuntimeError("selenium failed "+canary)
 def find_elements(self,*args):
  if scenario=="empty":return []
  if scenario=="invalid":return [Row(price="bad")]
  if scenario=="nan":return [Row(price="NaN")]
  if scenario=="zero":return [Row(price="0")]
  if scenario=="duplicate":return [Row(),Row()]
  if scenario=="partial":return [Row(),Row(ticker="AL29",price="bad")]
  if scenario=="unknown":return [Row(ticker="XYZ")]
  if scenario=="row_exception":return [BrokenRow()]
  return [Row()]
 def quit(self):
  if scenario in ("quit","selenium_quit"):raise RuntimeError("cleanup failed "+canary)
class Manager:
 def install(self):return "synthetic-driver"
class Options:
 def add_argument(self,*args):pass
class By:TAG_NAME="tag"
class Wait:
 def __init__(self,*args):pass
 def until(self,*args):return True
class Client:
 def table(self,*args):return self
 def upsert(self,*args,**kwargs):return self
 def execute(self):
  print("STUB_DB_CALLED")
  if scenario=="db":raise RuntimeError("database failed "+canary)
  if scenario=="db_none":return None
  if scenario=="db_error":return types.SimpleNamespace(error="error")
  return types.SimpleNamespace(error=None,data=[{"ticker":"AL30"}])
def mod(name,**fields):
 m=types.ModuleType(name);m.__dict__.update(fields);sys.modules[name]=m
mod("selenium",webdriver=types.SimpleNamespace(Chrome=lambda **kwargs:Driver()))
mod("selenium.webdriver");mod("selenium.webdriver.chrome")
mod("selenium.webdriver.chrome.service",Service=lambda x:x)
mod("selenium.webdriver.chrome.options",Options=Options)
mod("selenium.webdriver.common");mod("selenium.webdriver.common.by",By=By)
mod("selenium.webdriver.support")
mod("selenium.webdriver.support.ui",WebDriverWait=Wait)
mod("selenium.webdriver.support.expected_conditions",presence_of_element_located=lambda *args:None)
mod("webdriver_manager");mod("webdriver_manager.chrome",ChromeDriverManager=Manager)
mod("supabase",create_client=lambda *args:Client())
import time;time.sleep=lambda *args:None
runpy.run_path(os.environ["EC007_ROBOT"],run_name="__main__")
'''


class BonosExitStatusTests(unittest.TestCase):
    def test_failures_are_visible_and_safe(self):
        before_write = {"selenium", "selenium_quit", "empty", "invalid",
                        "nan", "zero", "duplicate", "partial", "unknown", "row_exception"}
        failures = sorted(before_write | {"db", "db_none", "db_error", "quit"})
        for scenario in failures:
            with self.subTest(scenario=scenario):
                code, output = self.execute(scenario)
                self.assertEqual(code, 1, output)
                self.assertIn("[bonos] ERROR", output)
                self.assertNotIn("[bonos] OK", output)
                self.assertNotIn(CANARY, output)
                if scenario in before_write:
                    self.assertNotIn("STUB_DB_CALLED", output)

    def test_valid_mocked_extract_succeeds(self):
        code, output = self.execute("valid")
        self.assertEqual(code, 0, output)
        self.assertIn("[bonos] OK registros=1", output)
        self.assertIn("STUB_DB_CALLED", output)
        self.assertNotIn(CANARY, output)

    @staticmethod
    def execute(scenario):
        env = {**os.environ, "EC007_SCENARIO": scenario,
               "EC007_ROBOT": str(ROBOT),
               "SUPABASE_URL": "https://synthetic.invalid",
               "SUPABASE_KEY": CANARY}
        result = subprocess.run([sys.executable, "-c", STUB],
                                env=env, capture_output=True, text=True,
                                timeout=15, check=False)
        return result.returncode, result.stdout + result.stderr


if __name__ == "__main__":
    unittest.main()
