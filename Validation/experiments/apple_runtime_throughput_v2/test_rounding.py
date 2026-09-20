import unittest
import numpy as np
import torch
from rounding_reference import bf16
class Rounding(unittest.TestCase):
 def test_halfway_even_both_signs(self):
  x=np.array([1.00390625,1.01171875,-1.00390625,-1.01171875,0.,-0.],dtype=np.float32)
  np.testing.assert_array_equal(bf16(x),torch.from_numpy(x).bfloat16().float().numpy())
 def test_random_against_independent_cpu_conversion(self):
  x=np.random.default_rng(192).normal(size=10000).astype(np.float32)
  np.testing.assert_array_equal(bf16(x),torch.from_numpy(x).bfloat16().float().numpy())
