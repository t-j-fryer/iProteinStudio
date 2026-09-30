import unittest,time,statistics
from types import SimpleNamespace
import numpy as np,torch
from rdkit import Chem
from rdkit.Chem import AllChem
from positions import install
import openfold3.core.data.pipelines.featurization.conformer as conformer
class PositionTest(unittest.TestCase):
 def test_exact_cropped_and_full_features(self):
  mol=Chem.AddHs(Chem.MolFromSmiles('NCC(=O)O'));AllChem.EmbedMolecule(mol,randomSeed=42)
  for i,a in enumerate(mol.GetAtoms()):a.SetBoolProp('annot_used_atom_mask',True);a.SetProp('annot_atom_name',str(i))
  for crop in [np.ones(mol.GetNumAtoms()),np.array([1,1,1,1,1]+[0]*(mol.GetNumAtoms()-5))]:
   data=[SimpleNamespace(mol=mol,in_crop_mask=crop,permutations=np.arange(mol.GetNumAtoms())[None,:])]*100
   times=[]
   for seed in range(3):
    torch.manual_seed(seed);t=time.perf_counter();expected=conformer.featurize_reference_conformers_of3(data);times.append(time.perf_counter()-t)
   undo=install();fast=[]
   try:
    for seed in range(3):
     torch.manual_seed(seed);t=time.perf_counter();observed=conformer.featurize_reference_conformers_of3(data);fast.append(time.perf_counter()-t)
    for k,v in expected.items():
     if isinstance(v,dict):
      for kk,vv in v.items():self.assertTrue(torch.equal(vv,observed[k][kk]),k)
     else:self.assertTrue(torch.equal(v,observed[k]),k)
   finally:undo()
   print('CPU featurizer test seconds',statistics.median(times),statistics.median(fast),'atoms retained',crop.sum())
if __name__=='__main__':unittest.main()
