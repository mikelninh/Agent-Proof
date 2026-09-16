"""Create a self-contained evidence viewer; no service or live data implied."""
import json
from pathlib import Path
import re
root = Path(__file__).resolve().parent
report = json.loads((root / 'evidence/report.json').read_text())
log = root / 'evidence/unit-tests.txt'
if log.exists():
    text = log.read_text()
    match = re.search(r'Ran (\d+) tests', text)
    if match:
        n = int(match[1]); ok = text.rstrip().endswith('OK')
        report['validation'] = {'tests': n, 'passed': n if ok else None,
                                'evidence': 'evidence/unit-tests.txt', 'scope': 'local deterministic tests'}
serialized = json.dumps(report, ensure_ascii=True).replace('<', '\\u003c')
page = (root / 'dashboard.template.html').read_text().replace('__REPORT__', serialized)
(root / 'control-room.html').write_text(page)
print(root / 'control-room.html')
