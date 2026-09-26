"""Declare new immutable attempts; never alter failed or held plans."""
import copy,json
from pathlib import Path
here=Path(__file__).resolve().parent;out=here.parents[1]/'output/portable_workflow_launch_v1';p=here/'manifest.json';m=json.loads(p.read_text());by={c['id']:c for c in m['cases']}
held=json.loads((out/'queue-hold.json').read_text())
names=[r['case'] for r in held]+['hunter-openfold-3-mlx','rfd3-protein-flash','nise-nesso']
new=[]
for name in names:
    case=copy.deepcopy(by[name]);cid=name+'-fixed'
    if cid in by:continue
    case.update(id=cid,supersedes=name,retry_reason='Fresh plan with staged broker, shared adapters and ligand export runtime; identical scientific inputs')
    args=case['arguments']
    if 'run_name' in args:args['run_name']=cid
    m['cases'].append(case);new.append(cid)
p.write_text(json.dumps(m,indent=2)+'\n');print(' '.join(new))
