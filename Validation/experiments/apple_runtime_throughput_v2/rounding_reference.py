"""Explicit round-to-nearest-even BF16 for finite numeric oracle operands."""
import numpy as np
def bf16(x):
 a=np.asarray(x,dtype=np.float32);u=a.view(np.uint32)
 return ((u+np.uint32(0x7fff)+((u>>16)&1))&np.uint32(0xffff0000)).view(np.float32).astype(np.float64)
