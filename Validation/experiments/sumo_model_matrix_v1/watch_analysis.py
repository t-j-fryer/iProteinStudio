"""CPU-only report refresher; no job control, GPU imports or scientific changes."""
import json,os,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];OUT=ROOT/'Validation/output/sumo_model_matrix_v1'
cfg=json.loads((OUT/'frozen/config.json').read_text());env=os.environ.copy();env.update(MPLCONFIGDIR=str(OUT/'analysis/mpl'),OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
state=Path.home()/'.iproteinstudio/agent/jobs/job-de244a02815c/state.json';last=None
while True:
 status=json.loads(state.read_text());receipts=tuple(sorted(str(p) for p in OUT.glob('*/completed.json')))
 terminal=status.get('status') in ('completed','failed','cancelled','interrupted')
 signature=(receipts,status.get('status'))
 if signature!=last:
  successful=True
  for script in ('analyse.py','paired_summary.py','plot_stages.py','per_residue.py'):
   with (OUT/'analysis_refresh.log').open('a') as f:r=subprocess.run([cfg['analysis_python'],str(HERE/script)],env=env,stdout=f,stderr=subprocess.STDOUT)
   if r.returncode:successful=False;break
  result=dict(job_status=status.get('status'),completed_engine_blocks=len(receipts),analysis_ok=successful,updated_at=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
  if successful:
   a=json.loads((OUT/'analysis/results.json').read_text());result.update(normal_audited=a['normal_count'],diagnostic_audited=a['diagnostic_count'],audit_failures=len(a['audit_failures']),matrix_complete=a['normal_count']==250 and a['diagnostic_count']==50 and not a['audit_failures'])
  (OUT/'analysis_status.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
  last=signature
 if terminal:break
 time.sleep(30)
