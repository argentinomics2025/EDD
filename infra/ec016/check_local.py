"""All repository unit tests that do not execute SQL or require services."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


def main():
    root=Path(__file__).resolve().parents[2]
    sys.path.insert(0,str(root/'tests'))
    loader=unittest.TestLoader();suite=unittest.TestSuite()
    with patch('socket.socket.connect',side_effect=AssertionError('External network forbidden')), \
         patch('sqlite3.connect',side_effect=AssertionError('SQL forbidden during local checks')):
        for path in sorted((root/'tests').glob('test_*.py')):
            if path.stem!='test_ica_integration_sqlite':
                suite.addTests(loader.loadTestsFromName(path.stem))
        result=unittest.TextTestRunner(verbosity=1).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__=='__main__':main()
