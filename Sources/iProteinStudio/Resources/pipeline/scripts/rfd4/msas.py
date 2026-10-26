"""Resolve requested automatic MSAs with Studio's existing cache/server policy."""
import json
import os
from pathlib import Path
import sys
from .contract import atomic, seal, verify


def resolve(config):
    cfg=dict(config['settings'])
    if cfg['predictor']=='esmfold2-fast-mlx': return config
    root=Path(os.environ['NANOHUNTER_ROOT']);output=Path(config['output'])
    marker=output/'msa_completed.json'
    if marker.exists():
        saved = dict(verify(marker)); per_chain = saved.pop('target_msas', {})
        return dict(config, settings={**cfg, **saved}, target_msas=per_chain)
    resolved={};files=[];per_chain={}
    if cfg['target_msa']=='auto':
        from .targets import target_sequences
        targets = target_sequences(config)
        if not targets: raise ValueError('Automatic target alignment requires identified target sequences.')
        sys.path.insert(0,str(root/'rfd3_scripts'))
        from predict_batch import resolve_msas, materialize_msas, sequence_key
        jobs=[dict(name='target',chains=[dict(id=c,kind='protein',sequence=seq,msa='auto') for c,seq in targets.items()])]
        policy=dict(msa=dict(cache_dir=str(root/'msa_cache'),index_roots=[str(root/'msa_cache'),str(root/'projects'),str(root/'objects')],allow_server=True))
        found=resolve_msas(jobs,policy,root,dict(os.environ))
        staged=materialize_msas(found,output/'inputs',root/'objects')
        per_chain={c:str(staged[sequence_key(seq)]) for c,seq in targets.items()}
        files.extend(Path(p) for p in set(per_chain.values()))
        if len(per_chain)==1: resolved['target_msa']=next(iter(per_chain.values()))
    if cfg['scaffold_msa']=='auto':
        if not cfg.get('scaffold_id'): raise ValueError('Choose a framework alignment or a known framework.')
        path=root/'examples/nanobody_scaffolds/msas'/cfg['scaffold_id']/'full_msa.a3m'
        if not path.is_file(): raise ValueError('The requested framework alignment is missing.')
        copy=output/'inputs/framework.a3m';copy.parent.mkdir(exist_ok=True,parents=True);copy.write_bytes(path.read_bytes())
        resolved['scaffold_msa']=str(copy);files.append(copy)
    if resolved or per_chain:
        seal(marker,dict(resolved,target_msas=per_chain),files)
    return dict(config,settings={**cfg,**resolved},target_msas=per_chain)
