#!/usr/bin/env python3
"""Score holo predictions and select the top N.

Reuses ``nise_lib.rank_score`` unchanged: ``ligand_plddt/100 + pbind``
(ligand_plddt = mean B-factor of the predicted ligand chain, Boltz's pLDDT*100
convention; pbind = affinity_probability_binary), degrading to
``ligand_plddt/100`` alone when the affinity module didn't produce a P(bind)
for a design. Both terms are already/rescaled to 0-1, so the sum is a plain,
unweighted combination -- exactly NISE's own ranking metric.

Protein-target campaigns use the same file for a deliberately different
contract: every requested predictor must have produced a structure and an iPTM,
then designs are ranked by mean iPTM while the least-agreeing predictor is kept
as ``min_iptm``. PAE-capable predictors must also emit conservative
``ipSAE(min)``; its per-engine, mean and minimum values are retained as
diagnostics without silently changing the established iPTM rank order.
Ligand-only columns are neither required nor invented.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path

import studio_runtime


IPSAE_PREDICTORS = {"boltz", "intellifold", "protenix-v2", "protenix-mini"}


def to_float(value, default=float("nan")):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def prediction_name(row: dict) -> str:
    design = row.get("design") or row.get("name") or row.get("backbone") or ""
    index = str(row.get("seq_index", "")).strip()
    return f"{Path(design).stem}_{index}" if index else Path(design).stem


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
    parser.add_argument("--protein", action="store_true",
                        help="rank run_predictors.py output by cross-predictor iPTM")
    parser.add_argument("--predictors",
                        help="comma-separated predictors every protein design must contain")
    parser.add_argument("--sequences", type=Path,
                        help="sequences.csv used to restore sequence/backbone metadata in protein mode")
    parser.add_argument("--nanohunter-root", type=Path)
    args = parser.parse_args()

    args.nanohunter_root = args.nanohunter_root or default_root()
    studio_runtime.configure(args.nanohunter_root)
    nise_lib = studio_runtime

    rows = list(csv.DictReader(args.predictions.open()))
    if not rows:
        raise SystemExit(f"No rows in {args.predictions}")

    if args.protein:
        score_proteins(rows, args)
        return

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


def score_proteins(rows: list[dict], args: argparse.Namespace) -> None:
    """Require successful agreement across all requested protein predictors."""
    predictors = ([item.strip() for item in args.predictors.split(",") if item.strip()]
                  if args.predictors else
                  sorted({row.get("predictor", "") for row in rows if row.get("predictor")}))
    if not predictors:
        raise SystemExit("Protein prediction metrics contain no predictor names")

    sequence_rows: dict[str, dict] = {}
    if args.sequences:
        if not args.sequences.exists():
            raise SystemExit(f"No sequence table at {args.sequences}")
        for row in csv.DictReader(args.sequences.open()):
            key = prediction_name(row)
            if key:
                sequence_rows[key] = row

    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row.get("design", ""), []).append(row)

    scored = []
    dropped = []
    for design, design_rows in sorted(grouped.items()):
        by_predictor = {row.get("predictor", ""): row for row in design_rows}
        missing = [predictor for predictor in predictors if predictor not in by_predictor]
        failures = [predictor for predictor, row in by_predictor.items()
                    if str(row.get("exit_code", "")) != "0" or not row.get("structure")]
        iptms = {predictor: to_float(row.get("iptm"), default=None)
                 for predictor, row in by_predictor.items()}
        missing_scores = [predictor for predictor, value in iptms.items() if value is None]
        ipsae_predictors = [predictor for predictor in predictors
                            if predictor in IPSAE_PREDICTORS]
        ipsaes = {predictor: to_float(by_predictor[predictor].get("ipsae_min"), default=None)
                  for predictor in ipsae_predictors if predictor in by_predictor}
        missing_ipsae = [predictor for predictor in ipsae_predictors
                         if ipsaes.get(predictor) is None]
        if missing or failures or missing_scores or missing_ipsae:
            dropped.append({"design": design, "missing": missing,
                            "failed": failures, "missing_iptm": missing_scores,
                            "missing_ipsae_min": missing_ipsae})
            continue

        values = list(iptms.values())
        source = sequence_rows.get(design, {})
        ipsae_values = list(ipsaes.values())
        score_row = {
            "design": design,
            "name": design,
            "sequence": source.get("sequence", ""),
            "backbone_pdb": source.get("backbone_pdb", source.get("backbone", "")),
            "score": sum(values) / len(values),
            "mean_iptm": sum(values) / len(values),
            "min_iptm": min(values),
            "predictors": ",".join(predictors),
            "structures": json.dumps({p: by_predictor[p]["structure"] for p in predictors}),
            **{f"iptm_{p}": iptms[p] for p in predictors},
            **{f"ipsae_min_{p}": ipsaes[p] for p in ipsae_predictors},
        }
        if ipsae_values:
            score_row["mean_ipsae_min"] = sum(ipsae_values) / len(ipsae_values)
            score_row["min_ipsae_min"] = min(ipsae_values)
        scored.append(score_row)

    scored.sort(key=lambda row: (row["score"], row["min_iptm"]), reverse=True)
    if not scored:
        detail = json.dumps(dropped[:5], sort_keys=True)
        raise SystemExit(
            "No protein design succeeded with required iPTM/ipSAE(min) metrics: " + detail
        )
    if args.require_top_n and len(scored) < args.top_n:
        raise SystemExit(f"Need {args.top_n} scored designs, but only {len(scored)} passed")

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in scored for key in row})
    for filename, selected in (("scored_designs.csv", scored),
                               ("top100.csv", scored[: args.top_n])):
        with (output / filename).open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(selected)
    top = scored[: args.top_n]
    (output / "top100_manifest.json").write_text(json.dumps(top, indent=2) + "\n")
    (output / "dropped_designs.json").write_text(json.dumps(dropped, indent=2) + "\n")
    print(f"scored {len(scored)}/{len(grouped)} protein designs across "
          f"{len(predictors)} predictor(s); top mean iPTM={top[0]['score']:.3f}, "
          f"minimum={top[0]['min_iptm']:.3f} -> {output / 'top100.csv'}")


if __name__ == "__main__":
    main()
