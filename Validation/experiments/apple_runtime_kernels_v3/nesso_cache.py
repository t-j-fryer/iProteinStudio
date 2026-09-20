"""Reuse immutable standard-AA CCD parsing; clone molecules for every request."""
from functools import lru_cache
from pathlib import Path
from rdkit import Chem

def install():
 import nesso.data.inference as inference
 original=inference.load_standard_aa_mols
 counters={'disk_loads':0,'requests':0}
 @lru_cache(maxsize=1)
 def cached(path):
  counters['disk_loads']+=1
  return original(Path(path))
 def load(path=None):
  counters['requests']+=1
  if path is None:return original(None)
  # The exact CCD bytes are fixed in the broker plan. Never share mutable molecules.
  return {name:Chem.Mol(mol) if mol is not None else None for name,mol in cached(str(Path(path).resolve())).items()}
 inference.load_standard_aa_mols=load
 return counters
