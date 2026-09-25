"""Loaded only through Studio's job-scoped PYTHONPATH, never installed globally."""
import os
import importlib.machinery
import importlib.util
from pathlib import Path
import sys

# Do not suppress a runtime's own startup policy if one is added in a future
# portable package. Run it first, excluding only this job-scoped bootstrap.
here = Path(__file__).resolve().parent
paths = [p for p in sys.path if Path(p or os.curdir).resolve() != here]
spec = importlib.machinery.PathFinder.find_spec('sitecustomize', paths)
if spec is not None and spec.loader is not None:
    existing = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(existing)

if os.environ.get('IPROTEINSTUDIO_PROGRESS') == '1':
    from engine_progress import install
    install()
