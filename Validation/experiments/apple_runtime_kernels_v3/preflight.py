"""Fixed engine experiments, immutable snapshots and the shared Studio GPU broker."""
import argparse,ast,json,os,shutil,sys,subprocess
from pathlib import Path
from datetime import datetime,timezone
from worker import atomic,sha
HERE=Path(__file__).resolve().parent;REPO=HERE.parents[2]
OUT=REPO/'Validation/output/apple_runtime_kernels_v3'
V2=REPO/'Validation/output/apple_runtime_throughput_v2'
V1=REPO/'Validation/output/apple_runtime_throughput_v1'

def main():
    ap=argparse.ArgumentParser();ap.add_argument('engine',choices=['boltz','protenix','nesso','intellifold-flash'])
    ap.add_argument('stage',choices=['kernel','profile','cache','metal','soak','preprocess','preprocess_soak','conformers','conformer_soak','combined','padding','lean','norm_kernel'])
    ap.add_argument('--reverse',action='store_true');ap.add_argument('--seed',type=int,choices=[42,43],default=42);ap.add_argument('--larger',action='store_true');ap.add_argument('--start',action='store_true')
    args=ap.parse_args()
    key='intellifold' if args.engine=='intellifold-flash' else args.engine
    if args.stage=='padding' and key!='intellifold':raise RuntimeError('Padding applies only to IntelliFold')
    if key=='intellifold' and args.stage!='padding':raise RuntimeError('Only padding integration requested for IntelliFold')
    if os.environ.get('IPROTEINSTUDIO_AGENT_ROOT'):raise RuntimeError('Shared broker required')
    managed=Path(os.environ.get('NANOHUNTER_ROOT',Path.home()/'.iproteinstudio')).resolve()
    os.environ['NANOHUNTER_ROOT']=str(managed)
    sys.path.insert(0,str(REPO/'Sources/iProteinStudio/Resources/pipeline/mcp'))
    from server import MCPServer
    from iprotein_mcp.plans import _persist,_script_provenance
    server=MCPServer('run');guide=server.tool_call('workflow_guide',{'workflow':'prediction'})
    if args.stage in ('cache','soak','preprocess','preprocess_soak','conformers','conformer_soak','combined') and args.engine!='nesso':raise RuntimeError('Only NESSO cache implemented')
    if args.stage in ('metal','lean'):
        prior=list(OUT.glob(args.engine+'_kernel_*/baseline/attempt_*/kernel.json'))
        def shader(path):
            tree=ast.parse(path.read_text())
            return next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SOURCE' for t in n.targets))
        if not any(json.loads(p.read_text())['passed'] and (p.parent/'completed.json').exists() and shader(p.parents[2]/'frozen/metal_ops.py')==shader(HERE/'metal_ops.py') for p in prior):
            raise RuntimeError('Passing local-runtime kernel oracle required before inference')
    out=OUT/(args.engine+'_'+args.stage+'_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True);f=out/'frozen';f.mkdir()
    for p in HERE.iterdir():
        if p.suffix in ('.py','.json','.metal'):shutil.copy2(p,f/p.name)
    scripts=f/'scripts'
    shutil.copytree(REPO/'Sources/iProteinStudio/Resources/pipeline/scripts',scripts,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    if args.engine=='boltz':
        seal=V1/'boltz-torch213.seal.json';root=managed;version='2.13.0'
        atomic(f/'source.seal.json',dict(root=str(scripts),files={str(p.relative_to(scripts)):sha(p) for p in scripts.rglob('*') if p.is_file()}))
    else:
        seal=V2/(key+'-baseline.seal.json');root=V2/'roots'/key
        version={'protenix':'2.7.1','nesso':'2.11.0','intellifold':'2.6.0'}[key]
        shutil.copy2(V2/(key+'.source.json'),f/'source.seal.json')
    shutil.copy2(seal,f/'baseline.seal.json')
    # Protenix helpers look beneath root/scripts; the sealed upstream tree remains unchanged.
    if key in ('protenix','intellifold'):
        local=f/'root';local.mkdir();(local/'scripts').symlink_to(scripts)
        for p in root.iterdir():
            if p.name!='scripts':(local/p.name).symlink_to(p)
        root=local
    spec=json.loads((HERE/'manifest.json').read_text());fixtures=spec['cases']
    if args.larger:fixtures=fixtures+[dict(name='ubiquitin_repeat228',sequence=fixtures[0]['sequence']*3)]
    cases=[dict(**fixtures[0],warmup=True)]+[dict(**x,warmup=False) for x in fixtures]
    if args.stage in ('soak','preprocess_soak','conformer_soak'):
        ligands=['CC(=O)O','c1ccccc1O','CCO','O=C(O)CCCC[C@@H]1SC[C@@H]2NC(=O)N[C@@H]21']
        cases=[dict(**x,warmup=i<2,smiles=ligands[i%4]) for i,x in enumerate(fixtures*4)]
    variants=[('reference','uncached'),('variant',None)] if args.stage in ('cache','soak') else [('reference',None),('variant','metal')]
    if args.stage=='padding':variants=[('reference','padding256'),('variant','buckets128')]
    if args.stage=='combined':variants=[('reference','uncached'),('variant','conformer_cache')]
    if args.stage=='lean':variants=[('reference',None),('variant','metal_lean')]
    if args.stage in ('conformers','conformer_soak'):variants=[('reference',None),('variant','conformer_cache')]
    if args.stage in ('preprocess','preprocess_soak'):variants=[('reference',None),('variant','preprocess')]
    if args.stage in ('kernel','norm_kernel','profile'):variants=[('baseline',None)]
    if args.reverse:variants.reverse()
    blocks=[dict(id=i,runtime='baseline',torch_version=version,variant=v,engine=args.engine,seed=args.seed,threads=4,
                 cases=[] if args.stage in ('kernel','norm_kernel') else cases,diagnostic=args.stage if args.stage in ('kernel','norm_kernel') else None,
                 detailed_profile=args.stage=='profile') for i,v in variants]
    cfg=dict(output=str(out),root=str(root),scripts=str(scripts),managed_root=str(managed),
             seals={'baseline':str(f/'baseline.seal.json')},source_seal=str(f/'source.seal.json'),blocks=blocks)
    atomic(f/'run.json',cfg);atomic(out/'workflow_guide.json',guide)
    atomic(out/'host.json',{k:subprocess.check_output(c,text=True).strip() for k,c in {
        'chip':['sysctl','-n','machdep.cpu.brand_string'],'os':['sw_vers'],'commit':['git','-C',str(REPO),'rev-parse','HEAD']}.items()})
    assets=[]
    if args.engine=='nesso':
        base=managed/'components/nesso/v1.0.0-mps-1'
        assets=[base/'receipt.json',*[base/p for p in json.loads((base/'receipt.json').read_text())['files'] if not p.startswith('venv/')]]
    else:
        model=managed/'models'/('boltz2' if args.engine=='boltz' else key)
        assets=[p for p in model.rglob('*') if p.is_file() and p.suffix in ('.ckpt','.pt','.pkl','.json','.npz')]
    command=['/usr/bin/caffeinate','-dimsu',sys.executable,str(f/'coordinator.py'),'--manifest',str(f/'run.json')]
    provenance=_script_provenance([p for p in f.rglob('*') if p.is_file()]+assets+[Path(sys.executable).resolve()])
    normalized=dict(workflow='runtime_benchmark',output=str(out),scheduler='serial complete-model blocks under shared GPU lease',
                    steps=[dict(stage='runtime-benchmark',command=command,cwd=str(out))])
    plan=_persist('desktop_runtime_benchmark','validation-runtime-benchmark',normalized,command,'apple_gpu_exclusive',provenance)
    atomic(out/'plan.json',plan);print(json.dumps(dict(output=str(out),plan_id=plan['id'],plan_sha256=plan['sha256'])),flush=True)
    if args.start:
        job=server.tool_call('job_start',{'plan_id':plan['id'],'plan_sha256':plan['sha256']});atomic(out/'submitted.json',job);print(json.dumps(job),flush=True)
if __name__=='__main__':main()
