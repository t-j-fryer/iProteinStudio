import tempfile,unittest
from pathlib import Path
try:import torch
except ImportError:torch=None
from random_tape import RandomTape
@unittest.skipIf(torch is None,'Torch unavailable in this test runtime')
class Tape(unittest.TestCase):
 def test_global_generator_replay(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'global.npz';torch.manual_seed(42)
   with RandomTape(torch,None,path):a=torch.randn(1,76,3)
   torch.manual_seed(91)
   with RandomTape(torch,None,Path(tmp)/'replay.npz',reference=path):b=torch.randn(1,76,3)
   self.assertTrue(torch.equal(a,b))
 def test_replay_and_restore(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'reference.npz';g=torch.Generator().manual_seed(42);normal=torch.Tensor.normal_
   with RandomTape(torch,g,path):
    a=torch.empty(3,4).normal_(generator=g);b=torch.rand(3,generator=g);c=torch.randn(3,generator=g)
   self.assertIs(torch.Tensor.normal_,normal)
   g.manual_seed(50)
   with RandomTape(torch,g,Path(tmp)/'replay.npz',reference=path):
    x=torch.empty(3,4).normal_(generator=g);y=torch.rand(3,generator=g);z=torch.randn(3,generator=g)
   self.assertTrue(torch.equal(a,x) and torch.equal(b,y) and torch.equal(c,z))
 def test_wrong_shape_restores_functions(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'reference.npz';g=torch.Generator().manual_seed(42);normal=torch.Tensor.normal_
   with RandomTape(torch,g,path):torch.empty(3).normal_(generator=g)
   with self.assertRaises(RuntimeError):
    with RandomTape(torch,g,Path(tmp)/'bad.npz',reference=path):torch.empty(4).normal_(generator=g)
   self.assertIs(torch.Tensor.normal_,normal)
if __name__=='__main__':unittest.main()
