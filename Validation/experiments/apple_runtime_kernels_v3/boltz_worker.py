"""Boltz2 fixed scientific settings; potentials retained throughout."""
import json,sys,time,resource
from pathlib import Path
from worker import atomic,sha

def run_boltz(req,out,request,start):
    import torch,yaml
    if req.get('diagnostic')=='kernel':
        from kernel_benchmark import run
        atomic(out/'kernel.json',run(torch))
    else:
        import resident_predictor as rp
        config=dict(root=req['root'],use_potentials=True,engine_args=['--accelerator','gpu','--devices','1',
            '--num_workers','0','--preprocessing-threads','1','--recycling_steps','3','--sampling_steps','200',
            '--diffusion_samples','1','--write_full_pae','--cache',str(Path(req['managed_root'])/'models/boltz2')])
        load=time.monotonic();session=rp.BoltzSession(config);load=time.monotonic()-load
        assert session.model.predict_args['sampling_steps']==200 and session.model.predict_args['recycling_steps']==3
        assert session.model.steering_args['fk_steering'] and session.model.steering_args['physical_guidance_update']
        atomic(out/'effective.json',dict(config=config,predict_args=session.model.predict_args,steering_args=session.model.steering_args))
        telemetry={}
        if req.get('variant') in ('metal','metal_lean'):
            from fusion import install
            telemetry=install(session.model,'boltz',torch,lean=req['variant']=='metal_lean')
        if req.get('detailed_profile'):
            from module_profile import install
            telemetry=install(session.model,torch)
        rows=[]
        for i,case in enumerate(req['cases']):
            unit=out/f'unit_{i:02d}';source=unit/'input';source.mkdir(parents=True)
            (source/(case['name']+'.yaml')).write_text(yaml.safe_dump(dict(version=1,sequences=[dict(protein=dict(id='A',sequence=case['sequence'],msa='empty'))])))
            session.request_seed=req['seed'];session.request_phase='structure'
            torch.mps.synchronize();t=time.monotonic();c=time.process_time()
            session.predict(source,unit/'prediction',1)
            torch.mps.synchronize()
            row=dict(name=case['name'],sequence=case['sequence'],seed=req['seed'],warmup=case.get('warmup',False),profiled=req.get('detailed_profile',False),
                     seconds=time.monotonic()-t,cpu_seconds=time.process_time()-c,torch=torch.__version__,threads=torch.get_num_threads(),
                     mps_bytes=torch.mps.driver_allocated_memory(),rss_peak_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            atomic(unit/'measurement.json',row);rows.append(str(unit/'measurement.json'));atomic(out/'telemetry.json',telemetry)
            print('BENCH_UNIT|'+json.dumps(row),flush=True)
        atomic(out/'result.json',dict(rows=rows,model_load_seconds=load,process_seconds=time.monotonic()-start))
    atomic(out/'completed.json',dict(request_sha256=sha(request),files={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file()}))
