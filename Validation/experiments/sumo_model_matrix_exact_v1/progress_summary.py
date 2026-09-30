"""Generate a compact speed/quality progress snapshot from audited results."""
import json
from pathlib import Path
OUT=Path(__file__).resolve().parents[2]/'output/sumo_model_matrix_exact_v1'
d=json.loads((OUT/'analysis/results.json').read_text());lookup={(s['engine'],s['msa'],s['budget']):s for s in d['summaries']}
labels={'boltz':'Boltz2','intellifold_flash':'IntelliFold Flash','intellifold_full':'IntelliFold Full','protenix_v2':'Protenix v2','protenix_constraint':'Protenix Constraint','protenix_mini':'Protenix Mini','esmfold2_full':'ESMFold2 Full','esmfold2_fast':'ESMFold2 Fast','openfold3':'OpenFold3'}
complete=d['normal_count']==250 and d['diagnostic_count']==50 and not d['audit_failures']
status='All nine model matrices are complete; earlier failed-attempt logs are retained.' if complete else 'Benchmark remains incomplete; completed outputs and earlier error logs are retained.'
lines=['# SUMO benchmark progress snapshot','',f"{d['normal_count']}/250 primary predictions and {d['diagnostic_count']}/50 profiling replays audited. {status}",'','M4 Max,96-aa SUMO monomer. Five seeds per cell. Warm resident request medians include preprocessing and output handling, exclude one-time loading; first model request excluded. Crystal-core query21–96 is fitted to3QHT chainA. RMSD lower is better; core CA-lDDT higher is better.128-row MSA except Fast, which has no MSA support. Steps are native requested settings (ESM internally truncates its schedule; see report).','','| Model | Steps | Request seconds | Time reduction | Core RMSD Å | Core CA-lDDT |','|---|---|---|---|---|---|']
for e,name in labels.items():
 msa='none' if e.endswith('fast') and e.startswith('esm') else '128'
 if (e,msa,'full') not in lookup or (e,msa,'reduced') not in lookup:continue
 a,b=lookup[(e,msa,'full')],lookup[(e,msa,'reduced')];ta,tb=a['warm_request_seconds'],b['warm_request_seconds']
 lines.append(f"| {name} | {a['steps']}→{b['steps']} | {ta:.2f}→{tb:.2f} | {100*(1-tb/ta):.1f}% | {a['crystal_core_rmsd']['median']:.2f}→{b['crystal_core_rmsd']['median']:.2f} | {a['core_ca_lddt']['median']:.3f}→{b['core_ca_lddt']['median']:.3f} |")
lines+=['','Negative time reduction means slower. Mini1-step: whole-chain geometry flags5/5 and core flags3/5 in the128-MSA cell; native5-step flags3/5 only outside the core. ESMFull13-step: tail flags5/5 at128 MSA, no core geometry flags, but core CA-lDDT declines. ESMFast6-step: severe core and whole-chain geometry flags5/5.','', '## Native-step MSA comparison','', '| Model | No MSA: seconds / RMSD |128: seconds / RMSD | Full: seconds / RMSD |','|---|---|---|---|']
for e,name in labels.items():
 cells=[]
 for msa in ('none','128','full'):
  s=lookup.get((e,msa,'full'));cells.append('N/A' if s is None else f"{s['warm_request_seconds']:.2f} / {s['crystal_core_rmsd']['median']:.2f}")
 lines.append('| '+name+' | '+' | '.join(cells)+' |')
lines+=['','The full file has8060 rows; native engine caps remain. Single target and five seeds do not establish a general accuracy ranking. Geometry is considered alongside alignment; a smaller RMSD alone is not sufficient. Padding comparisons and complete per-seed confidence scores are linked from REPORT.md.']
(OUT/'PROGRESS_SUMMARY.md').write_text('\n'.join(lines)+'\n');print('\n'.join(lines[:16]))
