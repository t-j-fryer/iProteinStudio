#!/usr/bin/env python3
"""One experimental process, using the existing model-owning Studio adapter."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import time


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(8*1024*1024), b''): h.update(b)
    return h.hexdigest()


def atomic(path, value):
    tmp = path.with_suffix('.part')
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n'); tmp.replace(path)


def oracle(torch):
    """Independent CPU-FP64 checks on bounded synthetic tensor workloads."""
    rows = []
    generator = torch.Generator(device='cpu').manual_seed(1841)
    for size in (16, 64, 129, 257):
        a = torch.randn(size, size, generator=generator, dtype=torch.float32)
        b = torch.randn(size, size, generator=generator, dtype=torch.float32)
        ref = (a.double() @ b.double()).float()
        got = (a.to('mps') @ b.to('mps')).cpu()
        error = (got-ref).abs()
        rows.append(dict(operation='matmul', shape=[size,size], max_absolute=float(error.max()),
                         relative_l2=float(torch.linalg.vector_norm(error)/torch.linalg.vector_norm(ref)),
                         passed=bool(torch.allclose(got,ref,atol=1e-4,rtol=1e-4))))
    # Reuse varied allocations and test the M1 indexing dimension implicated in prior failures.
    for repeat in range(12):
        a = torch.randn(540+repeat, 32, generator=generator)
        index = torch.arange(0, len(a), 2)
        got = a.to('mps').index_select(0,index.to('mps')).cpu()
        rows.append(dict(operation='index_select',shape=list(a.shape),passed=bool(torch.equal(got,a[index]))))
    if not all(row['passed'] for row in rows):
        raise RuntimeError('Independent primitive numerical gate failed: '+json.dumps(rows))
    return rows


def extract(structure, confidence, pae, sequence, geometry):
    import gemmi
    import numpy as np
    st = gemmi.read_structure(str(structure))
    ca=[]; identities=[]; observed=''
    for chain in st[0]:
        for res in chain:
            if not res.find_atom('CA','*'): continue
            observed += gemmi.find_tabulated_residue(res.name).one_letter_code
            for atom in res:
                p=atom.pos
                if not all(np.isfinite([p.x,p.y,p.z])): raise RuntimeError('Nonfinite coordinate')
                identities.append([chain.name,str(res.seqid),res.name,atom.name])
                if atom.name=='CA':ca.append([p.x,p.y,p.z])
    if observed != sequence: raise RuntimeError(f'Output sequence mismatch: {observed}')
    matrix=np.load(pae)['pae']
    if matrix.shape != (len(sequence),len(sequence)) or not np.isfinite(matrix).all():
        raise RuntimeError('Invalid PAE shape/values')
    values=json.loads(confidence.read_text())
    for key in ('complex_plddt','ptm'):
        if key not in values or not np.isfinite(values[key]):raise RuntimeError('Missing confidence '+key)
    quality=geometry.inspect_geometry(structure)
    if quality['errors']: raise RuntimeError('Geometry input errors: '+str(quality['errors']))
    return dict(ca=ca,atom_identities=identities,sequence=observed,confidence=values,
                geometry=quality,pae_path=str(pae))


def main():
    started=time.monotonic()
    ap=argparse.ArgumentParser(); ap.add_argument('--request',type=Path,required=True); args=ap.parse_args()
    request=json.loads(args.request.read_text()); out=Path(request['output'])
    if out.exists():raise SystemExit('Worker output already exists; use a new attempt directory')
    out.mkdir(parents=True)
    import torch
    if torch.__version__.split('+')[0] != request['torch_version']:raise RuntimeError('Wrong Torch runtime')
    if not torch.backends.mps.is_available():raise RuntimeError('MPS unavailable')
    torch.set_num_threads(request['threads']); torch.set_num_interop_threads(1)
    primitive=oracle(torch)
    atomic(out/'oracle.json',primitive)
    sys.path.insert(0,request['scripts'])
    import resident_predictor
    import validate_prediction_geometry as geometry
    engine_args=['--accelerator','gpu','--devices','1','--num_workers','0',
                 '--preprocessing-threads','1','--recycling_steps','3','--sampling_steps','200',
                 '--diffusion_samples','1','--write_full_pae','--cache',request['model_cache']]
    config=dict(root=request['root'],engine_args=engine_args,use_potentials=True)
    before=time.monotonic(); session=resident_predictor.BoltzSession(config)
    load_seconds=time.monotonic()-before
    if session.model.predict_args['sampling_steps']!=200 or session.model.predict_args['recycling_steps']!=3 or session.model.predict_args['diffusion_samples']!=1:
        raise RuntimeError('Effective scientific settings mismatch')
    if not session.model.steering_args['fk_steering'] or not session.model.steering_args['physical_guidance_update']:
        raise RuntimeError('Guidance unexpectedly disabled')
    atomic(out/'effective_model.json',dict(predict_args=session.model.predict_args,steering_args=session.model.steering_args,parameter_dtypes=sorted({str(p.dtype) for p in session.model.parameters()})))
    setup_seconds=time.monotonic()-started
    variant_telemetry=None
    if request.get('variant'):
        if request['variant']=='schedule_host_once':
            from equivalent_schedule import install
            variant_telemetry=install(session)
        elif request['variant']=='diffusion_bf16':
            from selective_precision import install
            variant_telemetry=install(session,torch)
        else:raise RuntimeError('Unknown experimental variant')
        atomic(out/'variant.json',variant_telemetry)
    profile=None
    if request.get('profile'):
        from profile_stages import StageProfile
        profile=StageProfile(session,torch)
    rows=[]
    for i,case in enumerate(request['cases']):
        unit=out/f'unit_{i:02d}'; source=unit/'input'; source.mkdir(parents=True)
        import yaml
        (source/(case['name']+'.yaml')).write_text(yaml.safe_dump(dict(version=1,sequences=[
            {'protein':dict(id='A',sequence=case['sequence'],msa='empty')}]),sort_keys=False))
        session.request_seed=case['seed']; session.request_phase='structure'
        if profile:profile.reset()
        cpu_before=time.process_time()
        torch.mps.synchronize(); before=time.monotonic()
        session.predict(source,unit/'prediction',1)
        torch.mps.synchronize(); seconds=time.monotonic()-before
        leaf=unit/'prediction/boltz_results_input/predictions'/case['name']
        structures=list(leaf.glob('*.cif')); confidences=list(leaf.glob('confidence_*_model_0.json')); paes=list(leaf.glob('pae_*_model_0.npz'))
        if not (len(structures)==len(confidences)==len(paes)==1):raise RuntimeError('Incorrect prediction output cardinality')
        result=extract(structures[0],confidences[0],paes[0],case['sequence'],geometry)
        result.update(name=case['name'],seed=case['seed'],warmup=case['warmup'],seconds=seconds,
                      torch=torch.__version__,threads=torch.get_num_threads(),interop_threads=torch.get_num_interop_threads(),
                      process_cpu_seconds=time.process_time()-cpu_before,
                      mps_current_bytes=torch.mps.current_allocated_memory(),mps_driver_bytes=torch.mps.driver_allocated_memory(),
                      rss_peak_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                      model_load_count=session.model_load_count)
        if profile:result['profile']=profile.report()
        atomic(unit/'measurement.json',result)
        rows.append(str(unit/'measurement.json'))
        print('BENCH_UNIT|'+json.dumps({k:result[k] for k in ('name','seed','warmup','seconds','threads','torch')}),flush=True)
    if variant_telemetry:atomic(out/'variant.json',variant_telemetry)
    torch.mps.synchronize()
    atomic(out/'result.json',dict(rows=rows,model_load_seconds=load_seconds,setup_seconds=setup_seconds,
                                 process_seconds=time.monotonic()-started,oracle_passed=True,
                                 effective_environment={k:os.environ.get(k) for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS','PYTORCH_ENABLE_MPS_FALLBACK','PYTORCH_MPS_FAST_MATH','PYTORCH_MPS_PREFER_METAL')}))
    files={str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    atomic(out/'completed.json',dict(request_sha256=sha(args.request),files=files))


if __name__=='__main__':main()
