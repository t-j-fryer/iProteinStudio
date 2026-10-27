"""Audit immutable managed monomer outputs and report distinct memory measures."""
import argparse, hashlib, json
from pathlib import Path
import biotite.structure as bst
from biotite.structure.io import pdbx
from Bio.SeqUtils import seq1
import numpy as np
p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--job-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
plan=json.loads(a.plan.read_text());root=Path(plan['normalized_request']['output']);cfg=plan['normalized_request']['config']
engine=cfg['predictors'][0];job=cfg['jobs'][0];expected=job['chains'][0]['sequence']
models=list((root/engine).glob('bucket_*/chunk_*/*/*_model_0.cif'));assert len(models)==1,len(models)
model=models[0];st=pdbx.get_structure(pdbx.CIFFile.read(model),model=1);assert set(st.chain_id)=={job['chains'][0]['id']}
starts=bst.get_residue_starts(st);sequence=''.join(seq1(str(st.res_name[i])) for i in starts);assert sequence==expected,(sequence,expected)
coords=st.coord;assert np.isfinite(coords).all()
confidence=json.loads(next(model.parent.glob('confidence_*.json')).read_text());assert all(np.isfinite(confidence[k]) for k in ('complex_plddt','ptm','model_call_seconds'))
for path in model.parent.glob('*.npz'):
 with np.load(path) as data:
  for key in data:assert np.isfinite(data[key]).all(),(path.name,key)
receipt=json.loads((model.parent/'complete.json').read_text());assert receipt
memory=[json.loads(p.read_text()) for p in (a.job_dir/'memory').glob('*.summary.json')];assert len(memory)==1
summary=json.loads((root/'run_summary.json').read_text());assert summary['failures']==0 and summary['results']==1
state=json.loads((a.job_dir/'state.json').read_text());assert state['status']=='completed'
files={str(p.relative_to(root)):dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),mtime_ns=p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}
out=dict(passed=True,job_id=state['id'],plan_id=plan['id'],plan_sha256=plan['sha256'],code_snapshot=plan['code_snapshot']['sha256'],engine=engine,residues=len(sequence),atoms=len(coords),settings=cfg['prediction_settings'][engine],seed=42,samples=1,model_call_seconds=confidence['model_call_seconds'],workflow_wall_seconds=summary['wall_sec'],mlx_peak_gib=confidence['mlx_peak_bytes']/2**30,accounted_tree_peak_gib=memory[0]['peaks']['tree_footprint_bytes']/2**30,tree_rss_peak_gib=memory[0]['peaks']['tree_rss_bytes']/2**30,memory_samples=memory[0]['samples'],memory_errors=memory[0]['errors'],plddt=confidence['complex_plddt'],ptm=confidence['ptm'],files=files,limitations=['n=1 per condition','64 GB M4 Max; not a 16 GB hardware test','process-tree footprint is not exact physical RAM','no accuracy or whole-model parity validation'])
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k!='files'},indent=2))
