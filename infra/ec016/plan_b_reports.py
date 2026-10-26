"""Fail closed on missing/unbound reports. The action already blocks all HIGH/CRITICAL."""
import json
import os
from pathlib import Path
import re
from .security_gate import validate_database


def validate_reports(root):
    root=Path(root);validate_database(json.loads((root/'cache/db/metadata.json').read_text()))
    summary={}
    for name in ('postgresql','postgrest','python','runner'):
        data=json.loads((root/(name+'.json')).read_text())
        if data.get('SchemaVersion')!=2:raise RuntimeError('Unknown report format')
        if not re.fullmatch('sha256:[a-f0-9]{64}',data.get('Metadata',{}).get('ImageID','')):
            raise RuntimeError('Missing image inspection')
        variable={'postgresql':'POSTGRES','postgrest':'POSTGREST','python':'PYTHON','runner':'RUNNER'}[name]
        if data['Metadata']['ImageID']!=os.environ.get('EC016_SCANNED_'+variable+'_ID'):
            raise RuntimeError('Different image scanned')
        results=data.get('Results') or []
        if not isinstance(results,list):raise RuntimeError('Incomplete report')
        packages=sum(len(r.get('Packages') or []) for r in results)
        if name!='postgrest' and not packages:raise RuntimeError('Missing package inventory')
        for result in results:
            for issue in result.get('Vulnerabilities') or []:
                if issue.get('Severity') in ('HIGH','CRITICAL'):raise RuntimeError('Blocking vulnerability')
        summary[name]={'packages':packages,'inventory_unavailable':packages==0}
    return summary


def main():
    try:
        summary=validate_reports(Path(os.environ['RUNNER_TEMP'])/'ec016-trivy')
        print(json.dumps({'EC016_SCAN_OK':summary},sort_keys=True))
    except Exception:
        print('EC016_SCAN_FAILED: missing, stale, incomplete or blocking report')
        raise SystemExit(1) from None


if __name__=='__main__':main()
