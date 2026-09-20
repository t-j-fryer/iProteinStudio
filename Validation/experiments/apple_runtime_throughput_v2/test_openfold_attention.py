import unittest
import torch
from openfold_attention import oracle,sdpa

class AttentionTests(unittest.TestCase):
 def test_independent_cpu_oracle(self):
  rows=oracle(torch,'cpu');self.assertEqual(len(rows),2)
  self.assertTrue(all(r['relative_l2']<=1e-5 for r in rows))
 def test_reject_unvalidated_precision(self):
  q=torch.ones((1,2,3,4),dtype=torch.float16)
  with self.assertRaises(RuntimeError):sdpa(torch,q,q,q,[])
 def test_reject_unsupported_value_width(self):
  q=torch.ones((1,2,3,4));v=torch.ones((1,2,3,2))
  with self.assertRaises(RuntimeError):sdpa(torch,q,q,v,[])

if __name__=='__main__':unittest.main()
