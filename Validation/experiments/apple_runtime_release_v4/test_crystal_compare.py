import unittest
import numpy as np
from crystal_compare import reference,aligned,lddt
class ReferenceChecks(unittest.TestCase):
 def test_identity_and_rigid_transform(self):
  seq='MQIFVKTLTGKTITLEVEPSDTIENVKAKIQDKEGIPPDQQRLIFAGKQLEDGRTLSDYNIQKESTLHLVLRLRGG'
  mapped,core,r=reference('ubiquitin',seq);x=np.array([mapped[i] for i in core]);rot=np.array([[0.,-1,0],[1,0,0],[0,0,1]])
  self.assertEqual(len(core),72);self.assertEqual(r['query_identity'],1)
  self.assertLess(aligned(x,x@rot+np.array([3,4,5]))[0],1e-10)
  self.assertEqual(lddt(x,x@rot+np.array([3,4,5])),1)
 def test_wrong_reference_sequence_rejected(self):
  with self.assertRaises(RuntimeError):reference('ubiquitin','A'*76)
 def test_sumo_construct_matches_and_tail_mask_is_fixed(self):
  seq='SDSEVNQEAKPEVKPEVKPETHINLKVSDGSSEIFFKIKKTTPLRRLMEAFAKRQGKEMDSLRFLYDGIRIQADQTPEDLDMEDNDIIEAHREQIG'
  _,core,r=reference('sumo',seq);self.assertEqual(r['query_offset'],1)
  self.assertTrue(all(i>=20 for i in core));self.assertEqual(len(core),76)
if __name__=='__main__':unittest.main()
