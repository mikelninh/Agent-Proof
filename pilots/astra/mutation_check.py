"""Deliberately break important controls and require real assertion failures."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parent
MUTATIONS={
    'role_boundary_removed':('if role != needed:', 'if False:'),
    'artifact_binding_removed':("if not state['artifact_hash'] or data.get('artifact_hash') != state['artifact_hash']:", 'if False:'),
    'human_gate_removed':("if state['status'] != 'approved':", 'if False:'),
    'fixtures_counted_as_live':("if row.get('provenance') != 'live_measured':", 'if False:'),
    'failed_work_omitted_from_unit_cost':('cost/accepted if cost is not None and accepted else None','cost/n if cost is not None and accepted else None'),
}


def main():
    original=(ROOT/'control_room.py').read_text(encoding='utf-8')
    results=[]
    for name,(old,new) in MUTATIONS.items():
        if original.count(old)!=1:
            raise RuntimeError(f'Mutation anchor drifted: {name}')
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            (folder/'control_room.py').write_text(original.replace(old,new),encoding='utf-8')
            shutil.copyfile(ROOT/'test_control_room.py',folder/'test_control_room.py')
            run=subprocess.run([sys.executable,'-m','unittest','discover','-s',temp,'-v'],
                               capture_output=True,text=True,timeout=30)
            output=run.stdout+run.stderr
            failures=[line for line in output.splitlines() if line.startswith('FAIL:')]
            results.append(dict(mutation=name,detected=bool(failures) and run.returncode!=0,
                                assertion_failures=failures,exit_code=run.returncode))
    report=dict(provenance='deliberate_source_mutations_not_live_agents',
                detected=sum(r['detected'] for r in results),total=len(results),results=results)
    (ROOT/'evidence').mkdir(exist_ok=True)
    (ROOT/'evidence'/'mutations.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
    raise SystemExit(0 if report['detected']==report['total'] else 1)


if __name__=='__main__': main()
