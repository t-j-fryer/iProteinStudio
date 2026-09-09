#!/usr/bin/env python3
"""Apply the validated sample-then-mask audit to this declared arm set."""
import importlib.util
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / 'secondary_structure_seed_mask_v1/audit.py'
spec = importlib.util.spec_from_file_location('coil_seed_audit', PATH)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

if __name__ == '__main__':
    audit.main()
