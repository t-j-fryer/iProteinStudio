import unittest
import torch
from openfold_initialization import CheckpointCoverage
class Coverage(unittest.TestCase):
 def test_exact_checkpoint_copy(self):
  m=torch.nn.Linear(3,4);state={k:v.clone()+1 for k,v in m.state_dict().items()};c=CheckpointCoverage(torch);c.skip(m.weight,m)
  with self.assertRaises(RuntimeError):c.guard()
  c.verify_load(m,state,True,torch.nn.Module.load_state_dict);c.guard()
  self.assertTrue(torch.equal(m.weight,state['weight']));self.assertEqual(c.evidence['verified_elements'],12)
 def test_uncovered_and_non_strict_rejected(self):
  m=torch.nn.Linear(3,4);c=CheckpointCoverage(torch);c.skip(m.weight,m)
  with self.assertRaises(RuntimeError):c.verify_load(m,m.state_dict(),False,torch.nn.Module.load_state_dict)
  uncovered=torch.nn.Linear(2,2);c.skip(uncovered.weight,uncovered)
  with self.assertRaises(RuntimeError):c.verify_load(m,m.state_dict(),True,torch.nn.Module.load_state_dict)
 def test_replaced_parameter_and_discarded_constructor(self):
  import gc
  m=torch.nn.Linear(3,4);state={k:v.clone()+1 for k,v in m.state_dict().items()};c=CheckpointCoverage(torch);c.skip(m.weight,m)
  m.weight=torch.nn.Parameter(m.weight.clone())
  temporary=torch.nn.Linear(2,2);c.skip(temporary.weight,temporary);del temporary;gc.collect()
  c.verify_load(m,state,True,torch.nn.Module.load_state_dict);c.guard()
  self.assertEqual(c.evidence['discarded_modules'],1);self.assertTrue(torch.equal(m.weight,state['weight']))
 def test_temporary_object_id_reuse_does_not_lose_events(self):
  import gc
  m=torch.nn.Linear(2,2);state={k:v.clone() for k,v in m.state_dict().items()};c=CheckpointCoverage(torch);c.skip(m.weight,m)
  for _ in range(50):
   temporary=torch.nn.Linear(2,2);c.skip(temporary.weight,temporary);del temporary
  gc.collect();c.verify_load(m,state,True,torch.nn.Module.load_state_dict)
  self.assertEqual(c.evidence['discarded_modules'],50)
  self.assertEqual(c.evidence['skipped_initializers'],c.evidence['verified_initializers']+c.evidence['discarded_modules'])
