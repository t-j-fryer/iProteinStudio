#!/usr/bin/env python
"""Adapter between NanoHunter's Boltz-style YAML/outputs and AlphaFold 3.

Two modes:

  to-json      Convert a NanoHunter/Boltz prediction YAML into an AlphaFold 3
               input JSON (dialect alphafold3, version 4). Protein chains carry
               precomputed MSAs (A3M) where available, or empty MSAs for
               single-sequence mode, so AF3 can be run with
               --norun_data_pipeline and needs none of the ~1 TB genetic
               databases. Ligands are passed through as SMILES or CCD codes.

  from-output  Normalise an AF3 output directory into NanoHunter's predictor
               contract: <pred_min>/model_0.cif plus a confidence.json carrying
               `iptm` and `complex_plddt` (0-1, matching Boltz's scale) so the
               existing metric extraction works unchanged. Also records
               ligand_plddt / ptm / ranking_score for downstream use.

AF3 gives no binding-affinity head, so there is no P(bind) equivalent; callers
that rank on ligand pLDDT + P(bind) must fall back to ligand pLDDT with AF3.
"""

from __future__ import annotations

import re
import json
import shutil
import argparse
from pathlib import Path

import yaml


# ---------------------------------------------------------------- to-json


def a3m_to_msa_string(path):
    """Return an A3M file's contents, or None if unusable."""
    try:
        text = Path(path).read_text()
    except OSError:
        return None
    return text if text.strip().startswith(">") else None


def build_af3_json(yaml_path, name, seeds=(42,)):
    doc = yaml.safe_load(Path(yaml_path).read_text()) or {}
    sequences = []
    for entry in doc.get("sequences", []):
        if "protein" in entry:
            p = entry["protein"]
            if not p.get("sequence"):
                raise SystemExit(
                    f"Protein chain {p.get('id')} in {yaml_path} has no sequence. "
                    "AF3 needs a concrete sequence; pass the per-cycle YAML, not the template."
                )
            chain = {"id": p["id"], "sequence": p["sequence"]}
            msa = p.get("msa")
            # `msa: empty` (or absent) -> single-sequence mode; a path -> reuse it.
            if isinstance(msa, str) and msa and msa != "empty" and Path(msa).exists():
                content = a3m_to_msa_string(msa)
                if content is not None:
                    chain["unpairedMsa"] = content
                else:
                    chain["unpairedMsa"] = ""
            else:
                chain["unpairedMsa"] = ""
            chain["pairedMsa"] = ""
            chain["templates"] = []
            sequences.append({"protein": chain})
        elif "ligand" in entry:
            lig = entry["ligand"]
            out = {"id": lig["id"]}
            if lig.get("smiles"):
                out["smiles"] = lig["smiles"]
            elif lig.get("ccd"):
                ccd = lig["ccd"]
                out["ccdCodes"] = ccd if isinstance(ccd, list) else [ccd]
            else:
                raise SystemExit(f"Ligand {lig.get('id')} has neither smiles nor ccd.")
            sequences.append({"ligand": out})
        # Other entity types (dna/rna) are passed through verbatim if present.
        elif "dna" in entry or "rna" in entry:
            sequences.append(entry)

    if not sequences:
        raise SystemExit(f"No sequences parsed from {yaml_path}")

    return {
        "name": name,
        "sequences": sequences,
        "modelSeeds": list(seeds),
        "dialect": "alphafold3",
        "version": 4,
    }


# ------------------------------------------------------------ from-output


def _find_one(root, pattern):
    hits = sorted(Path(root).glob(pattern))
    return hits[0] if hits else None


def normalise_output(af3_out_dir, pred_min, ligand_chain="B"):
    af3_out_dir = Path(af3_out_dir)
    pred_min = Path(pred_min)
    pred_min.mkdir(parents=True, exist_ok=True)

    cif = _find_one(af3_out_dir, "**/*_model.cif")
    if cif is None:
        raise SystemExit(f"No AF3 *_model.cif found under {af3_out_dir}")
    shutil.copy(cif, pred_min / "model_0.cif")

    summary = _find_one(af3_out_dir, "**/*_summary_confidences.json")
    conf = _find_one(af3_out_dir, "**/*_confidences.json")
    # the summary file also matches *_confidences.json; prefer a distinct one
    if conf is not None and conf.name.endswith("_summary_confidences.json"):
        others = [p for p in sorted(af3_out_dir.glob("**/*_confidences.json"))
                  if not p.name.endswith("_summary_confidences.json")]
        conf = others[0] if others else None

    out = {}
    if summary is not None:
        s = json.loads(summary.read_text())
        if s.get("iptm") is not None:
            out["iptm"] = float(s["iptm"])
        if s.get("ptm") is not None:
            out["ptm"] = float(s["ptm"])
        if s.get("ranking_score") is not None:
            out["ranking_score"] = float(s["ranking_score"])
        if s.get("has_clash") is not None:
            out["has_clash"] = float(s["has_clash"])

    if conf is not None:
        c = json.loads(conf.read_text())
        plddts = c.get("atom_plddts") or []
        chains = c.get("atom_chain_ids") or []
        if plddts:
            # Boltz reports complex_plddt on a 0-1 scale; AF3 pLDDT is 0-100.
            out["complex_plddt"] = sum(plddts) / len(plddts) / 100.0
            if chains and len(chains) == len(plddts):
                lig = [p for p, ch in zip(plddts, chains) if ch == ligand_chain]
                if lig:
                    out["ligand_plddt"] = sum(lig) / len(lig)          # 0-100
                    out["ligand_plddt_fraction"] = out["ligand_plddt"] / 100.0
                prot = [p for p, ch in zip(plddts, chains) if ch != ligand_chain]
                if prot:
                    out["protein_plddt"] = sum(prot) / len(prot)

    out["predictor"] = "alphafold3"
    out["affinity_available"] = False   # AF3 has no P(bind) head
    (pred_min / "confidence.json").write_text(json.dumps(out, indent=2))
    if "iptm" in out:
        (pred_min / "iptm.txt").write_text(f"{out['iptm']}\n")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="mode", required=True)

    tj = sub.add_parser("to-json")
    tj.add_argument("--in-yaml", required=True)
    tj.add_argument("--out-json", required=True)
    tj.add_argument("--name", default="nanohunter")
    tj.add_argument("--seed", type=int, default=42)

    fo = sub.add_parser("from-output")
    fo.add_argument("--af3-out", required=True)
    fo.add_argument("--pred-min", required=True)
    fo.add_argument("--ligand-chain", default="B")

    args = ap.parse_args()
    if args.mode == "to-json":
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", args.name)
        j = build_af3_json(args.in_yaml, safe, seeds=(args.seed,))
        Path(args.out_json).write_text(json.dumps(j, indent=2))
        print(safe)
    else:
        out = normalise_output(args.af3_out, args.pred_min, args.ligand_chain)
        print(json.dumps(out))


if __name__ == "__main__":
    main()
