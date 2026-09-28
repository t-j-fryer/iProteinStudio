"""Reference CPU preparation and decoding for explicitly sequence-only fixtures."""
import argparse
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
import numpy as np
from common import atomic, sha, pdb_audit, align

def make_input(cfg):
    from esm.models.esmfold2 import ESMFold2InputBuilder, ProteinInput, StructurePredictionInput
    builder = ESMFold2InputBuilder(ccd_cache=Path(cfg['assets'])/'ESMFold2')
    spi = StructurePredictionInput(sequences=[ProteinInput(id=k, sequence=v, msa=None) for k,v in cfg['protocol']['chains'].items()])
    return builder, spi

def prepare(cfg):
    import torch
    out = Path(cfg['output']); builder, spi = make_input(cfg)
    feats, _ = builder.prepare_input(spi, seed=42, device='cpu')
    if feats['msa'].shape[1] != 1 or torch.count_nonzero(feats['deletion_mean']):
        raise RuntimeError('Unexpected non-query MSA features')
    np.savez_compressed(out/'inputs/features.npz', **{k:v.numpy() for k,v in feats.items() if isinstance(v,torch.Tensor)})
    atomic(out/'inputs/features.json', dict(sha256=sha(out/'inputs/features.npz'), model_msa_shape=list(feats['msa'].shape), policy=cfg['protocol']['msa_policy'], homolog_msa_used=False))
    print('Prepared sequence-only '+cfg['context'], flush=True)

def decode(cfg, unit):
    import torch
    out=Path(cfg['output']); unit=Path(unit); builder,spi=make_input(cfg)
    _,chains=builder.prepare_input(spi,seed=42,device='cpu')
    with np.load(out/'inputs/features.npz') as z: feats={k:torch.from_numpy(z[k].copy()) for k in z.files}
    with np.load(unit/'outputs.npz') as z: tensors={k:torch.from_numpy(z[k].copy()) for k in z.files}
    result=builder.decode(tensors,feats,chains,num_diffusion_samples=1)
    text=result.complex.to_protein_complex().to_pdb_string(); (unit/'structure.pdb').write_text(text)
    expected=cfg['protocol']['chains']
    if {l[21] for l in text.splitlines() if l.startswith('ATOM  ')} != set(expected):
        raise RuntimeError('Wrong chain IDs/count')
    audit={}
    for chain,seq in expected.items():
        path=unit/f'chain_{chain}.pdb'
        path.write_text('\n'.join(l for l in text.splitlines() if l.startswith('ATOM  ') and l[21]==chain)+'\n')
        audit[chain]=pdb_audit(path,seq)
    confidence={k:float(tensors[k].float().mean()) for k in ('ptm','plddt')}
    extra={}
    if cfg['context']=='complex':
        for k in ('iptm','pair_chains_iptm'):
            v=tensors[k].float().numpy()
            if not np.isfinite(v).all() or v.min()<0 or v.max()>1:raise RuntimeError('Invalid '+k)
        confidence['iptm']=float(tensors['iptm'].float().mean())
        confidence['pair_chains_iptm']=tensors['pair_chains_iptm'].float().tolist()
        caa=np.array(audit['A']['ca']);cab=np.array(audit['B']['ca'])
        distances=np.linalg.norm(caa[:,None]-cab[None,:],axis=-1)
        extra['interchain_ca_contacts_8A']=np.argwhere(distances<8).tolist()
        extra['minimum_interchain_ca_distance']=float(distances.min())
    else:
        ref=json.loads((out/'inputs/reference.json').read_text())
        extra['core_ca_rmsd_to_3QHT']=align(ref['core_ca'],np.array(audit['A']['ca'])[ref['core_indices']])
    atomic(unit/'audit.json',dict(passed=True,chains=audit,confidence=confidence,structural_flags={k:v['ca_breaks'] for k,v in audit.items() if v['ca_breaks']},structure_sha256=sha(unit/'structure.pdb'),**extra))
    print(json.dumps(dict(unit=str(unit),confidence=confidence,**{k:v for k,v in extra.items() if not isinstance(v,list)})),flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['prepare','decode']);ap.add_argument('config');ap.add_argument('--unit');a=ap.parse_args()
    cfg=json.loads(Path(a.config).read_text());prepare(cfg) if a.mode=='prepare' else decode(cfg,a.unit)
