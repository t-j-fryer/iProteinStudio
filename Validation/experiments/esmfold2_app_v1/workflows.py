"""Exercise real Predict and shared RFD3/post-screen adapter orchestration."""
import argparse,csv,json,os,subprocess,sys
from pathlib import Path

def run(path):
    c=json.loads(Path(path).read_text());out=Path(c['output']);root=Path(c['root']);scripts=root/'scripts'
    os.environ.update(NANOHUNTER_ROOT=str(root), PYTHONPATH=str(scripts),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',IPROTEINSTUDIO_LIVE_RESULTS_ROOT=str(out))
    sys.path.insert(0,str(scripts))
    from esmfold2_predict import atomic,sha
    import yaml
    native=yaml.safe_load((Path(c['inputs'])/'c_biotin.yaml').read_text())
    chains=[dict(kind=kind,**item) for entry in native['sequences'] for kind,item in entry.items()]
    cfg=dict(root=str(root),output=str(out/'predict'),predictors=['esmfold2-fast-mlx'],seed=42,num_seeds=2,diffusion_samples=2,
             jobs=[dict(name='biotin',chains=chains)],msa=dict(cache_dir=str(out/'msa_cache'),allow_server=False,index_roots=[]))
    atomic(out/'predict_config.json',cfg)
    cmd=[sys.executable,str(out/'workflows/rfd3/predict_batch.py'),'--config',str(out/'predict_config.json')]
    with (out/'predict.log').open('w') as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
    receipts=list((out/'predict').rglob('complete.json'))
    if len(receipts)!=1:raise RuntimeError('Predict adapter receipt count')
    before=sha(receipts[0])
    with (out/'predict.log').open('a') as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
    if sha(receipts[0])!=before:raise RuntimeError('Predict changed completed outputs on resume')
    native_output=receipts[0].parent
    if len(list(native_output.glob('confidence_*.json')))!=4:raise RuntimeError('Predict multi-seed/sample cardinality')
    # RFD3 uses a directory of complete MPNN inputs; no new backbones are generated.
    inputs=out/'rfd_inputs';inputs.mkdir()
    for name in ('one','two'):(inputs/(name+'.yaml')).write_text(yaml.safe_dump(native))
    cmd=[sys.executable,str(out/'workflows/rfd3_overlay/scripts/run_predictors.py'),'--inputs',str(inputs),
        '--output',str(out/'rfd_checks'),'--predictors','esmfold2-fast-mlx','--nanohunter-root',str(root),'--resume']
    with (out/'rfd_checks.log').open('w') as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
    with (out/'rfd_checks.log').open('a') as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
    rows=list(csv.DictReader((out/'rfd_checks/prediction_metrics.csv').open()))
    if len(rows)!=2 or any(int(r['exit_code']) or r['reused']!='1' for r in rows):raise RuntimeError('RFD3 receipt/result reuse failed')
    atomic(out/'completed.json',dict(predict_samples=4,predict_resume_preserved=True,rfd3_inputs=2,rfd3_reused=True))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);a=p.parse_args();run(a.config)
