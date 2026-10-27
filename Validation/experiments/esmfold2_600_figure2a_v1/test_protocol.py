import json,os,unittest
import numpy as np
from quality import compare,fit
from memory import tree_memory
from host_load import classify,acceptable,audit
class Protocol(unittest.TestCase):
 def test_rigid_fit_and_assembly_permutation(self):
  a=np.random.default_rng(5).normal(size=(10,3));b=a+[8,0,0]
  target=dict(reference_ca={c:{str(i+1):v.tolist() for i,v in enumerate(x)} for c,x in [('A',a),('B',b)]},masks={'assembly':list(range(1,11))})
  swapped={'A':target['reference_ca']['B'],'B':target['reference_ca']['A']}
  self.assertLess(compare(target,swapped)['assembly']['ca_rmsd'],1e-8)
  wrong={c:{n:(np.array(v)+(0 if c=='A' else 20)).tolist() for n,v in xyz.items()} for c,xyz in target['reference_ca'].items()}
  self.assertGreater(compare(target,wrong)['assembly']['ca_rmsd'],5)
 def test_host_ownership_and_compiler_gate(self):
  rows=[dict(pid=1,ppid=0,cpu=0,executable='python'),dict(pid=2,ppid=1,cpu=300,executable='python'),dict(pid=3,ppid=0,cpu=5,executable='swiftc')]
  s=classify(rows,1);self.assertEqual(s['external_cpu_percent'],5);self.assertFalse(acceptable(s));self.assertFalse(audit([s])['timing_qualified'])
 def test_darwin_sampling(self):self.assertGreater(tree_memory(os.getpid())['tree_footprint_bytes'],0)
if __name__=='__main__':unittest.main()
