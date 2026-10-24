"""Emit only aggregate unittest results, never exception strings or credentials."""
import io
import json
import unittest


def run_suite(suite):
    # unittest normally writes traceback/SQL/HTTP details. Keep them private in memory.
    result=unittest.TextTestRunner(stream=io.StringIO(),verbosity=0).run(suite)
    report={'tests_run':result.testsRun,'failures':len(result.failures),
            'errors':len(result.errors),'skipped':len(result.skipped),
            'successful':result.wasSuccessful()}
    return report


def main():
    from .integration_suite import DisposableIntegration
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(DisposableIntegration)
    report=run_suite(suite)
    print(json.dumps(report,sort_keys=True))
    raise SystemExit(0 if report['successful'] and report['tests_run']==11 and not report['skipped'] else 1)


if __name__=='__main__':main()
