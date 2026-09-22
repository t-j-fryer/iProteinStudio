"""Experimental PSICHIC-XL scoring contract; no structural-confidence surrogate."""
import hashlib,json,math,re
from pathlib import Path

RANKING_POLICY=dict(version='psichic-xl-binding-proxy-v1',formula='1 - predicted_nonbinder',order='descending',experimental=True)
PROTOCOL='psichic-xl-esm-mps-batch8-cpu-graph16-fp32-v1'
SCALARS=('predicted_binding_affinity','predicted_antagonist','predicted_nonbinder','predicted_agonist')

def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(8<<20),b''):h.update(b)
    return h.hexdigest()

def installation(root):
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
    from engine_registry import pinned_installation
    return pinned_installation(root,'psichic',Path(root)/'components/psichic/current')
def asset_root(root):
    version=hashlib.sha256(Path(__file__).with_name('psichic_assets.json').read_bytes()).hexdigest()[:20]
    import os
    if json.loads(os.environ.get('IPROTEINSTUDIO_RUNTIME_BINDINGS','{}')).get('psichic'):root=os.environ.get('NANOHUNTER_ROOT',root)
    return Path(root)/'models/psichic'/version
def protocol():return json.loads(Path(__file__).with_name('psichic_assets.json').read_text())

def validate_sequence(sequence):
    if not isinstance(sequence,str) or not re.fullmatch('[ACDEFGHIKLMNPQRSTVWY]{1,700}',sequence):
        raise ValueError('Experimental PSICHIC supports complete protein sequences of 1–700 residues; masked and longer inputs are not supported.')

def validate_scores(values):
    result={}
    for k in SCALARS:
        v=values.get(k)
        if type(v) not in (int,float) or not math.isfinite(v):raise ValueError('Invalid PSICHIC output: '+k)
        result[k]=float(v)
    probabilities=[result[k] for k in SCALARS[1:]]
    if any(not 0<=v<=1 for v in probabilities) or abs(sum(probabilities)-1)>1e-6:raise ValueError('Invalid PSICHIC class probabilities')
    result['binding_probability_proxy']=1-result['predicted_nonbinder']
    return result

def placement_score(values):
    v=validate_scores(values)
    return dict(eligible=True,rejection_reason=None,score=v['binding_probability_proxy'])

def installation_files(root):
    base=installation(root);manifest=base/'runtime.json'
    if not manifest.is_file():return [manifest]
    record=json.loads(manifest.read_text())
    return [manifest]+[base/p for p,v in record['files'].items() if 'sha256' in v]+[asset_root(root)/p for p in protocol()['assets']]

def validate_installation(root,full=True):
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
    from runtime_package import verify
    base=installation(root)
    if not (base/'runtime.json').is_file():raise ValueError('Install experimental PSICHIC from Engines before selecting it.')
    record=verify(base,engine='psichic',full=full)
    for name,entry in protocol()['assets'].items():
        path=asset_root(root)/name
        if not path.is_file() or path.stat().st_size!=entry['size'] or (full and sha256(path)!=entry['sha256']):raise ValueError('Missing or changed PSICHIC model asset: '+name)
    if not (base/'python/bin/python3').is_file():raise ValueError('Missing portable PSICHIC Python')
    return record
