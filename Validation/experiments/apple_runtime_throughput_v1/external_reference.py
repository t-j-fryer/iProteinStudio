#!/usr/bin/env python3
"""Post-hoc structural context, not a changed benchmark acceptance gate."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request


def main():
    ap=argparse.ArgumentParser();ap.add_argument('output',type=Path);ap.add_argument('--download',action='store_true');a=ap.parse_args()
    out=a.output.resolve();ref=out/'external_reference';ref.mkdir(exist_ok=True)
    cif=ref/'1UBQ.cif';receipt=ref/'source.json';url='https://files.rcsb.org/download/1UBQ.cif'
    if not cif.exists():
        if not a.download:raise SystemExit('Reference absent; explicitly download first')
        data=urllib.request.urlopen(url,timeout=30).read();cif.write_bytes(data)
        receipt.write_text(json.dumps(dict(url=url,sha256=hashlib.sha256(data).hexdigest(),
            pdb_page='https://www.rcsb.org/structure/1UBQ',scope='post-hoc descriptive context; not an independent blind holdout or a new acceptance gate'),indent=2)+'\n')
    if hashlib.sha256(cif.read_bytes()).hexdigest()!=json.loads(receipt.read_text())['sha256']:raise SystemExit('Reference changed')
    import gemmi
    import numpy as np
    st=gemmi.read_structure(str(cif));coords=[];seq=''
    for res in st[0]['A']:
        atom=res.find_atom('CA','*')
        if atom:
            coords.append([atom.pos.x,atom.pos.y,atom.pos.z]);seq+=gemmi.find_tabulated_residue(res.name).one_letter_code
    def rmsd(x,y):
        x=x-x.mean(0);y=y-y.mean(0);u,_,vt=np.linalg.svd(y.T@x);d=np.eye(3);d[-1,-1]=np.linalg.det(u@vt)
        return float(np.sqrt(np.mean(np.sum((x-y@(u@d@vt))**2,axis=1))))
    rows=[]
    for r in json.loads((out/'measurements.json').read_text())['records']:
        if r['name']!='ubiquitin' or r['warmup']:continue
        p=json.loads(Path(r['path']).read_text())
        if p['sequence']!=seq:raise SystemExit('External reference sequence mismatch')
        x=np.array(coords);y=np.array(p['ca'])
        rows.append(dict(run=r['run'],block=r['block'],torch=r['torch'],seed=r['seed'],threads=r['threads'],
                         n=len(x),rmsd_all_angstrom=rmsd(x,y),rmsd_residues_1_72_angstrom=rmsd(x[:72],y[:72])))
    (ref/'comparison.json').write_text(json.dumps(dict(note='All76 residues plus separately reported1–72; terminal four residues are mobile in the crystal. No results removed from original gate.',rows=rows),indent=2)+'\n')
    print(json.dumps(rows,indent=2))


if __name__=='__main__':main()
