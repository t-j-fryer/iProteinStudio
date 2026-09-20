import copy,json,unittest
from pathlib import Path
import numpy as np
from analyse import compare
LIMITS=json.loads(Path(__file__).with_name('manifest.json').read_text())['acceptance']
class NumericalGates(unittest.TestCase):
 def sumo_fixture(self):
  a=self.fixture();a.update(ca=np.random.default_rng(4).normal(size=(50,3)),ca_plddt=np.array([40.]*20+[95.]*30),ids=list(range(50)),matrices={'pae':np.ones((50,50))})
  a['measurement'].update(name='sumo',sequence='A'*50);return a
 def test_sumo_tail_does_not_control_core_alignment(self):
  a=self.sumo_fixture();b=copy.deepcopy(a);b['ca'][:6]+=100
  r=compare(a,b,'intellifold-full',LIMITS)
  self.assertTrue(r['passed']);self.assertGreater(r['metrics']['whole_ca_rmsd'],1);self.assertLess(r['metrics']['ca_rmsd'],1e-10)
 def test_candidate_cannot_hide_core_error_with_low_confidence(self):
  a=self.sumo_fixture();b=copy.deepcopy(a);b['ca'][28]+=20;b['ca_plddt'][28]=10
  r=compare(a,b,'intellifold-full',LIMITS)
  self.assertFalse(r['passed']);self.assertIn(29,r['metrics']['sumo_core_indices_1based'])
 def test_overconfident_tail_still_excluded(self):
  a=self.sumo_fixture();a['ca_plddt'][:20]=99;b=copy.deepcopy(a);b['ca'][:20]+=100
  r=compare(a,b,'constraint',LIMITS)
  self.assertTrue(r['passed']);self.assertTrue(all(i>20 for i in r['metrics']['sumo_core_indices_1based']))
 def test_rfd3_length_fixture_is_not_sumo_structure(self):
  a=self.sumo_fixture();a['sequence_indices']=np.zeros(50);b=copy.deepcopy(a);b['ca'][:6]+=100
  r=compare(a,b,'rfd3',LIMITS)
  self.assertFalse(r['passed']);self.assertNotIn('sumo_core_residues',r['metrics'])
 def test_missing_core_is_unassessable_not_whole_chain_fallback(self):
  a=self.sumo_fixture();a['ca_plddt'][:]=60;b=copy.deepcopy(a)
  r=compare(a,b,'protenix',LIMITS)
  self.assertFalse(r['passed']);self.assertIn('insufficient high-confidence SUMO core',r['failures'])
  self.assertNotIn('ca_rmsd',r['metrics']);self.assertIn('whole_ca_rmsd',r['metrics'])
 def fixture(self):
  return dict(measurement=dict(name='fixture',sequence='AAAAA',seed=42,warmup=False,seconds=1),ca=np.random.default_rng(3).normal(size=(5,3)),ids=list(range(5)),breaks=set(),matrices={'pae':np.ones((5,5))},confidence={'plddt':.8,'ptm':.7})
 def test_rigid_transform_not_error(self):
  a=self.fixture();b=copy.deepcopy(a);b['ca']=a['ca']@np.array([[0,-1,0],[1,0,0],[0,0,1]])+10
  self.assertTrue(compare(a,b,'intellifold-flash',LIMITS)['passed'])
 def test_local_distortion_rejected(self):
  a=self.fixture();b=copy.deepcopy(a);b['ca'][0]+=20
  self.assertFalse(compare(a,b,'intellifold-flash',LIMITS)['passed'])
 def test_error_matrix_drift_rejected(self):
  a=self.fixture();b=copy.deepcopy(a);b['matrices']['pae']+=3
  self.assertIn('pae_mae',compare(a,b,'intellifold-flash',LIMITS)['failures'])
 def test_new_backbone_break_rejected(self):
  a=self.fixture();b=copy.deepcopy(a);b['breaks'].add('new')
  self.assertIn('new backbone breaks',compare(a,b,'intellifold-flash',LIMITS)['failures'])
 def test_unpaired_seed_rejected(self):
  a=self.fixture();b=copy.deepcopy(a);b['measurement']['seed']=43
  with self.assertRaises(AssertionError):compare(a,b,'intellifold-flash',LIMITS)
 def test_atom_mismatch_rejected(self):
  a=self.fixture();b=copy.deepcopy(a);b['ids'][1]='wrong'
  with self.assertRaises(AssertionError):compare(a,b,'intellifold-flash',LIMITS)
if __name__=='__main__':unittest.main()
