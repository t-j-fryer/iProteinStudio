#!/usr/bin/env python3
"""Apply the pinned Foundry fix for multiple disjoint RASA selections."""

from __future__ import annotations

import argparse
import sysconfig
from pathlib import Path


old = '''                if annotation_name in aa.get_annotation_categories():
                    # ... Set only mask overridden features if exists in atom array
                    aa.get_annotation(annotation_name)[start:end] = np.where(
                        mask, set_value, default_value
                    ).astype(np.int_)
'''
previous = '''                if annotation_name in aa.get_annotation_categories():
                    # Multiple selections may target the same annotation (for
                    # example buried and exposed RASA bins). Preserve values
                    # assigned by earlier, disjoint selections instead of
                    # resetting every non-selected atom to the default.
                    current = aa.get_annotation(annotation_name)[start:end]
                    aa.get_annotation(annotation_name)[start:end] = np.where(
                        mask, set_value, current
                    ).astype(np.int_)
'''
# Only RASA has multiple selection fields writing different values into the
# same annotation. Other selections must retain upstream reset semantics;
# preserving their True defaults fixes unrequested motif atoms as well.
new = previous.replace(
    "                        mask, set_value, current\n",
    '                        mask, set_value, current if annotation_name == "rasa_bin" else default_value\n',
)


def patch_source(text: str) -> str:
    if new in text:
        return text
    for known in (previous, old):
        if known in text:
            return text.replace(known, new, 1)
    raise ValueError("Could not locate the expected pinned Foundry code; inspect the installed version before proceeding.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=(
        Path(sysconfig.get_paths()["purelib"]) / "rfd3/inference/input_parsing.py"
    ), help="Explicit source copy for isolated regression testing (default: installed Foundry)")
    path = parser.parse_args().source
    text = path.read_text()
    try:
        updated = patch_source(text)
    except ValueError as exc:
        raise SystemExit(f"{path}: {exc}") from exc
    if updated != text:
        path.write_text(updated)
    print(f"Foundry RASA-only selection fix verified: {path}")


if __name__ == "__main__":
    main()
