"""Beta's apo input and weighted preorganisation calculation.

Ported from the source fingerprinted in UPSTREAM.json. Studio's runtime owns
prediction, checkpointing and shortlist handling; these numerical functions
retain the upstream calculation.
"""
from __future__ import annotations
from pathlib import Path
import metrics

PREORG_REF = 2.0
FOLD_REF = 3.0
DEFAULT_W_PREORG = 0.5
DEFAULT_W_FOLD = 0.25


def write_apo_yaml(path, binder_seq, binder_chain="A"):
    """Binder alone: no ligand, no affinity properties, no pocket constraint."""
    Path(path).write_text(
        "sequences:\n"
        "  - protein:\n"
        f"      id: {binder_chain}\n"
        f"      sequence: {binder_seq}\n"
        "      msa: empty\n"
        "version: 1\n")


def combine(base_score, pre: metrics.Preorg, w_preorg=DEFAULT_W_PREORG,
            w_fold=DEFAULT_W_FOLD, preorg_ref=PREORG_REF, fold_ref=FOLD_REF):
    """base + w_preorg*(preorganised) + w_fold*(folds without its ligand).

    Both terms are clamped to [0,1] and are rewards, not penalties, so adding them
    can only reorder the shortlist - it never drags a design below a candidate that
    was not apo-folded at all.
    """
    pterm = max(0.0, 1.0 - pre.preorg_rmsd / preorg_ref)
    gca = pre.global_ca_rmsd
    fterm = max(0.0, 1.0 - gca / fold_ref) if gca == gca else 0.0
    return round(base_score + w_preorg * pterm + w_fold * fterm, 4), \
        round(pterm, 4), round(fterm, 4)
