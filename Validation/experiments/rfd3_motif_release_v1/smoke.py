"""Public MCP plans and jobs for corrected motif/partial runtime acceptance."""
import json,os,sys,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'Validation/output/rfd3_motif_release_v1'
managed=Path.home()/'.iproteinstudio';os.environ['NANOHUNTER_ROOT']=str(managed);os.environ['DEBUG']='false'
sys.path.insert(0,str(managed/'mcp'))
from server import MCPServer
from iprotein_mcp.common import project_root
server=MCPServer('run');project='rfd3_motif_release_v1'
project_root(project,create=True)
name=sys.argv[1];mode={'motif':'motifScaffolding','partial':'partialDiffusion'}[name]
folder=OUT/name;folder.mkdir(exist_ok=True)
def save(n,data): (folder/n).write_text(json.dumps(data,indent=2)+'\n')
if len(sys.argv)>2 and sys.argv[2]=='status':
 job=server.tool_call('job_status',{'job_id':json.loads((folder/'job.json').read_text())['id']});save('latest.json',job)
 print(json.dumps({k:job.get(k) for k in ('id','status','stage','message','error','output_root','pipeline_log_tail')},indent=2));sys.exit()
if (folder/'job.json').exists():raise RuntimeError('Already submitted; use status')
workflow='rfd3_motif_scaffolding' if name=='motif' else 'rfd3_partial_diffusion'
save('guide.json',server.tool_call('workflow_guide',{'workflow':workflow}))
structure=project_root(project)/'motif-reference.pdb'
if not structure.exists(): shutil.copy2(ROOT/'Sources/iProteinStudio/Resources/examples/p53_mdm2/1YCR.pdb',structure)
save('inspection.json',server.tool_call('target_inspect',{'kind':'protein','structure':str(structure),'chains':['A','B']}))
request=dict(target_kind='protein',target_structure=str(structure),target_chain='A',target_chains=['A'],target_sequence='ETLVRPKPLLLKLLKSVGAQKDTYTMKEVLFYLGQYIMTKRLYDEKQQHIVYCSNDLLGDLFGVPSFSVKEHRKIYTMIYRNLVV',source_binder_chain='B',lengths=[70],num_backbones=1,batch_size=1,queues_per_bin=1,timesteps=200,recycles=2,precision='bf16',seed_base=1,sequences_per_backbone=1,top_n=1,sequence_model='solublempnn',extra_predictors=['boltz'],run_apo=True,boltz_calibrate_n=1)
if name=='motif':request['motif_sites']={'B19':'CG,CE1,CZ','B23':'CG,NE1,CH2','B26':'CG,CD1,CD2'}
else:request.update(partial_t=1.0,preserve_partial_sequence=True)
save('request.json',request)
plan=server.tool_call(workflow+'_plan',{'project':project,'run_name':name+'-corrected','request':request});save('plan.json',plan)
job=server.tool_call('job_start',{'plan_id':plan['id'],'plan_sha256':plan['sha256']});save('job.json',job)
print(json.dumps({k:job.get(k) for k in ('id','status','stage','message','error','output_root')},indent=2))
