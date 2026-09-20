"""Sequence-verified reference comparisons; independent fixed reference cores."""
import csv,json,sys,hashlib
from pathlib import Path
import numpy as np
import gemmi
REPO=Path(__file__).resolve().parents[3]
V2=REPO/'Validation/output/apple_runtime_throughput_v2'
OUT=REPO/'Validation/output/apple_runtime_release_v4'
sys.path.insert(0,str(REPO/'Validation/experiments/apple_runtime_throughput_v2'))
from analyse import extract,aligned
from coordinator import verify_complete

def reference(name,seq):
    code,chain=('1UBQ','A') if name=='ubiquitin' else ('3QHT','A')
    path=OUT/'references'/f'{code}.cif';block=gemmi.cif.read_file(str(path)).sole_block()
    polymers={r[0]:gemmi.cif.as_string(r[1]).replace('\n','').replace(' ','') for r in block.find('_entity_poly.',['entity_id','pdbx_seq_one_letter_code_can'])}
    coords={};identity={};entity=None
    for row in block.find('_atom_site.',['auth_asym_id','label_entity_id','label_seq_id','label_atom_id','label_comp_id','Cartn_x','Cartn_y','Cartn_z','label_alt_id']):
        if row[0]!=chain or row[3]!='CA' or row[8] not in ('.','A'):continue
        entity=row[1];i=int(row[2])-1;coords[i]=[float(x) for x in list(row)[5:8]];identity[i]=gemmi.find_tabulated_residue(row[4]).one_letter_code
    full=polymers[entity];offset=full.find(seq)
    if offset<0 or full.find(seq,offset+1)>=0:raise RuntimeError('Reference lacks unique exact full query sequence')
    mapped={i-offset:xyz for i,xyz in coords.items() if offset<=i<offset+len(seq)}
    assert all(identity[i+offset]==seq[i] for i in mapped)
    core=[i for i in sorted(mapped) if (i<72 if name=='ubiquitin' else i>=20)]
    return mapped,core,dict(pdb=code,chain=chain,query_offset=offset,query_identity=1.,observed=len(mapped),core_indices_1based=[i+1 for i in core],sha256=hashlib.sha256(path.read_bytes()).hexdigest(),url=f'https://www.rcsb.org/structure/{code}')

def lddt(x,y):
    d=np.linalg.norm(x[:,None]-x[None,:],axis=-1);e=np.linalg.norm(y[:,None]-y[None,:],axis=-1)
    mask=(d<15)&(~np.eye(len(d),dtype=bool));delta=np.abs(d[mask]-e[mask])
    return float(np.mean([np.mean(delta<t) for t in (.5,1,2,4)]))

def main():
    rows=[];refs={}
    prefixes=['boltz','intellifold-flash_smoke','intellifold-flash_repeat','intellifold-flash_tape','intellifold-full_smoke','protenix_smoke','protenix_tape','constraint_smoke','constraint_tape','openfold_smoke','openfold_init']
    for run in sorted(V2.glob('*_20*')):
        if not any(run.name.startswith(x) for x in prefixes) or not (run/'completed.json').exists():continue
        cfg=json.loads((run/'frozen/run.json').read_text());engine=cfg['blocks'][0]['engine']
        for arm,p in json.loads((run/'progress.json').read_text()).items():
            p=Path(p);verify_complete(p,p.parent/(p.name+'.request.json'))
            for item in json.loads((p/'result.json').read_text())['rows']:
                unit=Path(item).parent;d=extract(unit,engine);m=d['measurement']
                if m['warmup']:continue
                ref,core,receipt=reference(m['name'],m['sequence']);refs[m['name']]=receipt
                indices=sorted(ref);x=np.array([ref[i] for i in indices]);y=d['ca'][indices]
                cx=np.array([ref[i] for i in core]);cy=d['ca'][core]
                rows.append(dict(run=run.name,engine=engine,arm=arm,torch=m['torch'],input=m['name'],seed=m['seed'],msa='explicit empty',observed_residues=len(indices),core_residues=len(core),observed_ca_rmsd=aligned(x,y)[0],core_ca_rmsd=aligned(cx,cy)[0],core_ca_lddt=lddt(cx,cy),core_plddt=float(np.mean(d['ca_plddt'][core])),ca_breaks=int(np.sum((np.linalg.norm(np.diff(d['ca'],axis=0),axis=1)<2.8)|(np.linalg.norm(np.diff(d['ca'],axis=0),axis=1)>4.5))),structure_unit=str(unit)))
    (OUT/'crystal_comparison.json').write_text(json.dumps(dict(references=refs,rows=rows),indent=2)+'\n')
    with (OUT/'crystal_comparison.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    lines=['# Experimental-reference comparison','', 'Original outputs were explicitly single-sequence in both arms. References were selected by exact full query sequence containment, not by the resulting RMSD. 1UBQ chainA contains all76 ubiquitin residues; 3QHT chainA contains the exact96-residue yeast Smt3 query with construct terminal extensions. Only resolved, identity-matched CA atoms are scored. Fixed cores: ubiquitin1–72; Smt3 query21 onward, intersected with observed crystal residues. No predicted-confidence mask; poor predictions remain assessable. Crystals are training-era contextual references, not blind holdouts. 3QHT is a bound complex; context may affect conformation.','', '| Run | Arm | Input | Core n | Core CA RMSD (Å) | Core CA lDDT | Mean core pLDDT | CA breaks |','|---|---|---|---:|---:|---:|---:|---:|']
    for r in rows:lines.append(f"| {r['run']} | {r['arm']} | {r['input']} | {r['core_residues']} | {r['core_ca_rmsd']:.3f} | {r['core_ca_lddt']:.3f} | {r['core_plddt']:.1f} | {r['ca_breaks']} |")
    lines+=['','[1UBQ](https://www.rcsb.org/structure/1UBQ), [3QHT](https://www.rcsb.org/structure/3QHT). All-resolved RMSD and immutable source paths are retained in the CSV/JSON. This is a post-hoc external-reference diagnostic; original equivalence gates are not rewritten.']
    (OUT/'CRYSTAL_REPORT.md').write_text('\n'.join(lines)+'\n')
    for r in rows:print(r['run'].split('_20')[0],r['arm'],r['input'],round(r['core_ca_rmsd'],3),round(r['core_ca_lddt'],3),round(r['core_plddt'],1),r['ca_breaks'])
if __name__=='__main__':main()
