"""Real offline inference plus committed-unit interruption/resume qualification."""
import argparse,json,os,subprocess,sys,time
from pathlib import Path

def run(config):
    cfg=json.loads(Path(config).read_text());out=Path(cfg['output']);sys.path.insert(0,str(Path(cfg['adapter']).parent))
    from runtime_package import verify
    from esmfold2_predict import sha, atomic
    verify(Path(cfg['package']),cfg['package_sha256'],'esmfold2')
    assets=json.loads((Path(cfg['adapter']).parent/'runtime_assets.json').read_text())['assets']
    for key in ('esmfold2','esmfold2_full','esmfold2_fast'):
        for a in assets[key]:
            if sha(Path(cfg['root'])/a['path'])!=a['sha256']:raise RuntimeError('Model checksum mismatch: '+a['path'])
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','PYTORCH_ENABLE_MPS_FALLBACK':'0','IPROTEINSTUDIO_LIVE_RESULTS_ROOT':str(out),'MPLCONFIGDIR':str(out/'matplotlib')}
    rows=[]
    for model in ('fast','full'):
        dest=out/model;log=out/(model+'.log')
        command=[cfg['python'],cfg['adapter'],'--inputs',cfg['inputs'],'--output',str(dest),'--nanohunter-root',cfg['root'],'--model',model]
        t=time.perf_counter()
        with log.open('w') as stream:
            process=subprocess.Popen(command,env=env,stdout=stream,stderr=subprocess.STDOUT)
            # Cancel while later inputs are in flight, keeping an atomic first result.
            first=dest/'a_monomer/complete.json'
            deadline=time.monotonic()+600
            while not first.exists() and process.poll() is None:
                if time.monotonic()>deadline:process.terminate();process.wait();raise RuntimeError('First prediction timeout')
                time.sleep(.1)
            if not first.exists():raise RuntimeError('Predictor failed; see '+str(log))
            before=sha(first)
            if process.poll() is None:process.terminate();process.wait(timeout=30)
            cancelled_return=process.returncode
        with log.open('a') as stream:subprocess.run(command,env=env,stdout=stream,stderr=subprocess.STDOUT,check=True)
        if sha(first)!=before:raise RuntimeError('Completed first unit changed on resume')
        receipts=list(dest.glob('*/complete.json'))
        if len(receipts)!=6:raise RuntimeError('Output cardinality mismatch')
        for receipt in receipts:
            record=json.loads(receipt.read_text())
            for name,digest in record['files'].items():
                if sha(receipt.parent/name)!=digest:raise RuntimeError('Output inventory failed')
        rows.append(dict(model=model,units=6,interrupted_returncode=cancelled_return,resume_preserved_first=True,wall_seconds=time.perf_counter()-t,receipts=[str(p.relative_to(out)) for p in receipts]))
        atomic(out/'progress.json',dict(completed=rows))
    atomic(out/'completed.json',dict(rows=rows,live_records=len(list((out/'.studio_live_results').glob('*.json')))))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);a=p.parse_args();run(a.config)
