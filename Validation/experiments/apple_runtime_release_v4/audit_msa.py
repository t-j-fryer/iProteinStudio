"""Read-only audit of frozen paired MSA jobs and independent crystal comparisons."""
import json
from pathlib import Path
import numpy as np
from crystal_compare import OUT,reference,extract,aligned,lddt,verify_complete
from worker import sha
from analyse import compare, POLICY, REPO

def audit(run):
 cfg=json.loads((run/'frozen/run.json').read_text());engine=cfg['blocks'][0]['engine'];rows=[];data={}
 progress=json.loads((run/'progress.json').read_text())
 for arm,folder in progress.items():
  folder=Path(folder);req=folder.parent/(folder.name+'.request.json');verify_complete(folder,req)
  request=json.loads(req.read_text());case=request['cases'][0]
  assert request['use_msa'] and sha(case['msa'])==case['msa_sha256']
  assert sum(line.startswith('>') for line in Path(case['msa']).read_text().splitlines())>1
  items=json.loads((folder/'result.json').read_text())['rows'];assert len(items)==1
  d=extract(Path(items[0]).parent,engine);m=d['measurement'];data[arm]=d
  ref,core,receipt=reference(m['name'],m['sequence']);x=np.array([ref[i] for i in core]);y=d['ca'][core]
  shapes=m['details']['msa_feature_shapes'];assert len(shapes)==1 and 'msa' in shapes[0]
  msa_shape=shapes[0]['msa'];assert msa_shape[-3 if engine.startswith('intellifold') or engine=='openfold' else 0]>1
  if engine.startswith('intellifold'):
   msa_npzs=list((Path(items[0]).parent/'prediction').glob('*/processed/msa/*.npz'));assert len(msa_npzs)==1
   with np.load(msa_npzs[0]) as z:assert len(z['sequences'])>1
  rows.append(dict(engine=engine,arm=arm,torch=m['torch'],msa_sha256=case['msa_sha256'],msa_shapes=shapes,first_call_seconds=m['seconds'],core_ca_rmsd=aligned(x,y)[0],core_ca_lddt=lddt(x,y),mean_core_plddt=float(d['ca_plddt'][core].mean()),geometry_violations=len(d['breaks']),unit=str(Path(items[0]).parent)))
 pair=None
 if len(data)==2:
  a,b=data['baseline'],data['candidate'];assert a['ids']==b['ids']
  pair=dict(core_ca_rmsd=aligned(a['ca'][core],b['ca'][core])[0],core_mean_plddt_delta=float(b['ca_plddt'][core].mean()-a['ca_plddt'][core].mean()),new_geometry_violations=len(b['breaks']-a['breaks']),matrices={k:dict(mae=float(np.abs(v-b['matrices'][k]).mean()),p95=float(np.percentile(np.abs(v-b['matrices'][k]),95))) for k,v in a['matrices'].items()})
 limits=json.loads((REPO/'Validation/experiments/apple_runtime_throughput_v2/manifest.json').read_text())['acceptance']
 result=dict(complete=(run/'completed.json').exists() and len(data)==2,rows=rows,pair=pair,reference=receipt,original_equivalence_gate=compare(data['baseline'],data['candidate'],engine,limits) if len(data)==2 else None,original_policy=POLICY)
 (run/'MSA_AUDIT.json').write_text(json.dumps(result,indent=2)+'\n');return result

def main():
 results={}
 for run in sorted(OUT.glob('*_msa_20*')):
  if not (run/'progress.json').exists():continue
  try:results[run.name]=audit(run)
  except Exception as e:results[run.name]=dict(audit_error=repr(e))
 (OUT/'msa_comparison.json').write_text(json.dumps(results,indent=2)+'\n')
 lines=['# Paired cached-MSA runtime comparison','','Same exact yeast Smt3 96-residue query and 8,060-row cached alignment in both arms. FP32, 200 diffusion steps, 10 recycles for Protenix/IntelliFold; unchanged 3-recycle OpenFold preset. 1 sample, seed 42, 4 CPU threads. Core 21–96 is fixed from 3QHT chain A, excluding the mobile N-terminus. One first prediction per arm: timings include first-use work and are not steady-state speed estimates. This is a diagnostic on one protein/seed, not broad design validation.','', '| Engine | Torch | Core CA RMSD to crystal (Å) | CA lDDT | Core pLDDT | Geometry violations | First call (s) |','|---|---|---:|---:|---:|---:|---:|']
 for name,r in results.items():
  if 'audit_error' in r:lines+=['',f'Audit error for{name}: {r["audit_error"]}'];continue
  for row in r['rows']:lines.append(f"| {row['engine']} | {row['torch']} | {row['core_ca_rmsd']:.3f} | {row['core_ca_lddt']:.3f} | {row['mean_core_plddt']:.1f} | {row['geometry_violations']} | {row['first_call_seconds']:.2f} |")
 lines+=['', 'Original numerical-equivalence gates (unchanged):']
 for name,r in results.items():
  gate=r.get('original_equivalence_gate')
  if gate:lines.append('- '+name.split('_msa_')[0]+': '+('PASS' if gate['passed'] else 'FAIL: '+', '.join(gate['failures'])))
 lines+=['','[Crystal reference 3QHT](https://www.rcsb.org/structure/3QHT). Exact raw paths, alignment checksum, model-entry MSA tensor shapes, runtime-pair structure differences and confidence-matrix differences are retained in msa_comparison.json. Same-seed draws may differ across Torch versions; this test measures resulting structures, not identical stochastic trajectories.']
 (OUT/'MSA_REPORT.md').write_text('\n'.join(lines)+'\n');print(json.dumps(results,indent=2))
if __name__=='__main__':main()
