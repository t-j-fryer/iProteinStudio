#!/usr/bin/env python3
"""Score holo predictions with NISE's composite metric and select the top N.

Reuses ``nise_lib.rank_score`` unchanged: ``ligand_plddt/100 + pbind``
(ligand_plddt = mean B-factor of the predicted ligand chain, Boltz's pLDDT*100
convention; pbind = affinity_probability_binary), degrading to
``ligand_plddt/100`` alone when the affinity module didn't produce a P(bind)
for a design. Both terms are already/rescaled to 0-1, so the sum is a plain,
unweighted combination -- exactly NISE's own ranking metric.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import os
from pathlib import Path


def to_float(value, default=float("nan")):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def default_root() -> Path:
    """Where venvs/ and src/ live.

    From the environment the app sets, else this checkout's parent -- rfd3 is
    installed inside the pipeline root. Never a hard-coded home directory:
    that is one developer's machine, not the user's.
    """
    env = os.environ.get("NANOHUNTER_ROOT") or os.environ.get("IPROTEIN_ROOT")
    if env:
        return Path(env)
    # Installed layout is <root>/rfd3/scripts/, so the root is two levels up.
    # Verify rather than assume: a standalone checkout has no venvs/ above it,
    # and silently pointing at a home directory would be worse than saying so.
    candidate = Path(__file__).resolve().parents[2]
    if (candidate / "venvs").is_dir():
        return candidate
    raise SystemExit(
        "Cannot locate the pipeline root (no venvs/ found). "
        "Set NANOHUNTER_ROOT, or pass --nanohunter-root explicitly.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, required=True, help="predictions/holo/prediction_metrics.csv")
    parser.add_argument("--output", type=Path, required=True, help="campaign analysis/ dir")
    parser.add_argument("--top-n", type=int, default=100)
    parser.add_argument("--require-pbind", action="store_true",
                        help="exclude predictions without an affinity-head P(bind)")
    parser.add_argument("--require-top-n", action="store_true",
                        help="fail unless at least --top-n valid scored designs exist")
    parser.add_argument("--nanohunter-root", type=Path, default=default_root())
    args = parser.parse_args()

    nise_dir = args.nanohunter_root.resolve() / "scripts" / "nise"
    sys.path.insert(0, str(nise_dir))
    import nise_lib  # noqa: E402

    rows = list(csv.DictReader(args.predictions.open()))
    if not rows:
        raise SystemExit(f"No rows in {args.predictions}")

    scored = []
    for row in rows:
        if row.get("ok") != "True":
            continue
        pbind_raw = row.get("pbind", "")
        pbind = to_float(pbind_raw, default=None) if pbind_raw not in ("", "None") else None
        if args.require_pbind and pbind is None:
            continue
        pred = nise_lib.Prediction(
            name=row["name"], pdb=row.get("pdb", ""),
            ligand_plddt=to_float(row.get("ligand_plddt")), pbind=pbind,
        )
        score = nise_lib.rank_score(pred, mode="auto")
        scored.append({**row, "score": score})

    scored.sort(key=lambda r: r["score"], reverse=True)
    if not scored:
        raise SystemExit("No successful predictions with the required score components")
    if args.require_top_n and len(scored) < args.top_n:
        raise SystemExit(f"Need {args.top_n} scored designs, but only {len(scored)} passed")

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in scored for key in row})
    with (output / "scored_designs.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(scored)

    top = scored[: args.top_n]
    top_fields = ["design", "seq_index", "sequence", "backbone_pdb", "score", "ligand_plddt", "pbind", "name", "pdb"]
    with (output / "top100.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=top_fields)
        writer.writeheader()
        for row in top:
            writer.writerow({key: row.get(key, "") for key in top_fields})

    (output / "top100_manifest.json").write_text(json.dumps(top, indent=2) + "\n")
    print(
        f"scored {len(scored)}/{len(rows)} designs (dropped {len(rows) - len(scored)} failed folds); "
        f"top score={top[0]['score']:.3f}, rank-{len(top)} score={top[-1]['score']:.3f} -> {output / 'top100.csv'}"
    )


if __name__ == "__main__":
    main()
