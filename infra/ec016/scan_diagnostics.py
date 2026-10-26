"""Private Trivy capture and allowlisted, fail-closed diagnostics; never dump logs."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from .plan_b_reports import validate_reports

SUBJECTS = {'postgresql': 'POSTGRES', 'postgrest': 'POSTGREST',
            'python': 'PYTHON', 'runner': 'RUNNER'}


def capture(root, subject, args):
    if subject not in SUBJECTS:
        return 1
    # The verified binary is adjacent to the wrapper. Neither stream is published.
    with (root / (subject + '.private.log')).open('wb') as log:
        os.chmod(log.name, 0o600)
        result = subprocess.run([str(root / 'trivy-real'), *args],
                                stdout=log, stderr=log, check=False)
    return result.returncode


def diagnose(root, subject):
    """No report is evidence of success. Classify only recognized technical errors."""
    if subject not in SUBJECTS:
        raise ValueError('Unknown subject')
    codes = []
    log = root / (subject + '.private.log')
    text = log.read_text(errors='replace').lower() if log.is_file() else ''
    if any(marker in text for marker in (
            'failed to download vulnerability db', 'failed to download vulnerability database',
            'failed to download java db')) or (
            'failed to download artifact' in text and
            any(marker in text for marker in ('vulnerability db', 'db error:', 'java db'))):
        codes.append({'code': 'SCAN_DB_DOWNLOAD_FAILED'})
    if any(marker in text for marker in (
            'unable to inspect the image', 'unable to inspect image',
            'unable to initialize an image scanner', 'failed to initialize a scanner',
            'failed to get the image', 'image not found')):
        codes.append({'code': 'SCAN_IMAGE_ERROR'})
    report = root / (subject + '.json')
    if not report.is_file():
        return codes + [{'code': 'SCAN_REPORT_MISSING'}]
    try:
        data = json.loads(report.read_text())
        if data['SchemaVersion'] != 2:
            raise ValueError('Schema')
        image = data['Metadata']['ImageID']
        if not re.fullmatch(r'sha256:[a-f0-9]{64}', image):
            raise ValueError('Image')
        if image != os.environ.get('EC016_SCANNED_' + SUBJECTS[subject] + '_ID'):
            raise ValueError('Identity')
        results = data.get('Results')
        if not isinstance(results, list):
            raise ValueError('Results')
        counts = {'HIGH': 0, 'CRITICAL': 0}
        packages = set()
        for result in results:
            for issue in result.get('Vulnerabilities') or []:
                severity = issue['Severity']
                if severity in counts:
                    counts[severity] += 1
                    name = issue.get('PkgName', '')
                    # Publish only package identifiers, never targets, paths or versions.
                    if isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9+_.-]{0,99}', name):
                        packages.add(name)
        if sum(counts.values()):
            names = sorted(packages)
            codes.append({'code': 'SCAN_VULNERABILITIES_BLOCKED', **counts,
                          'packages': names[:50], 'packages_truncated': len(names) > 50})
    except (ValueError, KeyError, TypeError, AttributeError):
        codes.append({'code': 'SCAN_REPORT_INVALID'})
    return codes


def finish(root, outcomes):
    failed = False
    for subject in SUBJECTS:
        outcome = outcomes.get(subject)
        if outcome not in ('success', 'failure'):
            failed = True
            continue  # Not attempted: do not mislabel a skipped scan as a DB error.
        diagnostics = diagnose(root, subject)
        if diagnostics:
            failed = True
            for item in diagnostics:
                print(json.dumps({'subject': subject, **item}, sort_keys=True))
        if outcome != 'success':
            failed = True
            if not diagnostics:
                print(json.dumps({'subject': subject, 'code': 'SCAN_TECHNICAL_FAILED'}))
    if failed:
        return 1
    try:
        summary = validate_reports(root)  # Fresh DB, inventories, four bound images.
    except Exception:
        print('SCAN_REPORT_INVALID')
        return 1
    print(json.dumps({'EC016_SCAN_OK': summary}, sort_keys=True))
    return 0


def main():
    try:
        root = Path(os.environ['RUNNER_TEMP']) / 'ec016-trivy'
        if sys.argv[1:2] == ['run']:
            code = capture(root, os.environ.get('EC016_SCAN_SUBJECT'), sys.argv[2:])
        else:
            code = finish(root, json.loads(os.environ['EC016_SCAN_OUTCOMES']))
    except Exception:
        print('SCAN_REPORT_INVALID')
        code = 1
    raise SystemExit(code)


if __name__ == '__main__':
    main()
