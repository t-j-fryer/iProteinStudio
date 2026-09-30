"""Meaningful tests for crystal-coordinate accuracy independent of prediction."""
import sys,unittest
from pathlib import Path
import numpy as np
from quality import align
class CrystalAlignment(unittest.TestCase):
 def test_rigid_transform_is_removed(self):
  rng=np.random.default_rng(3);x=rng.normal(size=(76,3));q,_=np.linalg.qr(rng.normal(size=(3,3)))
  if np.linalg.det(q)<0:q[:,-1]*=-1
  self.assertLess(align(x,x@q+np.array([50,20,-30])),1e-12)
 def test_distortion_is_not_removed(self):
  x=np.random.default_rng(2).normal(size=(76,3));y=x.copy();y[:10,0]+=4
  self.assertGreater(align(x,y),1)
 def test_mobile_tail_does_not_change_core(self):
  x=np.random.default_rng(1).normal(size=(96,3));y=x.copy();y[:20]+=100
  self.assertLess(align(x[20:],y[20:]),1e-12)
  self.assertGreater(align(x,y),10)
if __name__=='__main__':unittest.main()
