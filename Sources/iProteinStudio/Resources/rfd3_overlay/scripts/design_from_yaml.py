#!/usr/bin/env python3
"""Run an RFD3 backbone-design job from a single YAML spec.

The YAML is a ``DesignInputSpecification`` (input PDB/CIF, contig, ligand CCD
code, and any ``select_*`` / ``infer_ori_strategy`` / ``is_non_loopy``
conditioning) plus an optional ``run:`` block of sampling knobs. This script
turns that into the two things RFD3 actually needs, in order:

  1. fixtures -- ``milestone0_oracle.py`` once per binder length (official
     Foundry is the only code path that can build ligand/RASA/hbond features);
  2. backbones -- ``run_backbone_bins.py``, which fans each fixture out into
     concurrent MLX shape queues and flattens the result into the usual
     ``rfd3/backbones/design_%04d.pdb`` set.

A fixture is frozen at ONE binder length, so a length range becomes one
fixture per bin (``lengths:`` or ``min_length``/``max_length``/``num_bins``).

Before spending any CPU on a fixture, a preflight pass resolves every
``select_*`` key and atom name against the input structure -- catching the
usual failure (a mistyped ligand atom name) in a second rather than minutes
deep inside Foundry.

Usage:
    source rfd3_env.sh
    .venv/bin/python scripts/design_from_yaml.py path/to/spec.yaml
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

# Keys consumed by this script; everything else in the YAML is passed through
# verbatim to Foundry's DesignInputSpecification (which has extra="forbid",
# so a typo'd conditioning field still fails loudly at fixture time).
RUN_KEYS = {
    "name", "output", "num_designs",
    "lengths", "min_length", "max_length", "num_bins",
    "timesteps", "n_recycle", "seed_base",
    "batch_size", "queues_per_bin", "precision",
    "ccd_mirror", "conformers",
}

DEFAULTS = {
    "num_designs": 100,
    "num_bins": 1,
    "timesteps": 200,
    "n_recycle": 2,
    "seed_base": 0,
    "batch_size": 8,      # measured M4 Max optimum (batch 16/32 regress)
    "queues_per_bin": 2,  # 2 concurrent shape queues = 9.6 designs/min
    "precision": "bf16",
}

# Atom-name macros that InputSelection expands itself -- not literal names.
ATOM_MACROS = {"ALL", "BKBN", "TIP", "SIDECHAIN", "NONE"}

KEY_RE = re.compile(r"^([A-Za-z0-9])(-?\d+)(?:-(-?\d+))?$")


# --------------------------------------------------------------------------- #
# spec loading
# --------------------------------------------------------------------------- #
def load_yaml(path: Path) -> tuple[dict, dict]:
    """Split the YAML into (design spec, run knobs)."""
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise SystemExit(f"{path}: expected a YAML mapping at the top level")

    # A single-key wrapper ({design_name: {...}}) is accepted so the same file
    # shape as oracle/input_*.json round-trips.
    wrapped_name = None
    if len(raw) == 1:
        only_key, only_value = next(iter(raw.items()))
        if isinstance(only_value, dict) and any(k.startswith("select_") or k in {"input", "contig"} for k in only_value):
            wrapped_name, raw = only_key, only_value

    run = dict(DEFAULTS)
    run.update(raw.pop("run", {}) or {})
    for key in list(raw):
        if key in RUN_KEYS:
            run[key] = raw.pop(key)
    if wrapped_name and "name" not in run:
        run["name"] = wrapped_name
    return raw, run


def resolve_paths(spec: dict, yaml_dir: Path) -> None:
    """Make `input` absolute -- subprocesses run with cwd=ROOT (CLAUDE.md rule 5)."""
    if not spec.get("input"):
        return
    path = Path(str(spec["input"])).expanduser()
    if not path.is_absolute():
        candidates = [yaml_dir / path, ROOT / path, Path.cwd() / path]
        path = next((c for c in candidates if c.exists()), candidates[0])
    if not path.exists():
        raise SystemExit(f"input structure not found: {spec['input']}")
    spec["input"] = str(path.resolve())


# --------------------------------------------------------------------------- #
# preflight: validate selection keys/atom names against the input structure
# --------------------------------------------------------------------------- #
def preflight(spec: dict) -> None:
    if not spec.get("input"):
        print("preflight: no `input` structure (ligand-free design) -- skipped")
        return
    try:
        from biotite.structure.io.pdbx import CIFFile, get_structure as cif_structure
        from biotite.structure.io.pdb import PDBFile
    except ImportError:  # pragma: no cover - biotite ships with the venv
        print("preflight: biotite unavailable -- skipped")
        return

    path = Path(spec["input"])
    if path.suffix.lower() in {".cif", ".mmcif", ".bcif"}:
        array = cif_structure(CIFFile.read(path), model=1)
    else:
        array = PDBFile.read(path).get_structure(model=1)

    problems: list[str] = []
    for field, value in spec.items():
        if not field.startswith("select_") or not isinstance(value, dict):
            continue
        for key, atoms in value.items():
            names = [a.strip() for a in str(atoms).split(",") if a.strip()]
            mask = _key_mask(array, str(key))
            if mask is None:
                problems.append(f"{field}[{key}]: key is neither chain+resnum (e.g. 'C1') nor a residue name in {path.name}")
                continue
            if not mask.any():
                problems.append(f"{field}[{key}]: no atoms in {path.name} match this key")
                continue
            present = set(array.atom_name[mask])
            missing = [n for n in names if n.upper() not in ATOM_MACROS and n not in present]
            if missing:
                problems.append(
                    f"{field}[{key}]: {len(missing)} atom name(s) not in the structure: "
                    f"{', '.join(missing)}  (available: {', '.join(sorted(present))})"
                )

    if problems:
        raise SystemExit("preflight failed:\n  - " + "\n  - ".join(problems))
    print(f"preflight ok: all select_* keys and atom names resolve against {path.name}")


def _key_mask(array, key: str):
    """Mask for a selection key: 'C1' / 'C1-5' (chain+resnum) or 'FHE' (res name)."""
    match = KEY_RE.match(key)
    if match:
        chain, start, end = match.group(1), int(match.group(2)), match.group(3)
        end = int(end) if end is not None else start
        return (array.chain_id == chain) & (array.res_id >= start) & (array.res_id <= end)
    if key in set(array.res_name):
        return array.res_name == key
    return None


# --------------------------------------------------------------------------- #
# length bins
# --------------------------------------------------------------------------- #
def parse_fixed_length(text: str | int | None) -> tuple[int, int] | None:
    if text is None:
        return None
    text = str(text).strip()
    if text.isdigit():
        return int(text), int(text)
    match = re.fullmatch(r"(\d+)\s*-\s*(\d+)", text)
    return (int(match.group(1)), int(match.group(2))) if match else None


def binder_length_from_contig(contig) -> tuple[int, int] | None:
    if not isinstance(contig, str):
        return None
    for segment in contig.split(","):
        parsed = parse_fixed_length(segment.strip().rstrip("/"))
        if parsed:  # a chainless "60-60" segment is the diffused binder
            return parsed
    return None


def fixed_motif_residue_count(contig) -> int:
    """Return the number of fixed polymer/ligand components in a contig.

    Foundry's ``length`` constraint is the total number of components, whereas
    this runner's ``lengths`` option deliberately means *diffused binder amino
    acids*.  A contig such as ``65-150,/0,C1-1`` therefore needs total length
    66 for a 65-aa binder.  Protein-target motifs work the same way (for
    example ``60-60,/0,B1-71`` needs total length 131).
    """
    if not isinstance(contig, str):
        return 0
    total = 0
    for segment in contig.split(","):
        segment = segment.strip()
        if not segment or segment == "/0" or not any(c.isalpha() for c in segment):
            continue
        match = re.fullmatch(r"[A-Za-z](\d+)(?:-(\d+))?", segment)
        if not match:
            raise SystemExit(f"cannot count fixed motif residues in contig segment: {segment!r}")
        start = int(match.group(1))
        end = int(match.group(2) or start)
        total += end - start + 1
    return total


def plan_lengths(spec: dict, run: dict) -> list[int]:
    # Partial diffusion preserves the input composition. Foundry explicitly
    # forbids a `length` alongside partial_t, so infer the diffused protein
    # chain length and ignore de-novo bin controls.
    if spec.get("partial_t") is not None:
        return [input_chain_length(spec, "A")]
    if run.get("lengths"):
        return [int(x) for x in run["lengths"]]
    if run.get("min_length") is not None and run.get("max_length") is not None:
        lo, hi, n = int(run["min_length"]), int(run["max_length"]), int(run["num_bins"])
        if n < 1:
            raise SystemExit("num_bins must be >= 1")
        if n == 1:
            return [lo]
        step = (hi - lo) / (n - 1)
        return sorted({round(lo + step * i) for i in range(n)})

    declared = parse_fixed_length(spec.get("length")) or binder_length_from_contig(spec.get("contig"))
    if declared is None:
        raise SystemExit(
            "cannot determine the binder length: give a fixed `length: \"80-80\"`, a contig with a "
            "fixed binder segment (e.g. \"80-80,/0,B1-71\"), or a `lengths:`/`min_length`+`max_length` run knob"
        )
    lo, hi = declared
    if lo != hi:
        raise SystemExit(
            f"binder length is a range ({lo}-{hi}), but one fixture is frozen at one length. "
            f"Set `lengths: [{lo}, ..., {hi}]` (or min_length/max_length/num_bins) to build one fixture per bin."
        )
    return [lo]


def input_chain_length(spec: dict, chain: str) -> int:
    """Count distinct protein residues in one input chain."""
    if not spec.get("input"):
        raise SystemExit("partial diffusion requires an input structure")
    try:
        from biotite.structure.io.pdbx import CIFFile, get_structure as cif_structure
        from biotite.structure.io.pdb import PDBFile
        path = Path(spec["input"])
        array = (cif_structure(CIFFile.read(path), model=1)
                 if path.suffix.lower() in {".cif", ".mmcif", ".bcif"}
                 else PDBFile.read(path).get_structure(model=1))
        mask = (array.chain_id == chain) & array.hetero.__eq__(False)
        ids = set(zip(array.chain_id[mask].tolist(), array.res_id[mask].tolist()))
    except Exception as exc:
        raise SystemExit(f"could not read partial-diffusion chain {chain}: {exc}") from exc
    if not ids:
        raise SystemExit(f"partial-diffusion input has no protein residues in chain {chain}")
    return len(ids)


def allocate(total: int, n: int) -> list[int]:
    base, remainder = divmod(total, n)
    return [base + (1 if i < remainder else 0) for i in range(n)]


# --------------------------------------------------------------------------- #
# stages
# --------------------------------------------------------------------------- #
def parse_conformers(value) -> list[tuple[str, float, str]]:
    """``path:weight:label`` triples, or a JSON list of the same fields.

    A flexible ligand has no single right geometry, so a campaign may want to
    spread its budget over several. Each conformer becomes its own set of
    fixtures -- one per length -- and its share of the design quota.
    """
    if not value:
        return []
    if isinstance(value, list):
        return [(str(c["path"]), float(c.get("weight", 1.0)), str(c.get("label", "")))
                for c in value]
    out = []
    for chunk in str(value).split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split(":")
        path = parts[0]
        weight = float(parts[1]) if len(parts) > 1 and parts[1] else 1.0
        label = parts[2] if len(parts) > 2 else ""
        out.append((path, weight, label))
    return out


def build_fixtures(spec: dict, run: dict, name: str, lengths: list[int],
                   campaign: Path, env: dict, overwrite: bool,
                   conformers: list[tuple[str, float, str]] | None = None) -> Path:
    oracle_dir = ROOT / "oracle"
    oracle_dir.mkdir(exist_ok=True)
    rfd3_dir = campaign / "rfd3"
    rfd3_dir.mkdir(parents=True, exist_ok=True)

    # Without an explicit conformer list this is the original single-input path,
    # so existing campaigns behave exactly as before.
    conformers = conformers or [(spec.get("input"), 1.0, "")]
    total_weight = sum(max(0.0, w) for _, w, _ in conformers) or 1.0

    motif_residues = fixed_motif_residue_count(spec.get("contig"))
    bins = []
    index = 0
    for conf_path, weight, label in conformers:
        share = max(0.0, weight) / total_weight
        conf_designs = int(round(int(run["num_designs"]) * share))
        if conf_designs <= 0:
            continue
        quotas = allocate(conf_designs, len(lengths))
        tag = f"_{label}" if label else ""
        bins.extend(_bins_for_conformer(spec, run, name, lengths, quotas, conf_path, tag,
                                        motif_residues, oracle_dir, rfd3_dir, env,
                                        overwrite, start_index=index))
        index += len(lengths)

    manifest_path = rfd3_dir / "bin_manifest.json"
    manifest_path.write_text(json.dumps({
        "design_name": name,
        "design_mode": ("partialDiffusion" if spec.get("partial_t") is not None
                        else "motifScaffolding" if spec.get("unindex") else "deNovo"),
        "component_id": spec.get("ligand"),
        "ccd_mirror": env.get("CCD_MIRROR_PATH"),
        "num_designs": int(run["num_designs"]),
        "timesteps": run["timesteps"], "n_recycle": run["n_recycle"],
        "conformers": [{"path": p, "weight": w, "label": l} for p, w, l in conformers],
        "bins": bins,
    }, indent=2) + "\n")
    total = sum(b["quota"] for b in bins)
    print(f"  wrote {len(bins)} bin(s), {total} designs -> {manifest_path}")
    return manifest_path


def _bins_for_conformer(spec, run, name, lengths, quotas, conf_path, tag, motif_residues,
                        oracle_dir, rfd3_dir, env, overwrite, start_index):
    bins = []
    for k, (length, quota) in enumerate(zip(lengths, quotas, strict=True)):
        i = start_index + k
        bin_name = f"{name}{tag}" if len(lengths) == 1 else f"{name}{tag}_L{length}"
        input_json = oracle_dir / f"input_{bin_name}.json"
        fixture = oracle_dir / f"oracle_{bin_name}.npz"

        bin_spec = dict(spec)
        if conf_path:
            bin_spec["input"] = str(conf_path)
        total_length = length + motif_residues
        if spec.get("partial_t") is None:
            bin_spec["length"] = f"{total_length}-{total_length}"
        input_json.write_text(json.dumps({bin_name: bin_spec}, indent=2) + "\n")

        if fixture.exists() and not overwrite:
            print(f"  L{length}: fixture cached -> {fixture.relative_to(ROOT)}")
        else:
            log_path = rfd3_dir / f"fixture_{bin_name}.log"
            cmd = [
                sys.executable, str(ROOT / "milestone0_oracle.py"),
                "--name", bin_name, "--input_json", str(input_json),
                "--timesteps", str(run["timesteps"]), "--n_recycle", str(run["n_recycle"]),
                "--seed", str(int(run["seed_base"]) + i), "--features-only",
            ]
            started = time.time()
            with log_path.open("w") as handle:
                result = subprocess.run(cmd, cwd=ROOT, env=env, stdout=handle, stderr=subprocess.STDOUT)
            if result.returncode:
                raise SystemExit(f"fixture build failed for L{length} (exit {result.returncode}); see {log_path}")
            print(f"  L{length}: fixture built in {time.time() - started:.1f}s -> {fixture.relative_to(ROOT)}")

        bins.append({
            "bin_index": i, "length": length, "binder_length": length,
            "total_component_length": total_length, "fixed_motif_residues": motif_residues,
            "quota": quota, "name": bin_name,
            "conformer": str(conf_path) if conf_path else None,
            "input_json": str(input_json), "fixture": str(fixture),
            "seed": int(run["seed_base"]) + i,
            "design_mode": ("partialDiffusion" if spec.get("partial_t") is not None
                            else "motifScaffolding" if spec.get("unindex") else "deNovo"),
            "motif_source_residues": ([part.strip() for part in str(spec.get("unindex", "")).split(",")
                                        if part.strip()]),
            "motif_fixed_atoms": {
                residue: [atom.strip().upper() for atom in str(atoms).split(",") if atom.strip()]
                for residue, atoms in (spec.get("select_fixed_atoms") or {}).items()
                if residue in {part.strip() for part in str(spec.get("unindex", "")).split(",")}
            },
        })
    return bins


def generate_backbones(run: dict, spec: dict, campaign: Path, manifest_path: Path, env: dict) -> None:
    cmd = [
        sys.executable, str(ROOT / "scripts" / "run_backbone_bins.py"),
        "--bin-manifest", str(manifest_path),
        "--output", str(campaign / "rfd3"),
        "--batch-size", str(run["batch_size"]),
        "--queues-per-bin", str(run["queues_per_bin"]),
        "--precision", run["precision"],
        "--steps", str(run["timesteps"]),
        "--recycle", str(run["n_recycle"]),
    ]
    if spec.get("ligand"):
        cmd += ["--ligand-code", str(spec["ligand"])]
    print(f"$ {' '.join(cmd)}")
    if subprocess.run(cmd, cwd=ROOT, env=env).returncode:
        raise SystemExit("backbone generation failed")


# --------------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("spec", type=Path, help="YAML design spec")
    parser.add_argument("--name", help="design/campaign name (default: YAML filename stem)")
    parser.add_argument("--output", type=Path, help="campaign dir (default: campaigns/<name>)")
    parser.add_argument("--num-designs", type=int)
    parser.add_argument("--lengths", help="comma-separated binder lengths, one fixture each")
    parser.add_argument("--batch-size", type=int)
    parser.add_argument("--queues-per-bin", type=int)
    parser.add_argument("--precision", choices=["fp32", "bf16", "int8"])
    parser.add_argument("--timesteps", type=int)
    parser.add_argument("--n-recycle", type=int)
    parser.add_argument("--seed-base", type=int)
    parser.add_argument("--ccd-mirror", type=Path, help="local CCD mirror dir (for a non-PDB ligand code)")
    parser.add_argument("--conformers",
                        help="comma-separated path:weight:label -- design across several ligand "
                             "geometries, splitting the design quota by weight")
    parser.add_argument("--stage", choices=["check", "fixtures", "backbones", "all"], default="all")
    parser.add_argument("--overwrite", action="store_true", help="rebuild fixtures even if cached")
    args = parser.parse_args()

    spec, run = load_yaml(args.spec.resolve())
    for key in ("name", "num_designs", "batch_size", "queues_per_bin", "precision",
                "timesteps", "n_recycle", "seed_base"):
        value = getattr(args, key)
        if value is not None:
            run[key] = value
    if args.output is not None:
        run["output"] = str(args.output)
    if args.ccd_mirror is not None:
        run["ccd_mirror"] = str(args.ccd_mirror)
    if args.lengths:
        run["lengths"] = [int(x) for x in args.lengths.split(",")]

    name = str(run.get("name") or args.spec.stem).replace("-", "_")
    campaign = Path(run.get("output") or (ROOT / "campaigns" / name))
    campaign = campaign if campaign.is_absolute() else (ROOT / campaign)
    campaign = campaign.resolve()

    resolve_paths(spec, args.spec.resolve().parent)
    preflight(spec)
    lengths = plan_lengths(spec, run)

    env = os.environ.copy()
    env.update({"DEBUG": "false", "TOKENIZERS_PARALLELISM": "false"})
    mirror = run.get("ccd_mirror") or env.get("CCD_MIRROR_PATH") or str(ROOT / "assets" / "fluorescein" / "ccd")
    env["CCD_MIRROR_PATH"] = str(Path(mirror).expanduser().resolve())

    print(f"design   : {name}")
    print(f"campaign : {campaign}")
    print(f"ligand   : {spec.get('ligand') or '(none)'}   ccd mirror: {env['CCD_MIRROR_PATH']}")
    print(f"lengths  : {lengths}  ({run['num_designs']} designs total)")
    if args.stage == "check":
        print(json.dumps({name: spec}, indent=2))
        return

    campaign.mkdir(parents=True, exist_ok=True)
    (campaign / "config").mkdir(exist_ok=True)
    (campaign / "config" / "spec.yaml").write_text(args.spec.read_text())

    conformers = parse_conformers(args.conformers or run.get("conformers"))
    if conformers:
        print(f"conformers: {len(conformers)} " +
              ", ".join(f"{(l or Path(p).stem)}={w:.2f}" for p, w, l in conformers))

    print("=== stage: fixtures ===")
    manifest_path = build_fixtures(spec, run, name, lengths, campaign, env, args.overwrite,
                                   conformers=conformers)
    if args.stage == "fixtures":
        return

    print("=== stage: backbones ===")
    generate_backbones(run, spec, campaign, manifest_path, env)
    print(f"done -> {campaign / 'rfd3' / 'backbones'}")


if __name__ == "__main__":
    main()
