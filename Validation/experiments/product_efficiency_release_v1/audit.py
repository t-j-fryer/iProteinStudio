"""Audit saved paired results without changing their exact-comparison record.

PDB serialization has 0.001-Angstrom coordinate precision. We separately report
exact identity and numerical equivalence; neither is experimental validation.
"""
import json
import math
from pathlib import Path
import sys


def audit(root):
    root=Path(root);raw=json.loads((root/'summary.json').read_text())
    left=raw['arms']['fresh_serial']['rows'];right=raw['arms']['resident_overlap']['rows']
    assert len(left)==len(right)==8
    rows=[]
    for a,b in zip(left,right):
        name=a['name'];cycle=name.split('_')[0]
        atoms=[]
        for arm in ('fresh_serial','resident_overlap'):
            pdb=root/arm/cycle/'fold'/name/'out/boltz_results_yaml/predictions'/name/(name+'_model_0.pdb')
            atoms.append([line for line in pdb.read_text().splitlines() if line.startswith(('ATOM  ','HETATM'))])
        assert len(atoms[0])==len(atoms[1])>0
        assert all(x[:30]==y[:30] for x,y in zip(*atoms)), 'Atom identity mismatch'
        distances=[math.dist([float(x[k:k+8]) for k in (30,38,46)],
                            [float(y[k:k+8]) for k in (30,38,46)]) for x,y in zip(*atoms)]
        rms=math.sqrt(sum(x*x for x in distances)/len(distances))
        row=dict(name=name, same_sequence=a['sequence']==b['sequence'], same_pbind=a['pbind']==b['pbind'],
                 same_geometry=a['geometry_pass']==b['geometry_pass'],
                 same_early_gate=(a['score']>=.8)==(b['score']>=.8),
                 rms_displacement_angstrom=rms,max_displacement_angstrom=max(distances),
                 ligand_plddt_delta=abs(a['ligand_plddt']-b['ligand_plddt']),score_delta=abs(a['score']-b['score']))
        row['passed']=all(row[k] for k in ('same_sequence','same_pbind','same_geometry','same_early_gate')) and (
            math.isfinite(rms) and rms<=.005 and max(distances)<=.05 and row['score_delta']<=.001)
        rows.append(row)
    ranks_equal=all([x['name'] for x in sorted((r for r in left if r['name'].startswith(c)),key=lambda r:-r['score'])]==
                    [x['name'] for x in sorted((r for r in right if r['name'].startswith(c)),key=lambda r:-r['score'])]
                    for c in ('c0_','c1_'))
    result=dict(passed=all(x['passed'] for x in rows) and ranks_equal,exact_comparison_passed=raw['passed'],
                interpretation='Numerical equivalence, not bitwise identity; tolerance audit added after exact-check failure.',
                criteria=dict(max_rms_angstrom=.005,max_atom_displacement_angstrom=.05,max_score_delta=.001),
                ranks_equal=ranks_equal,rows=rows)
    destination=root/'analysis';destination.mkdir(exist_ok=True)
    (destination/'numerical_audit.json').write_text(json.dumps(result,indent=2)+'\n')
    assert result['passed'], 'Numerical or decision equivalence failed'
    print(json.dumps(result,indent=2))


if __name__=='__main__':audit(sys.argv[1])
