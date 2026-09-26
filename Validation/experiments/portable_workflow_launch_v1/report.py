"""Render current launch evidence without treating scientific rejection as success."""
import collections,json
from pathlib import Path
here=Path(__file__).resolve().parent;out=here.parents[1]/'output/portable_workflow_launch_v1';m=json.loads((here/'manifest.json').read_text());audit={r['case']:r for r in json.loads((out/'output-audit.json').read_text())}
superseded={c['supersedes'] for c in m['cases'] if 'supersedes' in c};rows=[]
for c in m['cases']:
    p=out/c['id']/'job.json'
    if not p.exists():continue
    j=json.loads(p.read_text());s=json.loads((Path.home()/'.iproteinstudio/agent/jobs'/j['id']/'state.json').read_text());a=audit.get(c['id'],{})
    rows.append(dict(case=c['id'],job_id=j['id'],status=s['status'],message=s.get('message'),superseded=c['id'] in superseded,scientific_rejection=a.get('scientific_rejection',False),audit_passed=a.get('passed',False),structure_count=len(a.get('structures',[])),errors=a.get('errors',[])))
(out/'current-summary.json').write_text(json.dumps(rows,indent=2)+'\n')
text=['# Portable workflow launch checks','','These are launch/integration checks on one M4 Max, macOS26.6.1. They do not establish design quality, speed improvements, fresh-Mac compatibility or results on other chips.','','| Case | Job state | Output audit | Structure files |','|---|---|---|---:|']
for r in rows:
    if r['superseded']:continue
    verdict='passed' if r['audit_passed'] else ('pending' if r['status'] in ('queued','running') else 'needs review')
    label='scientific gate: no survivors' if r['scientific_rejection'] else r['status']
    text.append(f"| {r['case']} | {label} | {verdict} | {r['structure_count']} |")
text+=['','Original failures and cancelled-before-execution attempts are retained in `current-summary.json`, with their immutable plans and raw outputs. A zero-survivor NISE structural gate is a scientific rejection, not permission to relax the gate.','', 'The production biotin job remains separate; see pause/resume receipts.']
(out/'REPORT.md').write_text('\n'.join(text)+'\n');print(json.dumps(collections.Counter(r['status'] for r in rows if not r['superseded'])))
