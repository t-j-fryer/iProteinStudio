"""Unmodified upstream MLX model on frozen host features and local weights."""
from __future__ import annotations
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import resource
import sys
import time
import traceback
sys.dont_write_bytecode=True
from common import atomic, sha

def main(cfg, block):
    process_started=time.perf_counter()
    import numpy as np
    import torch
    import mlx.core as mx
    if os.environ.get('PYTORCH_ENABLE_MPS_FALLBACK')!='0': raise RuntimeError('Fallback policy missing')
    if not mx.metal.is_available(): raise RuntimeError('Native Metal unavailable')
    mx.set_default_device(mx.gpu)
    native_svd=mx.linalg.svd
    svd_calls=[]
    def counted_svd(x,*args,**kwargs):
        if tuple(x.shape[-2:])!=(3,3) or kwargs.get('stream')!=mx.cpu:
            raise RuntimeError('Unexpected SVD device/shape')
        svd_calls.append(list(x.shape))
        return native_svd(x,*args,**kwargs)
    mx.linalg.svd=counted_svd
    torch.set_num_threads(4)
    source=Path(cfg['sources'][block['arm']]);sys.path.insert(0,str(source))
    from mlx_lm.models import esmc
    from mlx_lm.models import esmfold2
    if Path(esmfold2.__file__).resolve()!=source/'mlx_lm/models/esmfold2.py':
        raise RuntimeError('Wrong model source imported')
    expected='0.31.2' if block['arm']=='old' else '0.32.2'
    if importlib.metadata.version('mlx')!=expected: raise RuntimeError('Unexpected MLX version')
    fp={'float32':mx.float32,'bfloat16':mx.bfloat16}; dtype=fp[block['fold_dtype']]
    assets=Path(cfg['assets']); fold_assets=Path(cfg['fast_assets']) if block['model']=='fast' else assets/'ESMFold2';start=time.perf_counter()
    model=esmfold2.ESMFold2Model(json.loads((fold_assets/'config.json').read_text()))
    weights=esmfold2.sanitize_esmfold2(mx.load(str(fold_assets/'model.safetensors')))
    weights={k:v.astype(dtype) if mx.issubdtype(v.dtype,mx.floating) else v for k,v in weights.items()}
    model.load_weights(list(weights.items()),strict=True);model.set_dtype(dtype);model.eval();mx.eval(model.parameters())
    fold_count=len(weights);del weights
    fold_load=time.perf_counter()-start;start=time.perf_counter()
    encoder=esmc.Model(esmc.ModelArgs.from_dict(json.loads((assets/'ESMC-6B/config.json').read_text())))
    weights={}
    for shard in sorted((assets/'ESMC-6B').glob('*.safetensors')):
        part={k:v.astype(mx.bfloat16) if mx.issubdtype(v.dtype,mx.floating) else v for k,v in mx.load(str(shard)).items()}
        mx.eval(list(part.values()));weights.update(part)
    sanitized=encoder.sanitize(weights)
    encoder.load_weights(list(sanitized.items()),strict=True);encoder.set_dtype(mx.bfloat16);encoder.eval();mx.eval(encoder.parameters())
    model._esmc=encoder
    encoder_count=len(sanitized);del weights,sanitized,part
    loading=dict(fold_seconds=fold_load,esmc_seconds=time.perf_counter()-start,fold_weights=fold_count,esmc_weights=encoder_count,strict=True)
    out=Path(block['output']);out.mkdir(parents=True,exist_ok=True)
    atomic(out/'loaded.json',dict(loading=loading,mlx=expected,torch=torch.__version__,source=str(source),source_sha256=sha(source/'mlx_lm/models/esmfold2.py'),device=str(mx.default_device()),device_info=mx.metal.device_info()))
    with np.load(Path(cfg['output'])/'inputs/features.npz') as z:
        raw={k:z[k].copy() for k in z.files}
    rows=[]
    for i in range(block['warmups']+block['repeats']):
        warmup=i<block['warmups'];name='warmup' if warmup else f'repeat_{i-block["warmups"]+1:02}'
        unit=out/name
        if unit.exists(): raise RuntimeError('Refusing to overwrite a prediction')
        unit.mkdir()
        feats={k:torch.from_numpy(v.copy()) for k,v in raw.items()}
        seed=cfg['protocol']['settings']['seed']
        torch.manual_seed(seed);mx.random.seed(seed)
        svd_before=len(svd_calls)
        mx.synchronize();started=time.perf_counter()
        tensors=model(**feats,num_loops=block['num_loops'],num_sampling_steps=block['num_sampling_steps'],num_diffusion_samples=1,msa_max_depth=1024)
        mx.synchronize();inference=time.perf_counter()-started
        arrays={k:v.detach().cpu().numpy() for k,v in tensors.items() if isinstance(v,torch.Tensor)}
        required={'sample_atom_coords','plddt','ptm','pae'}
        if not required.issubset(arrays): raise RuntimeError('Required outputs absent: '+str(required-arrays.keys()))
        if not all(np.isfinite(v).all() for v in arrays.values() if v.dtype.kind=='f'): raise RuntimeError('Nonfinite output')
        n=len(cfg['protocol']['sequence'])
        if arrays['pae'].shape[-2:]!=(n,n) or arrays['plddt'].size!=n: raise RuntimeError('Confidence shape mismatch')
        for k in ('plddt','ptm'):
            if np.min(arrays[k])<0 or np.max(arrays[k])>1: raise RuntimeError('Confidence outside0..1')
        if np.min(arrays['pae'])<0: raise RuntimeError('Negative PAE')
        np.savez_compressed(unit/'outputs.npz',**arrays)
        row=dict(model=block['model'],num_loops=block['num_loops'],num_sampling_steps=block['num_sampling_steps'],unit=str(unit),warmup=warmup,inference_seconds=inference,ptm=float(arrays['ptm'].mean()),mean_plddt=float(arrays['plddt'].mean()),seed=seed,msa_rows=int(raw['msa'].shape[1]),fold_dtype=block['fold_dtype'],active_memory_bytes=mx.get_active_memory(),peak_memory_bytes=mx.get_peak_memory(),cache_memory_bytes=mx.get_cache_memory(),maxrss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,outputs_sha256=sha(unit/'outputs.npz'),output_shapes={k:list(v.shape) for k,v in arrays.items()})
        row['explicit_cpu_svd_calls']=len(svd_calls)-svd_before
        row['explicit_cpu_svd_shapes']=svd_calls[svd_before:]
        atomic(unit/'measurement.json',row);rows.append(row)
        print(json.dumps(dict(block=block['id'],unit=name,inference_seconds=inference,ptm=row['ptm'],mean_plddt=row['mean_plddt'])),flush=True)
        del tensors,arrays,feats
    atomic(out/'worker_complete.json',dict(rows=rows,loading=loading,process_seconds=time.perf_counter()-process_started))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--config',required=True);ap.add_argument('--block',required=True);a=ap.parse_args()
    cfg=json.loads(Path(a.config).read_text());block=next(b for b in cfg['blocks'] if b['id']==a.block)
    try:main(cfg,block)
    except Exception as e:
        atomic(Path(block['output'])/'failure.json',dict(error=repr(e),traceback=traceback.format_exc()))
        raise
