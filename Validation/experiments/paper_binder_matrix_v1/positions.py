"""Avoid Python RDKit Point3D conversion; retain native crop, augmentation and RNG."""
import ast,inspect,textwrap
def install():
 import numpy as np,torch
 import openfold3.core.data.pipelines.featurization.conformer as conformer
 import openfold3.core.data.framework.single_datasets.inference as inference
 native=conformer.featurize_reference_conformers_of3
 source=textwrap.dedent(inspect.getsource(native))
 assert source.count('conf = mol.GetConformer()')==1
 assert source.count('coords = conf.GetAtomPosition(atom.GetIdx())')==1
 assert source.count('mol_ref_pos = torch.tensor(mol_ref_pos, dtype=torch.float32)')==1
 source=source.replace('conf = mol.GetConformer()','conf = mol.GetConformer()\n        _all_positions = conf.GetPositions()')
 source=source.replace('coords = conf.GetAtomPosition(atom.GetIdx())','coords = _all_positions[atom.GetIdx()]')
 source=source.replace('mol_ref_pos = torch.tensor(mol_ref_pos, dtype=torch.float32)','mol_ref_pos = torch.from_numpy(_np.asarray(mol_ref_pos, dtype=_np.float32))')
 ns=dict(inspect.unwrap(native).__globals__);ns['_np']=np
 exec(compile(ast.parse(source),'<experiment-rdkit-position-array>','exec'),ns)
 optimized=ns['featurize_reference_conformers_of3'];old_inference=inference.featurize_reference_conformers_of3
 conformer.featurize_reference_conformers_of3=optimized;inference.featurize_reference_conformers_of3=optimized
 def undo():conformer.featurize_reference_conformers_of3=native;inference.featurize_reference_conformers_of3=old_inference
 return undo
