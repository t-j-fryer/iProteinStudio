#!/usr/bin/env python3
"""Apply the pinned Foundry fix for multiple disjoint RASA selections."""

from __future__ import annotations

import sysconfig
from pathlib import Path


path = Path(sysconfig.get_paths()["purelib"]) / "rfd3" / "inference" / "input_parsing.py"
old = '''                if annotation_name in aa.get_annotation_categories():
                    # ... Set only mask overridden features if exists in atom array
                    aa.get_annotation(annotation_name)[start:end] = np.where(
                        mask, set_value, default_value
                    ).astype(np.int_)
'''
new = '''                if annotation_name in aa.get_annotation_categories():
                    # Multiple selections may target the same annotation (for
                    # example buried and exposed RASA bins). Preserve values
                    # assigned by earlier, disjoint selections instead of
                    # resetting every non-selected atom to the default.
                    current = aa.get_annotation(annotation_name)[start:end]
                    aa.get_annotation(annotation_name)[start:end] = np.where(
                        mask, set_value, current
                    ).astype(np.int_)
'''
text = path.read_text()
if new in text:
    print(f"Foundry RASA fix already present: {path}")
elif old in text:
    path.write_text(text.replace(old, new, 1))
    print(f"Applied Foundry RASA fix: {path}")
else:
    raise SystemExit(
        f"Could not locate the expected pinned Foundry code in {path}; "
        "inspect the installed version before proceeding."
    )
