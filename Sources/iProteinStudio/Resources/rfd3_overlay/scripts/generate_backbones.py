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
    def __init__(self, path: Path, ligand_code: str, motif_source_residues: list[str]):
        self.path = path
        with np.load(path) as z:
            self.feats = {k[6:]: z[k] for k in z.files if k.startswith("feats/")}
            self.coord = np.asarray(z["coord_to_be_noised"], dtype=np.float32)
        self.tok = np.asarray(self.feats["atom_to_token_map"], dtype=int)
        self.names = decode_atom_names(self.feats["ref_atom_name_chars"])
        self.fixed_atoms = np.asarray(self.feats["is_motif_atom_with_fixed_coord"], dtype=bool)
        self.fixed_tokens = np.asarray(self.feats["is_motif_token_with_fully_fixed_coord"], dtype=bool)
        self.unindexed_mask = np.asarray(
            self.feats.get("is_motif_token_unindexed", np.zeros_like(self.fixed_tokens)), dtype=bool)
        self.protein_mask = np.asarray(
            self.feats.get("is_protein", np.ones_like(self.fixed_tokens)), dtype=bool)
        self.ligand_mask = np.asarray(
            self.feats.get("is_ligand", np.zeros_like(self.fixed_tokens)), dtype=bool)
        self.asym_id = np.asarray(
            self.feats.get("asym_id", np.ones_like(self.fixed_tokens)), dtype=int)
        self.is_ca = np.asarray(self.feats["is_ca"], dtype=bool)
        self.restype = np.asarray(self.feats["restype"]).argmax(-1)
        self.residue_index = np.asarray(self.feats["residue_index"], dtype=int)
        self.rasa = np.asarray(self.feats["ref_atomwise_rasa"], dtype=int)
        self.n_tokens = self.fixed_tokens.size
        self.n_atoms = self.tok.size
        self.design_tokens = np.where(self.protein_mask & ~self.fixed_tokens & ~self.unindexed_mask)[0]
        self.unindexed_tokens = np.where(self.unindexed_mask)[0]
        self.motif_tokens = np.where(self.fixed_tokens)[0]
        self.ligand_code = ligand_code
        self.motif_source_residues = motif_source_residues
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
        self.target_protein_tokens = np.where(
            self.protein_mask & self.fixed_tokens & ~self.unindexed_mask)[0]
        self.ligand_tokens = np.where(self.ligand_mask)[0]
        partial = self.feats.get("partial_t")
        self.is_partial = partial is not None and np.isfinite(np.asarray(partial, dtype=float)).any()
        if len(self.design_tokens) == 0:
            raise ValueError("Fixture has no diffused design tokens")

    def _unindexed_assignments(self, coords: np.ndarray) -> tuple[dict[int, int], dict]:
        if not self.unindexed_tokens.size:
            return {}, {"diffused_index_map": {}, "motif_insertion_rmsd": None,
                        "fixed_residues": ""}
        remaining = set(map(int, self.design_tokens))
        assignments: dict[int, int] = {}
        rmsds: dict[str, float] = {}
        for guide in self.unindexed_tokens:
            guide_atoms = np.where((self.tok == guide) & self.fixed_atoms)[0]
            if not guide_atoms.size:
                raise ValueError(f"unindexed motif token {guide} has no explicitly fixed atom")
            best = None
            for candidate in sorted(remaining):
                candidate_atoms = {self.names[a]: a for a in np.where(self.tok == candidate)[0]}
                pairs = [(ga, candidate_atoms[self.names[ga]]) for ga in guide_atoms
                         if self.names[ga] in candidate_atoms]
                if not pairs:
                    continue
                delta = np.asarray([coords[ca] - coords[ga] for ga, ca in pairs])
                rmsd = float(np.sqrt((delta * delta).sum(-1).mean()))
                if best is None or rmsd < best[0]:
                    best = (rmsd, candidate)
            if best is None:
                raise ValueError(f"could not map unindexed motif token {guide} onto the scaffold")
            rmsd, candidate = best
            assignments[int(guide)] = int(candidate)
            remaining.remove(int(candidate))
            label = (self.motif_source_residues[len(rmsds)]
                     if len(rmsds) < len(self.motif_source_residues) else f"motif_{int(guide)}")
            rmsds[label] = rmsd
        design_num = {int(token): i + 1 for i, token in enumerate(self.design_tokens)}
        guide_order = list(map(int, self.unindexed_tokens))
        mapping = {source: f"A{design_num[assignments[guide_order[i]]]}"
                   for i, source in enumerate(rmsds)}
        return assignments, {
            "diffused_index_map": mapping,
            "motif_insertion_rmsd": float(np.mean(list(rmsds.values()))),
            "motif_insertion_rmsd_by_token": rmsds,
            "fixed_residues": " ".join(sorted(mapping.values(), key=lambda x: int(x[1:]))),
        }

    def write_pdb(self, coords: np.ndarray, path: Path) -> dict:
        motif_map, motif_meta = self._unindexed_assignments(coords)
        motif_by_design = {design: guide for guide, design in motif_map.items()}
        target_asym = sorted({int(self.asym_id[t]) for t in self.target_protein_tokens})
        target_chain = {asym: chr(ord("B") + i) for i, asym in enumerate(target_asym)}
        per_asym = {asym: 0 for asym in target_asym}
        target_num = {}
        for token in self.target_protein_tokens:
            asym = int(self.asym_id[token]); per_asym[asym] += 1
            target_num[int(token)] = per_asym[asym]
        ligand_num = {t: 1 for t in self.ligand_tokens}
        design_num = {t: i + 1 for i, t in enumerate(self.design_tokens)}
        lines: list[str] = []
        serial = 1
        for atom_idx, (token, name) in enumerate(zip(self.tok, self.names, strict=True)):
            x, y, z = coords[atom_idx]
            if token in design_num:
                guide = motif_by_design.get(int(token))
                guide_atoms = ({self.names[a]: a for a in np.where((self.tok == guide) & self.fixed_atoms)[0]}
                               if guide is not None else {})
                if name in guide_atoms and name in REAL_PROTEIN_ATOMS:
                    x, y, z = coords[guide_atoms[name]]
                elif name not in BINDER_ATOMS:
                    continue
                ri = int(self.restype[guide if guide is not None else token])
                resname = (AA3[ri] if (self.is_partial or guide is not None)
                           and 0 <= ri < len(AA3) else "ALA")
                record, chain, resnum = "ATOM  ", "A", design_num[token]
            elif token in target_num:
                if name not in REAL_PROTEIN_ATOMS:
                    continue
                ri = int(self.restype[token])
                record, chain, resnum = ("ATOM  ", target_chain[int(self.asym_id[token])],
                                          target_num[token])
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
        return motif_meta

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


def output_geometry_failures(path: Path) -> list[str]:
    """Catch broken joins and leaked virtual atoms before downstream design."""
    residues: dict[tuple[str, int], dict[str, np.ndarray]] = {}
    order: list[tuple[str, int]] = []
    failures: list[str] = []
    for line in path.read_text().splitlines():
        if not line.startswith("ATOM  ") or len(line) < 54:
            continue
        atom = line[12:16].strip().upper()
        chain = line[21].strip()
        residue = int(line[22:26])
        key = (chain, residue)
        if key not in residues:
            residues[key] = {}; order.append(key)
        xyz = np.array([float(line[30:38]), float(line[38:46]), float(line[46:54])])
        residues[key][atom] = xyz
        if atom.startswith("V"):
            failures.append(f"{chain}{residue} contains virtual atom {atom}")
    binder = [(key, residues[key]) for key in order if key[0] == "A" and "CA" in residues[key]]
    for (left_key, left), (right_key, right) in zip(binder, binder[1:]):
        ca_distance = float(np.linalg.norm(left["CA"] - right["CA"]))
        if not 2.5 <= ca_distance <= 4.5:
            failures.append(
                f"A{left_key[1]}-A{right_key[1]} CA-CA={ca_distance:.2f} A"
            )
        if "C" in left and "N" in right:
            peptide = float(np.linalg.norm(left["C"] - right["N"]))
            if not 0.9 <= peptide <= 2.2:
                failures.append(
                    f"A{left_key[1]}-A{right_key[1]} C-N={peptide:.2f} A"
                )
    for (chain, residue), atoms in binder:
        if "CA" not in atoms:
            continue
        for atom, xyz in atoms.items():
            if atom not in BINDER_ATOMS and np.linalg.norm(xyz - atoms["CA"]) < 0.5:
                failures.append(f"{chain}{residue} atom {atom} overlaps CA")
    return failures


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
    parser.add_argument("--motif-residues", default="")
    parser.add_argument("--cache-limit-gb", type=float, default=4.0)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--max-attempts-per-design", type=int, default=10)
    args = parser.parse_args()
    if (args.num_designs < 1 or args.batch_size < 1 or args.steps < 2
            or args.max_attempts_per_design < 1):
        raise SystemExit("--num-designs/--batch-size must be >=1 and --steps >=2")

    mx.set_default_device(mx.gpu)
    try:
        mx.set_cache_limit(int(args.cache_limit_gb * 1024**3))
    except Exception:
        pass

    motif_residues = [item.strip() for item in args.motif_residues.split(",") if item.strip()]
    fixture = Fixture(args.fixture.resolve(), args.ligand_code, motif_residues)
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

    rejected_path = output / "rejected_samples.csv"
    rejected: list[dict] = []
    accepted_rows: list[dict] = []
    if not args.overwrite:
        if rejected_path.exists():
            rejected = list(csv.DictReader(rejected_path.open()))
        # Only a contiguous prefix is resumable. A gap means outputs were
        # manually edited and silently renumbering later designs would destroy
        # provenance.
        index = 1
        while index <= args.num_designs:
            result = result_dir / f"design_{index:04d}.json"
            pdb = backbone_dir / f"design_{index:04d}.pdb"
            if not result.exists() and not pdb.exists():
                break
            if not result.is_file() or not pdb.is_file():
                raise RuntimeError(
                    f"Incomplete cached design {index}: expected both {result} and {pdb}"
                )
            accepted_rows.append(json.loads(result.read_text()))
            index += 1
        later = sorted(result_dir.glob("design_*.json"))[len(accepted_rows):]
        if later:
            raise RuntimeError(
                "Cached design numbering has a gap; refusing to renumber or overwrite it: "
                + ", ".join(path.name for path in later[:5])
            )

    design_index = len(accepted_rows)
    used_seeds = [int(row["sample_seed"]) for row in accepted_rows if row.get("sample_seed") is not None]
    used_seeds += [int(row["seed"]) for row in rejected if row.get("seed") not in (None, "")]
    attempted = max((seed - args.seed_start + 1 for seed in used_seeds), default=0)
    if design_index:
        print(f"resuming after {design_index} accepted and {len(rejected)} rejected sample(s)",
              flush=True)
    maximum_attempts = args.num_designs * args.max_attempts_per_design
    while design_index < args.num_designs:
        if attempted >= maximum_attempts:
            raise RuntimeError(
                f"Only produced {design_index}/{args.num_designs} valid backbones after "
                f"{attempted} attempts. See rejected_samples.csv."
            )
        width = min(args.batch_size, args.num_designs - design_index,
                    maximum_attempts - attempted)
        seed = args.seed_start + attempted
        sampler = Sampler(
            weights,
            num_timesteps=args.steps,
            n_recycle=args.recycle,
            seed=seed,
        )
        begin = time.time()
        prediction = sampler.generate(
            fixture.feats,
            D=width,
            coord_to_be_noised=fixture.coord,
        )
        mx.eval(prediction["X_L"], prediction["sequence_indices_I"])
        wall = time.time() - begin
        coords = np.asarray(prediction["X_L"])
        accepted_this_batch = 0
        for offset in range(width):
            candidate = backbone_dir / f".candidate_seed_{seed + offset}.pdb"
            motif_meta = fixture.write_pdb(coords[offset], candidate)
            failures = output_geometry_failures(candidate)
            if failures:
                candidate.unlink(missing_ok=True)
                rejected.append({
                    "seed": seed + offset,
                    "attempt": attempted + offset + 1,
                    "failures": "; ".join(failures),
                    **motif_meta,
                })
                continue
            name = f"design_{design_index + 1:04d}"
            pdb_path = backbone_dir / f"{name}.pdb"
            candidate.replace(pdb_path)
            row = {
                "design": name,
                "design_index": design_index + 1,
                "batch_index": attempted // args.batch_size,
                "batch_seed": seed,
                "sample_seed": seed + offset,
                "batch_size_actual": width,
                "batch_wall_sec": wall,
                "sec_per_design": wall / width,
                "steps": args.steps,
                "recycle": args.recycle,
                "precision": args.precision,
                "backbone_pdb": str(pdb_path),
                **motif_meta,
                **fixture.metrics(coords[offset]),
            }
            (result_dir / f"{name}.json").write_text(json.dumps(row, indent=2) + "\n")
            design_index += 1
            accepted_this_batch += 1
        print(
            f"batch {attempted // args.batch_size:04d}: accepted {accepted_this_batch}/{width}, "
            f"{wall:.2f}s ({wall / width:.2f}s/attempt)",
            flush=True,
        )
        attempted += width
        # Rejection history is part of the resume cursor, not a final report.
        # Persist it after every batch so a crash cannot recycle an old seed.
        write_csv(rejected, rejected_path)

    rows = [json.loads(path.read_text()) for path in
            sorted(result_dir.glob("design_*.json"))[:args.num_designs]]
    write_csv(rows, output / "backbone_metrics.csv")
    write_csv(rejected, rejected_path)
    print(f"wrote {len(rows)} designs -> {output}")


if __name__ == "__main__":
    main()
