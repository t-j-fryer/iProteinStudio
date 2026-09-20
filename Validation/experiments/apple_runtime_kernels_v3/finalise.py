"""Require terminal broker jobs, re-audit outputs and record final integration facts."""
import importlib.metadata,json,os,sys
from pathlib import Path
from collections import Counter
from worker import atomic,sha
from report import main as report
REPO=Path(__file__).resolve().parents[3];OUT=REPO/'Validation/output/apple_runtime_kernels_v3'

def main():
    os.environ['NANOHUNTER_ROOT']=str(Path.home()/'.iproteinstudio')
    sys.path.insert(0,str(REPO/'Sources/iProteinStudio/Resources/pipeline/mcp'))
    from server import MCPServer
    server=MCPServer('run');statuses=[]
    for p in sorted(OUT.glob('*/submitted.json')):
        job=json.loads(p.read_text())
        status=server.tool_call('job_status',{'job_id':job['id']})
        statuses.append(dict(run=p.parent.name,**status))
    atomic(OUT/'terminal_status.json',statuses)
    if any(s['status'] not in ('completed','failed','cancelled') for s in statuses):
        raise RuntimeError('Benchmark jobs remain active')
    report()
    measurements=json.loads((OUT/'measurements.json').read_text())
    audit_errors=[]
    for p in OUT.glob('*/analysis.json'):
        d=json.loads(p.read_text())
        # A retained kernel numerical rejection is distinct from corrupt raw output.
        audit_errors.extend(dict(run=p.parent.name,**e) for e in d['errors'] if e.get('error')!='kernel numerical gate failed')
    if audit_errors:raise RuntimeError('Completed-output audit errors: '+str(audit_errors))
    recovered=[]
    for p in OUT.glob('*/recovery_resume.json'):
        saved=json.loads(p.read_text());progress=json.loads((p.parent/'progress.json').read_text())
        current=sha(Path(progress['variant'])/'completed.json')
        if saved['completed_variant_sha256']!=current:raise RuntimeError('Recovery changed completed variant')
        recovered.append(dict(run=p.parent.name,completed_variant_unchanged=True,
                              reference_attempts=len(list(p.parent.glob('reference/attempt_*.request.json')))))
    versions={}
    managed=Path.home()/'.iproteinstudio'
    for engine,pattern in [('boltz','venvs/NanoHunter_boltz/lib/python*/site-packages'),
                           ('protenix','venvs/NanoHunter_protenix/lib/python*/site-packages'),
                           ('nesso','components/nesso/v1.0.0-mps-1/venv/lib/python*/site-packages')]:
        sites=list(managed.glob(pattern))
        dist=[p for site in sites for p in site.glob('torch-*.dist-info')]
        if len(dist)!=1:raise RuntimeError('Ambiguous installed runtime for '+engine)
        versions[engine]=dist[0].name.removeprefix('torch-').removesuffix('.dist-info')
    if versions!={'boltz':'2.13.0','protenix':'2.7.1','nesso':'2.11.0'}:raise RuntimeError('Installed runtime changed')
    result=dict(status='bounded testing complete',job_counts=dict(Counter(s['status'] for s in statuses)),
                completed_blocks=measurements['completed_blocks'],completed_outputs=measurements['completed_units'],
                roles=dict(Counter('profiled' if u['measurement'].get('profiled') or '_profile_' in u['run'] else
                    'warmup' if u['measurement'].get('warmup') else 'measured' for u in measurements['units'])),
                completed_output_audit_errors=audit_errors,
                operator_cases=sum(len(k['rows']) for k in measurements['kernels']),
                operator_rejections=sum(not r['passed'] for k in measurements['kernels'] for r in k['rows']),
                recovery=recovered,installed_torch=versions,
                source_sha256={p.name:sha(p) for p in [REPO/'Sources/iProteinStudio/Resources/pipeline/scripts/nise/nesso_worker.py',*(REPO/'Sources/iProteinStudio/Resources/pipeline/scripts/nise').glob('nesso*cache.py'),
                    *[REPO/'Sources/iProteinStudio/Resources/pipeline/scripts'/name for name in ('intellifold_padding.py','intellifold_predict.py','resident_predictor.py')]]},
                limits=['One M4 Max','No MSA-rich interface/design campaign qualification for Metal kernels',
                        'Repeated-request memory checks, not multi-hour soak','No model/runtime version changes'])
    atomic(OUT/'FINAL_AUDIT.json',result);print(json.dumps(result))
if __name__=='__main__':main()
