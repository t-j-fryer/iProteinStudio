"""Paired raw-fixture and output comparison of the ligand-name-only correction."""
import hashlib,json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[3];out=ROOT/'Validation/output/portable_workflow_launch_v1'
def work(case):
    job=json.loads((out/case/'job.json').read_text())
    return Path(job['output_root'])/'phase0/cycle00/rfd3_initial'
old,new=work('nise-nesso'),work('nise-nesso-fixed')
key='rfd3/fixtures/oracle_nise_initial.npz'
with np.load(old/key) as a,np.load(new/key) as b:
    existing=set(a.files);added=set(b.files)-existing
    assert existing<=set(b.files)
    changed=[k for k in sorted(existing) if not np.array_equal(a[k],b[k],equal_nan=True)]
    assert not changed,changed
    assert added=={'export_atom_names','export_elements'},added
    feature_count=len(existing)
def lines(base):return [s for s in (base/'rfd3/backbones/design_0001.pdb').read_text().splitlines() if s.startswith(('ATOM  ','HETATM'))]
a,b=lines(old),lines(new);assert len(a)==len(b)
coords=lambda lines:np.array([[float(s[i:i+8]) for i in (30,38,46)] for s in lines])
difference=coords(a)-coords(b)
protein_equal=[s for s in a if s.startswith('ATOM')]==[s for s in b if s.startswith('ATOM')]
expected=json.loads((new/'assets/atom_selections.json').read_text())['all_heavy_atoms']
actual=[s[12:16].strip() for s in b if s.startswith('HETATM')]
assert len(actual)==len(set(actual)) and set(actual)==set(expected)
receipt={'unchanged_input_arrays':feature_count,'changed_input_arrays':changed,'added_export_arrays':sorted(added),'atoms':len(a),'max_coordinate_difference_angstrom':float(np.abs(difference).max()),'coordinate_rms_difference_angstrom':float(np.sqrt(np.mean(difference**2))),'protein_pdb_lines_identical':protein_equal,'ligand_unique_names_match_prepared_molecule':True}
(out/'rfd3-export-comparison.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
