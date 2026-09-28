"""Pinned Biohub PyTorch/MPS reference on the benign SUMO monomer and complex fixtures."""
import argparse
import json
import os
from pathlib import Path
import resource
import sys
import time
import traceback
sys.dont_write_bytecode=True
from common import atomic,sha

def main(cfg,block):
    process_start=time.perf_counter()
    import numpy as np
    import torch
    from esm.models.esmfold2.processor import _seed_context,_lm_dropout_context
    from transformers.models.esmc.modeling_esmc import ESMCModel
    from transformers.models.esmfold2.modeling_esmfold2 import ESMFold2Model
    from transformers.models.esmfold2 import modeling_esmfold2_common as common
    if torch.__version__!='2.11.0':raise RuntimeError('Reference Torch revision changed')
    if os.environ.get('PYTORCH_ENABLE_MPS_FALLBACK')!='0' or not torch.backends.mps.is_available():
        raise RuntimeError('Native MPS / no-fallback policy required')
    torch.set_num_threads(4)
    out=Path(block['output']);out.mkdir(parents=True,exist_ok=True)
    assets=Path(cfg['assets']); fold_assets=Path(cfg['fast_assets']) if block['model']=='fast' else assets/'ESMFold2'; loading={}
    models=[]
    for name,cls,asset,dtype,extra in [('esmc',ESMCModel,'ESMC-6B',torch.bfloat16,{'attn_implementation':'sdpa'}),('fold',ESMFold2Model,fold_assets,torch.float32,{'load_esmc':False})]:
        start=time.perf_counter()
        model,info=cls.from_pretrained(assets/asset,dtype=dtype,device_map={'':'mps'},low_cpu_mem_usage=True,local_files_only=True,output_loading_info=True,**extra)
        # The published masked-LM checkpoint also stores the six vocabulary
        # output-head tensors. The pinned reference intentionally loads the
        # feature-only ESMCModel, which has no lm_head and never computes logits.
        expected_unused={f'lm_head.{i}.{kind}' for i in (0,2,3) for kind in ('weight','bias')} if name=='esmc' else set()
        if any(info.get(k) for k in ('missing_keys','mismatched_keys','error_msgs')) or set(info.get('unexpected_keys',[]))!=expected_unused:
            atomic(out/(name+'_loading_error.json'),info);raise RuntimeError('Checkpoint coverage failed')
        atomic(out/(name+'_loading.json'),dict(info=info,expected_unused_checkpoint_keys=sorted(expected_unused),required_model_coverage_pass=True))
        model.eval();torch.mps.synchronize()
        if any(p.device.type!='mps' or (p.is_floating_point() and p.dtype!=dtype) for p in model.parameters()):
            raise RuntimeError('Model dtype/device mismatch')
        loading[name+'_seconds']=time.perf_counter()-start
        loading[name+'_parameter_tensors']=sum(1 for _ in model.parameters());models.append(model)
    encoder,model=models;model.set_kernel_backend(None);model.set_chunk_size(None)
    loading['strict']=True
    atomic(out/'loaded.json',dict(loading=loading,torch=torch.__version__,device='mps',dtype='float32',esmc_dtype='bfloat16',lm_dropout=0.3,msa_column_mask_rate=0.1,source_sha256=sha(Path(sys.modules[ESMFold2Model.__module__].__file__))))
    with np.load(Path(cfg['output'])/'inputs/features.npz') as z: raw={k:z[k].copy() for k in z.files}
    rows=[]
    for i in range(block['warmups']+block['repeats']):
        warmup=i<block['warmups'];unit=out/('warmup' if warmup else f'repeat_{i-block["warmups"]+1:02}')
        if unit.exists():raise RuntimeError('Refusing to overwrite prediction')
        unit.mkdir()
        feats={k:torch.from_numpy(v.copy()).to('mps') for k,v in raw.items()}
        torch.mps.synchronize();before=common.MPS_EXPLICIT_CPU_SVD_CALLS;svd_before=common.MPS_EXPLICIT_CPU_SVD_SECONDS
        start=time.perf_counter()
        with torch.inference_mode(),_seed_context(42):
            hidden=common.compute_lm_hidden_states(encoder,feats['input_ids'],feats['asym_id'],feats['residue_index'],feats['mol_type'],feats['token_attention_mask'],lm_mask_pct=0.0)
        torch.mps.synchronize();encoded=time.perf_counter()
        with torch.inference_mode(),_seed_context(42),_lm_dropout_context(model,0.3):
            tensors=model(**feats,lm_hidden_states=hidden,num_loops=block['num_loops'],num_sampling_steps=block['num_sampling_steps'],num_diffusion_samples=1,lm_mask_pct=0.0,msa_max_depth=1024,msa_column_mask_rate=0.1)
        torch.mps.synchronize();device_done=time.perf_counter()
        arrays={k:(v.detach().float().cpu().numpy() if v.is_floating_point() else v.detach().cpu().numpy()) for k,v in tensors.items() if isinstance(v,torch.Tensor)}
        returned=time.perf_counter()
        required={'sample_atom_coords','plddt','ptm','pae'}
        if not required.issubset(arrays):raise RuntimeError('Required outputs absent')
        if not all(np.isfinite(v).all() for v in arrays.values() if v.dtype.kind=='f'):raise RuntimeError('Nonfinite output')
        n=len(cfg['protocol']['sequence'])
        if arrays['pae'].shape[-2:]!=(n,n) or arrays['plddt'].size!=n:raise RuntimeError('Confidence shape mismatch')
        for k in ('plddt','ptm'):
            if np.min(arrays[k])<0 or np.max(arrays[k])>1:raise RuntimeError('Confidence outside 0..1')
        if np.min(arrays['pae'])<0:raise RuntimeError('Negative PAE')
        np.savez_compressed(unit/'outputs.npz',**arrays)
        row=dict(model=block['model'],num_loops=block['num_loops'],num_sampling_steps=block['num_sampling_steps'],unit=str(unit),warmup=warmup,inference_seconds=returned-start,device_model_seconds=device_done-start,esmc_seconds=encoded-start,fold_seconds=device_done-encoded,return_seconds=returned-device_done,ptm=float(arrays['ptm'].mean()),mean_plddt=float(arrays['plddt'].mean()),seed=42,msa_rows=int(raw['msa'].shape[1]),fold_dtype='float32',active_memory_bytes=torch.mps.current_allocated_memory(),driver_memory_bytes=torch.mps.driver_allocated_memory(),maxrss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,outputs_sha256=sha(unit/'outputs.npz'),output_shapes={k:list(v.shape) for k,v in arrays.items()},explicit_cpu_svd_calls=common.MPS_EXPLICIT_CPU_SVD_CALLS-before,explicit_cpu_svd_seconds=common.MPS_EXPLICIT_CPU_SVD_SECONDS-svd_before)
        atomic(unit/'measurement.json',row);rows.append(row)
        print(json.dumps({k:row[k] for k in ('unit','inference_seconds','esmc_seconds','fold_seconds','ptm','mean_plddt','explicit_cpu_svd_calls')}),flush=True)
        del tensors,arrays,feats,hidden
    atomic(out/'worker_complete.json',dict(rows=rows,loading=loading,process_seconds=time.perf_counter()-process_start))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--config',required=True);ap.add_argument('--block',required=True);a=ap.parse_args()
    cfg=json.loads(Path(a.config).read_text());block=next(b for b in cfg['blocks'] if b['id']==a.block)
    try:main(cfg,block)
    except Exception as e:
        atomic(Path(block['output'])/'failure.json',dict(error=repr(e),traceback=traceback.format_exc()));raise
