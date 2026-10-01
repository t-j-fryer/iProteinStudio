"""Prepare the normal immutable iterative plan using a disposable adapter root.

The root shares Studio's agent directory, execution lock, installed engines and
weights; only app-owned adapters are copied. Never bypass the broker.
"""
import json, os, shutil, sys, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'Validation/output/hunter_stages_v1'
DEV=OUT/'runtime';REAL=Path.home()/'.iproteinstudio'
RES=ROOT/'Sources/iProteinStudio/Resources'
DEV.mkdir(parents=True,exist_ok=True)
for p in REAL.iterdir():
    target=DEV/p.name
    if p.name in {'scripts','nanohunter_run.sh','mcp','rfd3_scripts','projects','agent'}:continue
    if not target.exists():target.symlink_to(p.resolve())
for source,name in [(RES/'pipeline/scripts','scripts'),(RES/'pipeline/mcp','mcp'),(RES/'rfd3','rfd3_scripts')]:
    shutil.copytree(source,DEV/name,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
shutil.copy2(RES/'pipeline/nanohunter_run.sh',DEV/'nanohunter_run.sh')
(DEV/'projects/hunter-stages-acceptance').mkdir(parents=True,exist_ok=True)
os.environ['NANOHUNTER_ROOT']=str(DEV)
os.environ['IPROTEINSTUDIO_AGENT_ROOT']=str(REAL/'agent')
sys.path.insert(0,str(DEV/'mcp'))
from iprotein_mcp.plans import iterative_plan
from iprotein_mcp.broker import start_job
from iprotein_mcp.catalog import workflow_guide
(OUT/'workflow_guide.json').write_text(json.dumps(workflow_guide('iterative_design'),indent=2))
import hashlib
assets={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (RES/'examples/acbx').iterdir() if p.is_file()}
(OUT/'inputs.sha256.json').write_text(json.dumps(assets,indent=2))
shutil.copytree(RES/'examples/acbx',DEV/'acceptance_inputs',dirs_exist_ok=True)
input_path=DEV/'acceptance_inputs/input.yaml'
input_path.write_text((RES/'pipeline/examples/aCbx_bind.yaml').read_text().replace('sequence:\n','sequence: '+ 'X'*65 +'\n').replace('version: 1','      msa: '+str(DEV/'acceptance_inputs/target_msa.a3m')+'\nversion: 1'))
manifest=json.loads((Path(__file__).parent/'manifest.json').read_text())
arm=next(a for a in manifest['arms'] if a['name']==sys.argv[1])
run_name=arm['name']+next((s.split('=',1)[1] for s in sys.argv if s.startswith('--suffix=')), '')
args=['--workflow','protein','--predictor',arm['refinement'],'--sequence-designer','solublempnn','--num-runs',str(arm['trajectories']),'--num-opt-cycles',str(arm['cycles']),'--iptm-threshold','0.8','--post-predictor','none','--post-mode','none','--random-binder','--binder-min-len','65','--binder-max-len','65','--binder-random-seed','42','--mpnn-seed','42','--predictor-seed','42','--target-msa-mode','auto','--require-target-msa','--skip-predictor-calibration']
if arm['initialization']=='rfd3':args+=['--initialization-method','rfd3','--initialization-target',str(DEV/'acceptance_inputs/target.pdb')]
else:args+=['--initialization-method','hallucination','--initialization-predictor',arm['initialization']]
if arm['name']=='rfd3_ligand_boltz':
    index=args.index('--initialization-target');del args[index:index+2]
    args[args.index('--sequence-designer')+1]='ligandmpnn'
    args.remove('--require-target-msa')
    args[args.index('--target-msa-mode')+1]='off'
    smiles=(RES/'examples/fluorescein/ligand.smi').read_text().strip().split()[0]
    helper=DEV/'rfd3_scripts/boltz_ligand_atoms.py'
    mapping=json.loads(subprocess.check_output([str(REAL/'venvs/NanoHunter_boltz/bin/python'),str(helper),smiles,'0'],text=True))
    chosen=next(a['name'] for a in mapping['atoms'] if a['el']=='O')
    input_path=DEV/'acceptance_inputs/ligand.yaml'
    input_path.write_text("version: 1\nsequences:\n- protein:\n    id: A\n    sequence: "+'X'*65+"\n    msa: empty\n- ligand:\n    id: B\n    smiles: '"+smiles+"'\nconstraints:\n- pocket:\n    binder: A\n    contacts: [[B, "+chosen+"]]\n    max_distance: 6.0\n    force: true\n")
    args+=['--boltz-use-potentials']
request=dict(project='hunter-stages-acceptance',run_name=run_name,template_path=str(input_path),arguments=args)
(OUT/(run_name+'.request.json')).write_text(json.dumps(request,indent=2))
plan=iterative_plan(request)
(OUT/(run_name+'.plan.json')).write_text(json.dumps(plan,indent=2))
print(json.dumps(dict(plan_id=plan['id'],sha256=plan['sha256'],command=plan['command_preview']),indent=2))
if '--start' in sys.argv:
    job=start_job(plan['id'],plan['sha256'])
    (OUT/(run_name+'.job.json')).write_text(json.dumps(job,indent=2))
    print(json.dumps(job,indent=2))
