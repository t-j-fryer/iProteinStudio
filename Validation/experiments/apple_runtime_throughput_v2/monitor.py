"""Bounded monitor: audit finished jobs and submit only declared follow-up screens.
All inference stays inside immutable Studio broker jobs. Never modifies raw output.
"""
import json,os,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[2];OUT=REPO/'Validation/output/apple_runtime_throughput_v2'
ANALYSIS=REPO/'Validation/output/apple_runtime_throughput_v1/environments/boltz-torch214/bin/python'
sys.path.insert(0,str(REPO/'Sources/iProteinStudio/Resources/pipeline/mcp'));os.environ['NANOHUNTER_ROOT']=str(Path.home()/'.iproteinstudio')
from server import MCPServer
from worker import atomic
server=MCPServer('run');observed={};audited=set();submitted=set()

def existing(engine,stage,runtime=None):
 rows=[]
 for p in OUT.glob(engine+'_'+stage+'_*/frozen/run.json'):
  cfg=json.loads(p.read_text())
  if runtime is not None and not all(b['runtime']==runtime for b in cfg['blocks']):continue
  if (p.parent.parent/'submitted.json').exists():rows.append(p.parent.parent)
 return sorted(rows)
def complete_screen(engine):
 for run in reversed(existing(engine,'smoke')):
  if not (run/'completed.json').exists() or not (run/'analysis.json').exists():continue
  a=json.loads((run/'analysis.json').read_text())
  if a.get('errors') or 'baseline' not in a.get('blocks_audited',[]):continue
  return a
 return None

def launch(engine,stage,runtime='candidate',reuse=False):
 key=(engine,stage,runtime)
 if key in submitted or existing(engine,stage,runtime):return
 args=[sys.executable,str(HERE/'preflight.py'),engine,'--stage',stage,'--runtime',runtime,'--start']
 if reuse:args.append('--reuse-reference')
 result=subprocess.run(args,capture_output=True,text=True)
 log=OUT/'monitor';log.mkdir(exist_ok=True);(log/('-'.join(key)+'.log')).write_text(result.stdout+result.stderr)
 submitted.add(key)
 print('FOLLOWUP',key,'exit',result.returncode,flush=True)

def main():
 while True:
  states=[];changed=False
  for p in sorted(OUT.glob('*/submitted.json')):
   j=json.loads(p.read_text());r=server.tool_call('job_status',{'job_id':j['id']});state=r.get('status');states.append(dict(run=p.parent.name,id=j['id'],status=state))
   if observed.get(j['id'])!=state:
    observed[j['id']]=state;print('STATUS',p.parent.name,state,flush=True);changed=True
   if state=='completed' and p.parent not in audited:
    result=subprocess.run([str(ANALYSIS),str(HERE/'analyse.py'),str(p.parent)],capture_output=True,text=True)
    (p.parent/'analysis_execution.txt').write_text(result.stdout+result.stderr);audited.add(p.parent);changed=True
    if (p.parent/'analysis.json').exists():
     a=json.loads((p.parent/'analysis.json').read_text());print('AUDIT',p.parent.name,a.get('passed'),a.get('errors'),flush=True)
  # Implementation arms change only computational execution and retain their original gates.
  for engine in ('protenix','constraint'):
   screen=complete_screen(engine)
   if screen:launch(engine,'cache','candidate' if screen['passed'] else 'baseline',reuse=True)
  flash=complete_screen('intellifold-flash');full=complete_screen('intellifold-full')
  if full:
   passing_bucket=any((p/'analysis.json').exists() and json.loads((p/'analysis.json').read_text()).get('passed') for p in existing('intellifold-flash','buckets'))
   if passing_bucket:launch('intellifold-full','buckets','baseline',reuse=True)
  rfd=complete_screen('rfd3')
  if rfd and any((p/'completed.json').exists() for p in existing('rfd3','profile')):
   launch('rfd3','attention','candidate' if rfd['passed'] else 'baseline',reuse=True)
  nesso=complete_screen('nesso')
  if nesso:
   ccd=existing('nesso','ccd','candidate')
   if any((p/'analysis.json').exists() and json.loads((p/'analysis.json').read_text()).get('passed') for p in ccd):launch('nesso','ccd','baseline',reuse=True)
  atomic(OUT/'live_status.json',dict(updated=time.time(),jobs=states))
  if changed:
   env=dict(os.environ,MPLCONFIGDIR='/private/tmp/iprotein-throughput-mpl')
   subprocess.run([sys.executable,str(HERE/'summarise.py')],env=env,capture_output=True,text=True)
  active=[s for s in states if s['status'] in ('queued','running','stopping')]
  # New followups submitted in this iteration appear on the next poll.
  if not active and len(states)==len(list(OUT.glob('*/submitted.json'))):
   print('ALL_TERMINAL',flush=True);return
  time.sleep(40)
if __name__=='__main__':main()
