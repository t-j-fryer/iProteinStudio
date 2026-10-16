"""Resident, paired affinity replay; original structures and geometry stay fixed."""
import hashlib
import json
import math
import os
from pathlib import Path
import random
import resource
import shutil
import subprocess
import sys
import time
from common import sha, save, seal, verified


def stage(unit,cases):
    source=unit/'yaml';source.mkdir(parents=True)
    result=unit/'prediction/boltz_results_yaml'
    for case in cases:
        frozen=Path(case['directory']);name=case['name']
        shutil.copy2(frozen/(name+'.yaml'),source)
        for path in (frozen/'processed').rglob('*'):
            if not path.is_file() or path.name=='manifest.json':
                continue
            dst=result/'processed'/path.relative_to(frozen/'processed')
            dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dst)
        shutil.copytree(frozen/'prediction',result/'predictions'/name)
    return source


class Replay:
    def __init__(self,cfg):
        self.cfg=cfg; self.current={};self.events=[];self.features={};self.repeat=0
        sys.path.insert(0,cfg['scripts'])
        import resident_predictor
        import numpy as np
        import torch
        self.np=np;self.torch=torch
        torch.set_num_threads(4);torch.set_num_interop_threads(1)
        self.start=time.perf_counter()
        args=['--accelerator','gpu','--devices','1','--num_workers','0',
              '--preprocessing-threads','1','--recycling_steps','3','--sampling_steps','25',
              '--diffusion_samples','1','--sampling_steps_affinity','200',
              '--diffusion_samples_affinity','5','--cache',str(Path(cfg['root'])/'models/boltz2')]
        self.session=resident_predictor.BoltzSession(dict(root=cfg['root'],engine_args=args,
                                                        allow_affinity=True,use_potentials=True))
        self.load_seconds=time.perf_counter()-self.start
        cache=self.session.checkpoints;original_load=cache.load
        def load(path,*args,**kwargs):
            model=original_load(path,*args,**kwargs)
            if Path(path).resolve()==cache.affinity_path:
                # Native cache intentionally freezes production settings. This experiment
                # explicitly updates only the two controls being compared on the same weights.
                model.predict_args=dict(kwargs['predict_args'])
                assert model.predict_args['recycling_steps']==5
                assert model.predict_args['sampling_steps']==self.arm['steps']
                assert model.predict_args['diffusion_samples']==self.arm['samples']
                assert not any(model.steering_args[k] for k in
                               ('fk_steering','physical_guidance_update','contact_guidance_update'))
                if not hasattr(model,'_benchmark_wrapped'):
                    original_step=model.predict_step
                    def step(batch,batch_idx,dataloader_idx=0):
                        name=batch['record'][0].id
                        self.seed(name);t=time.perf_counter()
                        result=original_step(batch,batch_idx,dataloader_idx)
                        if result.get('exception'):
                            raise RuntimeError('Affinity model failed: '+name)
                        self.events.append(dict(name=name,host_predict_seconds=time.perf_counter()-t,
                            mps_current_bytes=torch.mps.current_allocated_memory(),
                            mps_driver_bytes=torch.mps.driver_allocated_memory(),
                            process_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss))
                        return result
                    model.predict_step=step;model._benchmark_wrapped=True
            return model
        cache.load=load
        # Never accidentally rerun the outer structure model.
        def forbidden(*args,**kwargs):
            raise RuntimeError('Outer structure prediction is forbidden in affinity replay')
        self.session.model.predict_step=forbidden
        from boltz.data.module.inferencev2 import PredictionDataset
        original_get=PredictionDataset.__getitem__
        def get(dataset,idx):
            name=dataset.manifest.records[idx].id;self.seed(name)
            result=original_get(dataset,idx)
            assert result['record'].id==name, 'Upstream failed-input substitution is forbidden'
            h=hashlib.sha256()
            for key in sorted(result):
                value=result[key]
                if isinstance(value,torch.Tensor):
                    assert value.device.type=='cpu'
                    h.update(key.encode());h.update(str(value.dtype).encode());h.update(str(tuple(value.shape)).encode())
                    h.update(value.contiguous().numpy().tobytes())
            self.features[name]=h.hexdigest()
            return result
        PredictionDataset.__getitem__=get

    def seed(self,name):
        value=self.current[name]['seed']+self.repeat*10000
        random.seed(value);self.np.random.seed(value);self.torch.manual_seed(value);self.torch.mps.manual_seed(value)

    def batch(self,path,cases,arm,repeat):
        if verified(path) is not None:
            return verified(path)
        if path.exists():
            path.rename(path.with_name(path.name+f'.interrupted-{time.time_ns()}'))
        path.mkdir(parents=True)
        source=stage(path,cases)
        self.current={c['name']:c for c in cases}
        if len(self.current)!=len(cases):raise RuntimeError('Colliding original candidate names')
        self.repeat=repeat;self.arm=arm;self.events=[];self.features={}
        for option,value in [('--sampling_steps_affinity',arm['steps']),('--diffusion_samples_affinity',arm['samples'])]:
            self.session.arguments[self.session.arguments.index(option)+1]=str(value)
        self.session.request_phase='affinity';self.session.request_seed=101600+repeat*10000
        before={c['key']:sha(Path(c['directory'])/'prediction'/f"pre_affinity_{c['name']}.npz") for c in cases}
        self.torch.mps.synchronize();start=time.perf_counter();cpu=time.process_time()
        self.session.predict(source,path/'prediction',len(cases))
        self.torch.mps.synchronize();elapsed=time.perf_counter()-start
        model=self.session.checkpoints.affinity_model
        assert self.session.model_load_count==2 and model is not None
        assert len(self.events)==len(cases)
        assert {e['name'] for e in self.events}==set(self.current)
        rows=[]
        for case in cases:
            name=case['name'];leaf=path/'prediction/boltz_results_yaml/predictions'/name
            assert sha(leaf/f'pre_affinity_{name}.npz')==before[case['key']]
            for original in (Path(case['directory'])/'prediction').glob('*_model_0.*'):
                assert sha(leaf/original.name)==sha(original), 'Outer structure/confidence changed'
            obj=json.loads((leaf/f'affinity_{name}.json').read_text())
            assert all(math.isfinite(v) for v in obj.values())
            pbind=obj['affinity_probability_binary'];assert 0<=pbind<=1
            rows.append(dict(key=case['key'],generator=case['generator'],historical_pbind=case['pbind'],
                             pbind=pbind,score=pbind+case['ligand_plddt']/100,
                             feature_sha256=self.features[name],**obj))
        result=dict(arm=arm,repeat=repeat,elapsed_seconds=elapsed,cpu_seconds=time.process_time()-cpu,
                    rows=rows,events=self.events,predict_args=model.predict_args,
                    model_load_count=self.session.model_load_count,
                    timing_scope='resident directory request including features, affinity inference, writes and native output audit; staging excluded')
        save(path/'results.json',result);seal(path,result)
        print(json.dumps(dict(batch=str(path),n=len(rows),seconds=elapsed,arm=arm['name'])),flush=True)
        return result


def cpu_job(cfg,config,mode,path,workers):
    py=cfg['laser_python'] if mode=='laser' else cfg['python']
    path.parent.mkdir(parents=True,exist_ok=True)
    log=path.with_suffix('.log').open('a')
    proc=subprocess.Popen([py,'-B',str(Path(__file__).with_name('cpu.py')),str(config),mode,str(path),str(workers)],
                          stdout=log,stderr=subprocess.STDOUT)
    return proc,log


def finish_cpu(jobs):
    try:
        for proc,log in jobs:
            code=proc.wait();log.close()
            if code:raise RuntimeError(f'CPU qualification subprocess failed with {code}')
    finally:
        for proc,log in jobs:
            if proc.poll() is None:proc.terminate();proc.wait()
            log.close()


def main(config,audit_only=False):
    cfg=json.loads(config.read_text());out=Path(cfg['output'])
    for p,digest in cfg['frozen_inputs_sha256'].items():
        if sha(p)!=digest:raise RuntimeError('Frozen input/code changed: '+p)
    # Audit saved coordinates and identity before loading models.
    import numpy as np
    import gemmi
    import yaml
    for case in cfg['cases']:
        structure=gemmi.read_structure(case['pdb'])
        sequence=''.join(gemmi.find_tabulated_residue(r.name).one_letter_code for r in structure[0]['A'])
        assert sequence==case['sequence']
        assert all(np.isfinite([a.pos.x,a.pos.y,a.pos.z]).all() for c in structure[0] for r in c for a in r)
        document=yaml.safe_load((Path(case['directory'])/(case['name']+'.yaml')).read_text())
        geometry=json.loads((Path(case['directory'])/'geometry_settings.json').read_text())
        assert geometry['exposure_mode']=='biotin-carboxamide-v1' and len(geometry['hotspot_atoms'])==9
        assert geometry['exposed_atoms'] and geometry['hotspot_distance']>0
        for item in document['sequences']:
            if 'protein' in item:assert item['protein'].get('msa')=='empty'
    if audit_only:
        print(json.dumps(dict(input_audit_passed=True,cases=len(cfg['cases']))));return
    save(out/'runtime_host.json',{k:subprocess.check_output(cmd,text=True).strip() for k,cmd in {
        'chip':['/usr/sbin/sysctl','-n','machdep.cpu.brand_string'],
        'memory_bytes':['/usr/sbin/sysctl','-n','hw.memsize'], 'os':['/usr/bin/sw_vers']}.items()})
    replay=Replay(cfg)
    # Four real inputs, both settings, before the larger paired cohort.
    for generator in ('boltz','rfd3'):
        cases=[c for c in cfg['cases'] if c['generator']==generator]
        for arm in cfg['arms']:
            replay.batch(out/'smoke'/generator/arm['name'],[cases[0],cases[-1]],arm,0)
    save(out/'smoke_passed.json',dict(cases=4,settings=cfg['arms'],load_seconds=replay.load_seconds))
    batches=[]
    for repeat in range(cfg['repeats']):
        arms=cfg['arms'] if repeat==0 else cfg['arms'][::-1]
        for arm in arms:
            for generator in ('boltz','rfd3'):
                cases=[c for c in cfg['cases'] if c['generator']==generator]
                for offset in range(0,len(cases),cfg['batch_size']):
                    batches.append(replay.batch(out/f'r{repeat}'/arm['name']/f'{generator}_{offset:02d}',
                                               cases[offset:offset+cfg['batch_size']],arm,repeat))
    save(out/'affinity_results.json',dict(batches=batches))
    same_seed=[]
    for generator in ('boltz','rfd3'):
        cases=[c for c in cfg['cases'] if c['generator']==generator][:4]
        for arm in cfg['arms']:
            same_seed.append(replay.batch(out/'same_seed'/generator/arm['name'],cases,arm,0))
    save(out/'same_seed_results.json',dict(batches=same_seed))
    # Isolated geometry throughput, including pool startup; reverse worker order on repeat.
    geometry=[]
    for repeat in range(2):
        for workers in ([1,2,4,8] if repeat==0 else [8,4,2,1]):
            path=out/'isolated_geometry'/f'r{repeat}_w{workers}'
            finish_cpu([cpu_job(cfg,config,'geometry',path,workers)])
            geometry.append(verified(path))
    reference={r['key']:r['result'] for r in geometry[0]['rows']}
    assert all({r['key']:r['result'] for r in g['rows']}==reference for g in geometry)
    save(out/'geometry_results.json',dict(passed=True,arms=geometry))
    # Same independent CPU and GPU work, serial versus overlapped. Two repeats,
    # alternating order. No same-lineage dependency is violated: frozen input replay.
    overlaps=[]
    for repeat in range(2):
        for mode in (['serial','overlap'] if repeat==0 else ['overlap','serial']):
            path=out/'overlap'/f'r{repeat}_{mode}'
            if verified(path) is not None:
                overlaps.append(verified(path));continue
            if path.exists():path.rename(path.with_name(path.name+f'.interrupted-{time.time_ns()}'))
            path.mkdir(parents=True)
            start=time.perf_counter()
            jobs=[cpu_job(cfg,config,'laser',path/'laser',2),cpu_job(cfg,config,'geometry',path/'geometry',2)]
            try:
                if mode=='serial':finish_cpu(jobs)
                gpu=replay.batch(path/'affinity',cfg['cases'][:8],cfg['arms'][1],repeat)
                if mode=='overlap':finish_cpu(jobs)
            finally:
                for proc,log in jobs:
                    if proc.poll() is None:proc.terminate();proc.wait()
                    log.close()
            result=dict(mode=mode,repeat=repeat,elapsed_seconds=time.perf_counter()-start,
                        gpu=gpu,laser=verified(path/'laser'),geometry=verified(path/'geometry'))
            seal(path,result);overlaps.append(result)
    save(out/'overlap_results.json',dict(arms=overlaps))
    from analyse import analyse
    analyse(cfg)


if __name__=='__main__':main(Path(sys.argv[1]),'--audit-inputs' in sys.argv)
