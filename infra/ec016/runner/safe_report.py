"""Emit only aggregate unittest results, never exception strings or credentials."""
import io
import json
import unittest
from .startup import code_from_exception


def run_suite(suite):
    # unittest normally writes traceback/SQL/HTTP details. Keep them private in memory.
    class SafeResult(unittest.TextTestResult):
        startup_code=None
        def addError(self,test,err):
            self.startup_code=code_from_exception(err[1]) or self.startup_code
            super().addError(test,err)
    result=unittest.TextTestRunner(stream=io.StringIO(),verbosity=0,resultclass=SafeResult).run(suite)
    report={'tests_run':result.testsRun,'failures':len(result.failures),
            'errors':len(result.errors),'skipped':len(result.skipped),
            'successful':result.wasSuccessful()}
    if result.startup_code:report['startup_code']=result.startup_code
    return report


def main():
    from .integration_suite import DisposableIntegration
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(DisposableIntegration)
    report=run_suite(suite)
    print(json.dumps(report,sort_keys=True))
    raise SystemExit(0 if report['successful'] and report['tests_run']==11 and not report['skipped'] else 1)


if __name__=='__main__':main()
