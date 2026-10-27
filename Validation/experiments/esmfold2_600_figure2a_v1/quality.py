"""Fixed crystal masks; homodimer permutations fitted as a single assembly."""
import itertools, json, gzip, math
from pathlib import Path
import numpy as np
from common import sha

def fit(x,y):
    x=np.asarray(x);y=np.asarray(y);u,_,v=np.linalg.svd((y-y.mean(0)).T@(x-x.mean(0)))
    d=np.eye(3);d[-1,-1]=np.linalg.det(u@v);r=u@d@v;t=x.mean(0)-y.mean(0)@r
    return r,t,float(np.sqrt(np.mean(np.sum((y@r+t-x)**2,axis=1))))

def lddt(x,y):
    x=np.asarray(x);y=np.asarray(y);a=np.linalg.norm(x[:,None]-x[None,:],axis=-1);b=np.linalg.norm(y[:,None]-y[None,:],axis=-1)
    mask=(a<15)&(a>0);delta=np.abs(a-b)[mask]
    return float(np.mean([np.mean(delta<v) for v in (.5,1,2,4)]))

def compare(target,ca):
    ref=target['reference_ca'];chains=list(ref);result={};alignments={}
    for label,indices in target['masks'].items():
        x=[ref[c][str(n)] for c in chains for n in indices];options=[]
        for perm in itertools.permutations(chains):
            y=[ca[c][str(n)] for c in perm for n in indices];r,t,rmsd=fit(x,y)
            options.append((rmsd,perm,r,t,y))
        rmsd,perm,r,t,y=min(options,key=lambda v:v[0])
        result[label]=dict(ca_rmsd=rmsd,ca_lddt=lddt(x,y),n_ca=len(x),chain_order=list(perm),rotation=r.tolist(),translation=t.tolist())
        alignments[label]=(r,t)
    if len(chains)==2:
        indices=next(iter(target['masks'].values()));label=next(iter(result));order=result[label]['chain_order']
        ra,rb=[np.array([ref[c][str(n)] for n in indices]) for c in chains]
        pa,pb=[np.array([ca[c][str(n)] for n in indices]) for c in order]
        reference_contacts=np.linalg.norm(ra[:,None]-rb[None,:],axis=-1)<8
        predicted_contacts=np.linalg.norm(pa[:,None]-pb[None,:],axis=-1)<8
        result['interface_ca_contacts_8A']=dict(reference=int(reference_contacts.sum()),predicted=int(predicted_contacts.sum()),
            recall=float((reference_contacts&predicted_contacts).sum()/max(1,reference_contacts.sum())),
            precision=float((reference_contacts&predicted_contacts).sum()/max(1,predicted_contacts.sum())))
    return result

def audit(structure,target):
    from validate_prediction_geometry import inspect_geometry,cif_atom_rows,read_cif
    columns,rows=cif_atom_rows(structure);lookup={n.removeprefix('_atom_site.'):i for i,n in enumerate(columns)}
    def field(row,*names):return next((row[lookup[n]] for n in names if n in lookup and row[lookup[n]] not in ('.','?')),None)
    aa=dict(zip('ALA ARG ASN ASP CYS GLN GLU GLY HIS ILE LEU LYS MET PHE PRO SER THR TRP TYR VAL'.split(),'ARNDCQEGHILKMFPSTWYV'))
    observed={};ca={}
    for row in rows:
        xyz=[float(row[lookup[k]]) for k in ('Cartn_x','Cartn_y','Cartn_z')];assert all(math.isfinite(v) for v in xyz)
        if field(row,'label_atom_id','auth_atom_id')=='CA':
            chain=field(row,'label_asym_id','auth_asym_id');observed.setdefault(chain,[]).append(aa[field(row,'label_comp_id','auth_comp_id')])
            n=str(len(observed[chain]));ca.setdefault(chain,{})[n]=xyz
    expected={c:target['sequence'] for c in 'AB'[:target['copies']]}
    assert {c:''.join(v) for c,v in observed.items()}==expected,('Sequence/cardinality mismatch',observed)
    assert all({'N','CA','C'}.issubset(v) for v in read_cif(structure).values())
    files=[p for p in structure.parent.iterdir() if p.is_file() and any(k in p.name for k in ('confidence','full_data','pae','plddt'))]
    assert files,('Missing confidence',structure)
    keys={'ptm','iptm','plddt','avg_plddt','complex_plddt','pae','pde','token_pair_pae','token_pair_pde','atom_plddts','confidence_score','ipsae_min'};seen={}
    for f in files:
        if f.name.endswith(('.json','.json.gz')):
            data=json.loads(gzip.decompress(f.read_bytes()) if f.suffix=='.gz' else f.read_text())
            for k,v in data.items():
                if k in keys and v is not None:
                    arr=np.asarray(v,dtype=float);assert np.isfinite(arr).all(),(f,k);seen[k]=float(arr.mean())
        elif f.suffix=='.npz':
            with np.load(f,allow_pickle=False) as data:
                for k in data.files:assert np.isfinite(data[k]).all(),(f,k)
    assert 'ptm' in seen and any('plddt' in k for k in seen),(structure,seen)
    geometry=inspect_geometry(structure)
    # Geometry violations are outcomes, not a reason to discard a reduced-budget prediction.
    return dict(geometry=geometry,crystal=compare(target,ca),scores=seen,files={str(p):sha(p) for p in [structure]+files})
