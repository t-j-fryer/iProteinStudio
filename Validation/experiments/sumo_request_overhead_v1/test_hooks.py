"""CPU-only regression for combined loader/RNG and teardown hook lifetimes."""
from pathlib import Path
from types import SimpleNamespace
import tempfile,unittest
import torch,numpy as np,random
from optimizations import ExperimentHooks
from pytorch_lightning.strategies.strategy import Strategy
from openfold3.core.data.framework.single_datasets.inference import InferenceDataset

class HooksTest(unittest.TestCase):
 def test_array_conversion_preserves_native_features_and_augmentation(self):
  from rdkit import Chem
  from rdkit.Chem import AllChem
  import openfold3.core.data.pipelines.featurization.conformer as conformer
  mol=Chem.AddHs(Chem.MolFromSmiles('NCC(=O)O'));AllChem.EmbedMolecule(mol,randomSeed=42)
  for i,atom in enumerate(mol.GetAtoms()):atom.SetBoolProp('annot_used_atom_mask',True);atom.SetProp('annot_atom_name',str(i))
  processed=[SimpleNamespace(mol=mol,in_crop_mask=np.ones(mol.GetNumAtoms()),permutations=np.arange(mol.GetNumAtoms())[None,:])]
  torch.manual_seed(123);expected=conformer.featurize_reference_conformers_of3(processed)
  with tempfile.TemporaryDirectory() as tmp:
   hooks=ExperimentHooks('openfold3','w0_keep_arrays',SimpleNamespace(data_module_args=SimpleNamespace(num_workers=10,data_seed=42)),torch.nn.Linear(2,2),SimpleNamespace(wrap=lambda *a,**k:None,rows={}),Path(tmp))
   try:
    torch.manual_seed(123);observed=conformer.featurize_reference_conformers_of3(processed)
    for k,v in expected.items():
     if isinstance(v,dict):
      for key,value in v.items():self.assertTrue(torch.equal(value,observed[k][key]),k)
     else:self.assertTrue(torch.equal(v,observed[k]),k)
   finally:
    for obj,name,old in reversed(hooks.undo):setattr(obj,name,old)

 def test_feature_cache_copies_storage_and_keys_sequence_and_msa_contents(self):
  import copy
  original=InferenceDataset.create_all_features;calls=[]
  def build(dataset,query):calls.append(query.sequence);return {'feature':torch.tensor([1.,2.])}
  InferenceDataset.create_all_features=build
  class Query:
   sequence='AAAA';query_name='first'
   chains=[SimpleNamespace(molecule_type=SimpleNamespace(name='PROTEIN'))]
   def model_dump(self,mode):return {'query_name':self.query_name,'chains':[{'sequence':self.sequence,'main_msa_file_paths':[str(msa)]}]}
  try:
   with tempfile.TemporaryDirectory() as tmp:
    msa=Path(tmp)/'colabfold_main.a3m';msa.write_text('>query\nAAAA\n')
    hooks=ExperimentHooks('openfold3','w0_keep_features_keyed',SimpleNamespace(data_module_args=SimpleNamespace(num_workers=10,data_seed=42)),torch.nn.Linear(2,2),SimpleNamespace(wrap=lambda *a,**k:None,rows={}),Path(tmp))
    try:
     query=Query();a=InferenceDataset.create_all_features(None,query);a['feature'][0]=999
     query.query_name='second'
     b=InferenceDataset.create_all_features(None,query);self.assertEqual(b['feature'][0].item(),1);self.assertEqual(len(calls),1)
     msa.write_text('>query\nAAAA\n>homolog\nAAAG\n');InferenceDataset.create_all_features(None,query);self.assertEqual(len(calls),2)
     query.sequence='AAAG';InferenceDataset.create_all_features(None,query);self.assertEqual(len(calls),3)
    finally:
     for obj,name,old in reversed(hooks.undo):setattr(obj,name,old)
  finally:InferenceDataset.create_all_features=original

 def test_combined_hooks_keep_distinct_originals_and_restore(self):
  class Model(torch.nn.Linear):
   calls=0
   def cpu(self):self.calls+=1;return super().cpu()
  model=Model(2,2);session=SimpleNamespace(data_module_args=SimpleNamespace(num_workers=10,data_seed=42))
  profiler=SimpleNamespace(wrap=lambda *a,**k:None,rows={})
  original=InferenceDataset.__getitem__
  InferenceDataset.__getitem__=lambda dataset,index:(index,random.random(),np.random.random(),torch.rand(1).item())
  try:
   with tempfile.TemporaryDirectory() as tmp:
    hooks=ExperimentHooks('openfold3','w0_keep',session,model,profiler,Path(tmp))
    try:
     random.seed(7);np.random.seed(7);torch.manual_seed(7)
     pr=random.getstate();nr=np.random.get_state();tr=torch.get_rng_state()
     a=InferenceDataset.__getitem__(None,3);b=InferenceDataset.__getitem__(None,3)
     self.assertEqual(a,b);self.assertEqual(random.getstate(),pr);self.assertTrue(np.array_equal(np.random.get_state()[1],nr[1]));self.assertTrue(torch.equal(torch.get_rng_state(),tr))
     noop=SimpleNamespace(teardown=lambda:None)
     strategy=SimpleNamespace(lightning_module=model,optimizers=[],precision_plugin=noop,accelerator=noop,checkpoint_io=noop)
     Strategy.teardown(strategy);self.assertEqual(model.calls,0)
     self.assertNotIn('cpu',model.__dict__);model.cpu();self.assertEqual(model.calls,1)
    finally:
     for obj,name,old in reversed(hooks.undo):setattr(obj,name,old)
  finally:InferenceDataset.__getitem__=original

if __name__=='__main__':unittest.main()
