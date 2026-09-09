"""Monomer initialization assessment. This module neither samples nor schedules.

Eligibility means only that the explicitly supplied exploratory criterion passed.
P-SEA coil and prediction uncertainty do not establish intrinsic disorder.
"""
from __future__ import annotations

import math
from pathlib import Path


def validate_policy(policy):
    if set(policy) != {"max_attempts", "min_uncertain_coil_length", "confidence_threshold"}:
        raise ValueError("Provide an attempt budget, uncertain-coil length and confidence threshold")
    for key in ("max_attempts", "min_uncertain_coil_length"):
        if type(policy[key]) is not int or not 1 <= policy[key] <= 1000:
            raise ValueError(f"{key} must be an integer between 1 and 1000")
    threshold = policy["confidence_threshold"]
    if type(threshold) not in (float, int) or not math.isfinite(threshold) or not 0 <= threshold <= 100:
        raise ValueError("confidence_threshold must be finite pLDDT on the 0–100 scale")


def spans(flags):
    start = None
    for index, flag in enumerate([*flags, False], 1):
        if flag and start is None:
            start = index
        elif not flag and start is not None:
            yield start, index - 1
            start = None


def assess(codes, confidence, policy):
    validate_policy(policy)
    if not codes or any(code not in "abc" for code in codes) or len(codes) != len(confidence):
        raise ValueError("Complete, aligned P-SEA and per-residue confidence are required")
    if any(type(p) not in (int, float) or not math.isfinite(p) or not 0 <= p <= 100
           for p in confidence):
        raise ValueError("Per-residue confidence must be finite pLDDT on the 0–100 scale")
    uncertain = [code == "c" and p < policy["confidence_threshold"]
                 for code, p in zip(codes, confidence)]
    regions = [{"start": start, "end": end,
                "mean_confidence": sum(confidence[start - 1:end]) / (end - start + 1)}
               for start, end in spans(uncertain)
               if end - start + 1 >= policy["min_uncertain_coil_length"]]
    segments = []
    for start, end in spans([code == "c" for code in codes]):
        segments.append({"start": start, "end": end,
                         "terminal": start == 1 or end == len(codes),
                         "mean_confidence": sum(confidence[start - 1:end]) / (end - start + 1),
                         "contains_uncertain_run": any(start <= r["start"] <= end for r in regions),
                         "short_connecting_loop_candidate": end - start + 1 < policy["min_uncertain_coil_length"]})
    return {"schema": 1, "eligible": not regions,
            "reason": "No qualifying uncertain coil run" if not regions else "Long uncertain coil requires reassessment",
            "criterion": "contiguous-coil-residues-individually-below-threshold-v1",
            "scientific_status": "experimental-eligibility-not-fold-validation",
            "psea": codes, "confidence": list(confidence), "coil_segments": segments,
            "reconsider_regions": regions,
            "fractions": {name: codes.count(code) / len(codes)
                          for name, code in (("helix", "a"), ("sheet", "b"), ("coil", "c"))}}


def assess_structure(path: Path, expected_sequence: str, policy):
    # Same Biotite P-SEA coordinate assignment used by Studio's validation tools.
    # Use the caller's selected prediction environment; never switch runtimes.
    import biotite
    import numpy as np
    from biotite.sequence import ProteinSequence
    from biotite.structure import annotate_sse, get_residue_starts
    if path.suffix.lower() in {".cif", ".mmcif"}:
        from biotite.structure.io.pdbx import CIFFile, get_structure
        atoms = get_structure(CIFFile.read(path), model=1, extra_fields=["b_factor"])
    elif path.suffix.lower() == ".pdb":
        from biotite.structure.io.pdb import PDBFile
        atoms = PDBFile.read(path).get_structure(model=1, extra_fields=["b_factor"])
    else:
        raise ValueError("Initialization prediction must be PDB or mmCIF")
    if not len(atoms) or set(atoms.chain_id) != {"A"} or not np.isfinite(atoms.coord).all():
        raise ValueError("Initialization refinement requires one finite monomer on chain A")
    starts = get_residue_starts(atoms, add_exclusive_stop=True)
    observed, confidence, residue_ids = [], [], []
    for start, end in zip(starts[:-1], starts[1:]):
        residue = atoms[start:end]
        ca = residue[residue.atom_name == "CA"]
        if len(ca) != 1:
            raise ValueError("Every monomer residue requires exactly one alpha carbon")
        name = str(ca.res_name[0])
        observed.append("X" if name == "UNK" else ProteinSequence.convert_letter_3to1(name))
        confidence.append(float(ca.b_factor[0]))
        residue_ids.append({"number": int(ca.res_id[0]), "insertion_code": str(ca.ins_code[0])})
    if len(observed) != len(expected_sequence) or any(
            expected != "X" and expected != actual for expected, actual in zip(expected_sequence, observed)):
        raise ValueError("Prediction sequence differs from the recorded initialization input")
    result = assess("".join(annotate_sse(atoms)), confidence, policy)
    result["provenance"] = {"assignment": "Biotite P-SEA", "biotite_version": biotite.__version__,
                            "confidence": "predicted CA B-factor, pLDDT 0–100",
                            "observed_sequence": "".join(observed), "residue_ids": residue_ids}
    return result
