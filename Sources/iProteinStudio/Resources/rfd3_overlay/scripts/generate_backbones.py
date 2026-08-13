#!/usr/bin/env python3
"""Generate resumable RFD3-MLX backbone batches from an official feature fixture."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import mlx.core as mx
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mlx_port"))

import rfd3_mlx as rfd3  # noqa: E402
from sampler import Sampler  # noqa: E402


AA3 = [
    "ALA", "ARG", "ASN", "ASP", "CYS", "GLN", "GLU", "GLY", "HIS", "ILE",
    "LEU", "LYS", "MET", "PHE", "PRO", "SER", "THR", "TRP", "TYR", "VAL",
]
REAL_PROTEIN_ATOMS = {"N", "CA", "C", "O", "CB", "CG", "CG1", "CG2", "CD", "CD1", "CD2",
                      "CE", "CE1", "CE2", "CE3", "CZ", "CZ2", "CZ3", "CH2", "ND1", "ND2",
                      "NE", "NE1", "NE2", "NH1", "NH2", "NZ", "OD1", "OD2", "OE1", "OE2",
                      "OG", "OG1", "OH", "SD", "SG"}
# RFD3 predicts an atom14 coordinate canvas, not sequence-conditioned sidechain
# geometry.  MPNN reconstructs C-beta internally from N/CA/C, so exporting the
# placeholder CB would add misleading sidechain context.
BINDER_ATOMS = {"N", "CA", "C", "O"}


def decode_atom_names(chars: np.ndarray) -> list[str]:
    codes = chars.reshape(-1, 4, 64).argmax(-1)
    return ["".join(chr(int(c) + 32) for c in row if c) for row in codes]


def pdb_atom_field(name: str, element: str) -> str:
    if len(name) >= 4:
        return name[:4]
    return (" " + name.ljust(3)) if len(element) == 1 else name.ljust(4)


class Fixture:
    def __init__(self, path: Path, ligand_code: str):
        self.path = path
        with np.load(path) as z:
            self.feats = {k[6:]: z[k] for k in z.files if k.startswith("feats/")}
            self.coord = np.asarray(z["coord_to_be_noised"], dtype=np.float32)
        self.tok = np.asarray(self.feats["atom_to_token_map"], dtype=int)
        self.names = decode_atom_names(self.feats["ref_atom_name_chars"])
        self.fixed_atoms = np.asarray(self.feats["is_motif_atom_with_fixed_coord"], dtype=bool)
        self.fixed_tokens = np.asarray(self.feats["is_motif_token_with_fully_fixed_coord"], dtype=bool)
        self.is_ca = np.asarray(self.feats["is_ca"], dtype=bool)
        self.restype = np.asarray(self.feats["restype"]).argmax(-1)
        self.residue_index = np.asarray(self.feats["residue_index"], dtype=int)
        self.rasa = np.asarray(self.feats["ref_atomwise_rasa"], dtype=int)
        self.n_tokens = self.fixed_tokens.size
        self.n_atoms = self.tok.size
        self.design_tokens = np.where(~self.fixed_tokens)[0]
        self.motif_tokens = np.where(self.fixed_tokens)[0]
        self.ligand_code = ligand_code
        if self.coord.ndim == 2:
            self.coord = self.coord[None]
        if self.coord.shape != (1, self.n_atoms, 3):
            raise ValueError(f"Unexpected coordinate shape {self.coord.shape}")

        counts = np.bincount(self.tok, minlength=self.n_tokens)
        token_has_ca = np.zeros(self.n_tokens, dtype=bool)
        np.logical_or.at(token_has_ca, self.tok, self.is_ca)
        # AtomWorks represents a small molecule as one token per atom and marks
        # each token's sole atom as central/CA-like.  Token atom count, not the
        # is_ca flag alone, therefore distinguishes ligand from protein motif.
        self.target_protein_tokens = np.where(self.fixed_tokens & (counts > 1))[0]
        self.ligand_tokens = np.where(self.fixed_tokens & (counts == 1))[0]
        if len(self.design_tokens) == 0:
            raise ValueError("Fixture has no diffused design tokens")

    def write_pdb(self, coords: np.ndarray, path: Path) -> None:
        target_num = {t: i + 1 for i, t in enumerate(self.target_protein_tokens)}
        ligand_num = {t: 1 for t in self.ligand_tokens}
        design_num = {t: i + 1 for i, t in enumerate(self.design_tokens)}
        lines: list[str] = []
        serial = 1
        for atom_idx, (token, name) in enumerate(zip(self.tok, self.names, strict=True)):
            x, y, z = coords[atom_idx]
            if token in design_num:
                if name not in BINDER_ATOMS:
                    continue
                record, chain, resnum, resname = "ATOM  ", "A", design_num[token], "ALA"
            elif token in target_num:
                if name not in REAL_PROTEIN_ATOMS:
                    continue
                ri = int(self.restype[token])
                record, chain, resnum = "ATOM  ", "B", target_num[token]
                resname = AA3[ri] if 0 <= ri < len(AA3) else "UNK"
            elif token in ligand_num:
                record, chain, resnum, resname = "HETATM", "B", 1, self.ligand_code
            else:
                continue
            element = "".join(c for c in name if c.isalpha())[:2].strip().upper() or "C"
            if element not in {"CL", "BR"}:
                element = element[:1]
            atom_field = pdb_atom_field(name, element)
            lines.append(
                f"{record}{serial:5d} {atom_field}{' ':1}{resname:>3} {chain}{resnum:4d}{' ':1}   "
                f"{x:8.3f}{y:8.3f}{z:8.3f}{1.00:6.2f}{0.00:6.2f}          {element:>2}  "
            )
            serial += 1
        lines.extend(["TER", "END"])
        path.write_text("\n".join(lines) + "\n")

    def metrics(self, coords: np.ndarray) -> dict[str, float | int]:
        ca_atom = {int(self.tok[a]): int(a) for a in np.where(self.is_ca)[0]}
        bca = np.asarray([coords[ca_atom[t]] for t in self.design_tokens])
        seg = np.linalg.norm(np.diff(bca, axis=0), axis=1)
        motif_xyz = coords[self.fixed_atoms]
        d_iface = np.linalg.norm(bca[:, None] - motif_xyz[None], axis=-1)
        drift = np.linalg.norm(
            coords[self.fixed_atoms] - self.coord[0, self.fixed_atoms], axis=1
        )
        out: dict[str, float | int] = {
            "binder_length": int(len(self.design_tokens)),
            "ca_mean": float(seg.mean()),
            "ca_min": float(seg.min()),
            "ca_max": float(seg.max()),
            "ca_valid_pct": float(((seg > 3.6) & (seg < 4.0)).mean() * 100),
            "binder_rg": float(np.sqrt(((bca - bca.mean(0)) ** 2).sum(1).mean())),
            "interface_min": float(d_iface.min()),
            "contacts_8A": int((d_iface < 8.0).sum()),
            "contacts_5A": int((d_iface < 5.0).sum()),
            "motif_max_drift": float(drift.max() if drift.size else 0.0),
        }
        if self.ligand_tokens.size:
            buried = self.fixed_atoms & (self.rasa[:, 0] == 1)
            exposed = self.fixed_atoms & (self.rasa[:, 2] == 1)
            for label, mask in (("buried", buried), ("exposed", exposed)):
                d = np.linalg.norm(bca[:, None] - coords[mask][None], axis=-1)
                out[f"{label}_atom_min"] = float(d.min())
                out[f"{label}_ca_contacts_8A"] = int((d < 8.0).sum())
        return out


def write_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        return
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--num-designs", type=int, default=1)
    parser.add_argument("--steps", type=int, default=200)
    parser.add_argument("--recycle", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--seed-start", type=int, default=0)
    parser.add_argument("--precision", choices=["fp32", "bf16", "int8"], default="bf16")
    parser.add_argument("--ligand-code", default="FHE")
    parser.add_argument("--cache-limit-gb", type=float, default=4.0)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.num_designs < 1 or args.batch_size < 1 or args.steps < 2:
        raise SystemExit("--num-designs/--batch-size must be >=1 and --steps >=2")

    mx.set_default_device(mx.gpu)
    try:
        mx.set_cache_limit(int(args.cache_limit_gb * 1024**3))
    except Exception:
        pass

    fixture = Fixture(args.fixture.resolve(), args.ligand_code)
    output = args.output.resolve()
    backbone_dir = output / "backbones"
    result_dir = output / "results"
    backbone_dir.mkdir(parents=True, exist_ok=True)
    result_dir.mkdir(parents=True, exist_ok=True)

    weights = mx.load(str(ROOT / "weights" / "rfd3_core.safetensors"))
    if args.precision == "bf16":
        weights = rfd3.to_bf16(weights)
    elif args.precision == "int8":
        weights = rfd3.quantize_weights(weights, 8)

    manifest = {
        "fixture": str(fixture.path),
        "weights": str(ROOT / "weights" / "rfd3_core.safetensors"),
        "num_designs": args.num_designs,
        "steps": args.steps,
        "recycle": args.recycle,
        "batch_size": args.batch_size,
        "seed_start": args.seed_start,
        "precision": args.precision,
        "cache_limit_gb": args.cache_limit_gb,
        "tokens": fixture.n_tokens,
        "atoms": fixture.n_atoms,
        "design_tokens": int(fixture.design_tokens.size),
        "target_protein_tokens": int(fixture.target_protein_tokens.size),
        "ligand_tokens": int(fixture.ligand_tokens.size),
    }
    (output / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    for start in range(0, args.num_designs, args.batch_size):
        stop = min(start + args.batch_size, args.num_designs)
        indices = list(range(start, stop))
        paths = [result_dir / f"design_{i + 1:04d}.json" for i in indices]
        if not args.overwrite and all(path.exists() for path in paths):
            print(f"batch {start // args.batch_size:04d}: cached", flush=True)
            continue
        seed = args.seed_start + start
        sampler = Sampler(
            weights,
            num_timesteps=args.steps,
            n_recycle=args.recycle,
            seed=seed,
        )
        begin = time.time()
        prediction = sampler.generate(
            fixture.feats,
            D=len(indices),
            coord_to_be_noised=fixture.coord,
        )
        mx.eval(prediction["X_L"], prediction["sequence_indices_I"])
        wall = time.time() - begin
        coords = np.asarray(prediction["X_L"])
        for offset, design_idx in enumerate(indices):
            name = f"design_{design_idx + 1:04d}"
            pdb_path = backbone_dir / f"{name}.pdb"
            fixture.write_pdb(coords[offset], pdb_path)
            row = {
                "design": name,
                "design_index": design_idx + 1,
                "batch_index": start // args.batch_size,
                "batch_seed": seed,
                "batch_size_actual": len(indices),
                "batch_wall_sec": wall,
                "sec_per_design": wall / len(indices),
                "steps": args.steps,
                "recycle": args.recycle,
                "precision": args.precision,
                "backbone_pdb": str(pdb_path),
                **fixture.metrics(coords[offset]),
            }
            paths[offset].write_text(json.dumps(row, indent=2) + "\n")
        print(
            f"batch {start // args.batch_size:04d}: designs {start + 1}-{stop}, "
            f"{wall:.2f}s ({wall / len(indices):.2f}s/design)",
            flush=True,
        )

    rows = [json.loads(path.read_text()) for path in sorted(result_dir.glob("design_*.json"))]
    write_csv(rows, output / "backbone_metrics.csv")
    print(f"wrote {len(rows)} designs -> {output}")


if __name__ == "__main__":
    main()
