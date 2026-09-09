"""Helpers for the experimental NISE (Neural Iterative Selection-Expansion)
small-molecule binder design protocol.

This module is intentionally standalone from ``nanohunter_run.sh``: it wraps the
same installed venvs (Boltz, LASErMPNN, LigandMPNN) as subprocesses but owns its
own prediction/design/metric logic so the experimental protocol cannot pollute
the production runner.

Method reference: Fry, Slaw & Polizzi, "Zero-shot design of drug-binding
proteins via neural iterative selection-expansion", Nature 2026.
"""

from __future__ import annotations

import os
import re
import json
import glob
import shutil
import subprocess
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

import numpy as np

REPO_ROOT = Path(os.environ["NANOHUNTER_ROOT"]).expanduser().resolve()
VENV_PREFIX = os.environ.get("NANOHUNTER_VENV_PREFIX", "NanoHunter")
BOLTZ_VENV = REPO_ROOT / "venvs" / f"{VENV_PREFIX}_boltz"
LASERMPNN_VENV = REPO_ROOT / "venvs" / f"{VENV_PREFIX}_lasermpnn"
LIGANDMPNN_VENV = REPO_ROOT / "venvs" / f"{VENV_PREFIX}_ligandmpnn"
LASERMPNN_REPO = REPO_ROOT / "src" / "LASErMPNN"
LASERMPNN_WEIGHTS = LASERMPNN_REPO / "model_weights" / "laser_weights_0p1A_nothing_heldout.pt"
LIGANDMPNN_REPO = REPO_ROOT / "src" / "LigandMPNN"
LIGANDMPNN_CHECKPOINT = LIGANDMPNN_REPO / "model_params" / "ligandmpnn_v_32_010_25.pt"
PREPARE_HELPER = Path(__file__).resolve().parent.parent / "lasermpnn_prepare_input.py"

AA20 = "ACDEFGHIKLMNPQRSTVWY"

# ---------------------------------------------------------------------------
# subprocess helper
# ---------------------------------------------------------------------------


def run(cmd, cwd=None, env=None, log_path=None, check=True):
    """Run a subprocess, teeing combined output to log_path. Returns the CompletedProcess."""
    merged_env = dict(os.environ)
    if env:
        merged_env.update(env)
    proc = subprocess.run(
        [str(c) for c in cmd],
        cwd=str(cwd) if cwd else None,
        env=merged_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if log_path is not None:
        header = "$ " + " ".join(str(c) for c in cmd) + "\n"
        Path(log_path).write_text(header + (proc.stdout or ""))
    if check and proc.returncode != 0:
        tail = "\n".join((proc.stdout or "").splitlines()[-40:])
        raise RuntimeError(f"Command failed ({proc.returncode}): {' '.join(map(str, cmd))}\n{tail}")
    return proc


# ---------------------------------------------------------------------------
# lightweight PDB parsing (avoids heavy deps in the orchestrator core)
# ---------------------------------------------------------------------------


def _iter_pdb_atoms(pdb_path):
    for ln in Path(pdb_path).read_text().splitlines():
        if ln.startswith(("ATOM", "HETATM")):
            yield ln


def _element(ln):
    el = ln[76:78].strip()
    if not el:
        # fall back to atom name
        el = ln[12:16].strip().lstrip("0123456789")[:1]
    return el


def ca_coords_chain(pdb_path, chain):
    """Ordered CA coordinates for a protein chain."""
    coords = []
    for ln in _iter_pdb_atoms(pdb_path):
        if ln[21] == chain and ln[12:16].strip() == "CA":
            coords.append([float(ln[30:38]), float(ln[38:46]), float(ln[46:54])])
    return np.array(coords, dtype=float)


def ligand_heavy_coords(pdb_path, chain):
    """Ordered heavy-atom coordinates for the ligand chain (H excluded)."""
    coords = []
    for ln in _iter_pdb_atoms(pdb_path):
        if ln[21] == chain and _element(ln) != "H":
            coords.append([float(ln[30:38]), float(ln[38:46]), float(ln[46:54])])
    return np.array(coords, dtype=float)


def ligand_bfactors(pdb_path, chain):
    """Per-atom B-factors for the ligand chain (Boltz stores pLDDT*100 here)."""
    vals = []
    for ln in _iter_pdb_atoms(pdb_path):
        if ln[21] == chain:
            try:
                vals.append(float(ln[60:66]))
            except ValueError:
                pass
    return np.array(vals, dtype=float)


# ---------------------------------------------------------------------------
# RMSD / self-consistency
# ---------------------------------------------------------------------------


def _kabsch(P, Q):
    """Return RMSD of P onto Q and the (R, t) that maps P -> Q frame."""
    Pc = P - P.mean(0)
    Qc = Q - Q.mean(0)
    H = Pc.T @ Qc
    U, _, Vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    D = np.diag([1.0, 1.0, d])
    R = Vt.T @ D @ U.T
    Pr = (R @ Pc.T).T
    rmsd = float(np.sqrt(((Pr - Qc) ** 2).sum(1).mean()))
    return rmsd, R, P.mean(0), Q.mean(0)


@dataclass
class SelfConsistency:
    ca_rmsd: float
    ligand_rmsd: float
    ok: bool


def self_consistency(pred_pdb, ref_pdb, chain_protein="A", chain_ligand="B",
                     ca_thresh=2.5, lig_thresh=2.5):
    """Superpose predicted protein CA onto the reference, then measure ligand
    heavy-atom RMSD in the same frame. Returns SelfConsistency."""
    def ligand_identity(path):
        return [(line[12:16].strip(), _element(line)) for line in _iter_pdb_atoms(path)
                if line[21] == chain_ligand and _element(line) != "H"]
    pkeys, qkeys = ligand_identity(pred_pdb), ligand_identity(ref_pdb)
    if len(set(pkeys)) != len(pkeys) or len(set(qkeys)) != len(qkeys) or set(pkeys) != set(qkeys):
        raise ValueError("Ligand atom correspondence changed; refusing an array-order RMSD")
    Pca = ca_coords_chain(pred_pdb, chain_protein)
    Qca = ca_coords_chain(ref_pdb, chain_protein)
    Plig = ligand_heavy_coords(pred_pdb, chain_ligand)
    Qlig = ligand_heavy_coords(ref_pdb, chain_ligand)
    Qlig = Qlig[[qkeys.index(key) for key in pkeys]]
    if len(Pca) != len(Qca) or len(Pca) < 3:
        raise ValueError(f"CA count mismatch: pred={len(Pca)} ref={len(Qca)}")
    if len(Plig) != len(Qlig) or len(Plig) == 0:
        raise ValueError(f"Ligand atom count mismatch: pred={len(Plig)} ref={len(Qlig)}")
    ca_rmsd, R, Pmean, Qmean = _kabsch(Pca, Qca)
    # Apply the same rigid transform to the predicted ligand and compare.
    Plig_aligned = (R @ (Plig - Pmean).T).T + Qmean
    lig_rmsd = float(np.sqrt(((Plig_aligned - Qlig) ** 2).sum(1).mean()))
    ok = (ca_rmsd < ca_thresh) and (lig_rmsd < lig_thresh)
    return SelfConsistency(ca_rmsd=ca_rmsd, ligand_rmsd=lig_rmsd, ok=ok)


# ---------------------------------------------------------------------------
# UNK patching (hallucinated X-seed structures)
# ---------------------------------------------------------------------------


def patch_unk_pdb(in_pdb, out_pdb):
    """Rewrite UNK residue names to ALA so ProDy/RDKit treat them as protein.
    Only backbone atoms are typically present for UNK; that is fine for
    inverse folding which designs from the backbone."""
    text = Path(in_pdb).read_text()
    text = re.sub(r"(?<=\W)UNK(?=\W)", "ALA", text)
    Path(out_pdb).write_text(text)
    return out_pdb


# ---------------------------------------------------------------------------
# hallucination: random X-seeded binder sequences
# ---------------------------------------------------------------------------


def generate_random_binder(rng, min_len=65, max_len=150, percent_x=50, no_cys=True):
    """Generate a random binder sequence with a fraction of positions emitted as
    X, matching NanoHunter's random-binder hallucination seed."""
    length = int(rng.integers(min_len, max_len + 1))
    alphabet = [a for a in AA20 if not (no_cys and a == "C")]
    seq = [rng.choice(alphabet) for _ in range(length)]
    n_x = int(round(length * percent_x / 100.0))
    x_positions = rng.choice(length, size=n_x, replace=False)
    for i in x_positions:
        seq[i] = "X"
    return "".join(seq)


# ---------------------------------------------------------------------------
# Boltz prediction (with affinity for P(bind))
# ---------------------------------------------------------------------------


def ligand_contact_atoms(smiles, k=5, affinity=True):
    """Return k ligand heavy-atom names (Boltz naming) that span the molecule's
    long axis — good pocket contacts to make the protein enclose the ligand.

    Uses the Boltz venv to reproduce Boltz's exact atom naming.
    """
    if not affinity:
        raise ValueError("Studio ligand NISE requires Boltz affinity atom naming.")
    from ligand_atoms import resolve, contact_atoms
    return contact_atoms(resolve(smiles), k)


def write_boltz_yaml(path, sequence, smiles, affinity=True, binder_chain="B", pocket=None):
    """Write a Boltz YAML (protein A + ligand B, empty MSA).

    pocket: optional dict emitting a Boltz `pocket` constraint that biases the
    ligand (binder chain "B") to sit in a pocket formed by protein residues.
    Boltz indexes ligand tokens by atom name (fragile) but polymer tokens by
    residue index, so we use binder="B" (ligand) with protein-A residue contacts.

    Provide either explicit ``contacts`` ([[chain, resid], ...]) or
    ``n_center_contacts`` (K central protein residues, computed from the protein
    length here so it is valid for any binder size). ``max_distance``/``force``
    optional.
    """
    lines = [
        "sequences:",
        "  - protein:",
        "      id: A",
        f"      sequence: {sequence}",
        "      msa: empty",
        "  - ligand:",
        "      id: B",
        f"      smiles: {json.dumps(smiles)}",
    ]
    if pocket:
        contacts = pocket.get("contacts")
        if contacts is None and pocket.get("n_center_contacts"):
            # K protein residues spread across the central 50% of the chain
            L = len(sequence)
            k = max(1, int(pocket["n_center_contacts"]))
            lo, hi = max(1, L // 4), max(1, (3 * L) // 4)
            if k == 1:
                idxs = [max(1, L // 2)]
            else:
                idxs = sorted({int(round(lo + (hi - lo) * i / (k - 1))) for i in range(k)})
            contacts = [["A", r] for r in idxs]
        contacts_str = ", ".join(f"[{c[0]}, {c[1]}]" for c in contacts)
        lines += [
            "constraints:",
            "  - pocket:",
            f"      binder: {pocket.get('binder', 'B')}",
            f"      contacts: [{contacts_str}]",
            f"      max_distance: {pocket.get('max_distance', 6.0)}",
            f"      force: {str(pocket.get('force', True)).lower()}",
        ]
    if affinity:
        lines += ["properties:", "  - affinity:", f"      binder: {binder_chain}"]
    lines += ["version: 1", ""]
    Path(path).write_text("\n".join(lines))
    return path


@dataclass
class Prediction:
    name: str
    pdb: str
    complex_plddt: float = float("nan")
    iptm: float = float("nan")
    ligand_iptm: float = float("nan")
    ligand_plddt: float = float("nan")  # 0-100 scale (mean ligand B-factor)
    pbind: Optional[float] = None       # affinity_probability_binary (0-1)


def _find_pred_dir(out_dir, stem):
    hits = glob.glob(os.path.join(out_dir, "**", "predictions", stem), recursive=True)
    return hits[0] if hits else None


def parse_prediction(out_dir, stem):
    pred_dir = _find_pred_dir(out_dir, stem)
    if pred_dir is None:
        return None
    pdbs = glob.glob(os.path.join(pred_dir, f"{stem}_model_0.pdb"))
    if not pdbs:
        return None
    pdb = pdbs[0]
    p = Prediction(name=stem, pdb=pdb)
    conf = os.path.join(pred_dir, f"confidence_{stem}_model_0.json")
    if os.path.exists(conf):
        d = json.load(open(conf))
        p.complex_plddt = float(d.get("complex_plddt", float("nan")))
        p.iptm = float(d.get("iptm", float("nan")))
        p.ligand_iptm = float(d.get("ligand_iptm", float("nan")))
    aff = os.path.join(pred_dir, f"affinity_{stem}.json")
    if os.path.exists(aff):
        a = json.load(open(aff))
        if "affinity_probability_binary" in a:
            p.pbind = float(a["affinity_probability_binary"])
    bvals = ligand_bfactors(pdb, "B")
    if len(bvals):
        p.ligand_plddt = float(bvals.mean())
    return p


def _boltz_cmd(yaml_dir, out_dir, recycling, sampling_steps, extra, use_potentials=False):
    cmd = [
        BOLTZ_VENV / "bin" / "boltz", "predict", yaml_dir,
        "--out_dir", out_dir,
        "--output_format", "pdb",
        "--num_workers", "0",
        "--override",
    ]
    if use_potentials:
        cmd += ["--use_potentials"]
    if recycling is not None:
        cmd += ["--recycling_steps", str(recycling)]
    if sampling_steps is not None:
        cmd += ["--sampling_steps", str(sampling_steps)]
    if extra:
        cmd += list(extra)
    return cmd


def _run_parallel(cmds_and_logs):
    """Launch (cmd, log_path) pairs concurrently and wait for all. Raises if any fails."""
    procs = []
    for cmd, log_path in cmds_and_logs:
        fh = open(log_path, "w")
        fh.write("$ " + " ".join(str(c) for c in cmd) + "\n")
        fh.flush()
        p = subprocess.Popen([str(c) for c in cmd], stdout=fh, stderr=subprocess.STDOUT,
                             env=dict(os.environ))
        procs.append((p, fh, cmd, log_path))
    failures = []
    for p, fh, cmd, log_path in procs:
        rc = p.wait()
        fh.close()
        if rc != 0:
            tail = "\n".join(Path(log_path).read_text().splitlines()[-30:])
            failures.append(f"rc={rc}: {' '.join(map(str, cmd))}\n{tail}")
    if failures:
        raise RuntimeError("Boltz shard(s) failed:\n" + "\n---\n".join(failures))


def parse_existing_batch(work_dir, names):
    """Parse already-computed Boltz predictions for `names` under work_dir.

    Used on resume: a fold step whose structures exist on disk is scored without
    re-running Boltz. Searches every shard's out/ dir. Returns {name: Prediction}.
    """
    work_dir = Path(work_dir).resolve()
    out_dirs = sorted(set(p.parent for p in work_dir.glob("**/predictions")))
    results = {}
    for name in names:
        for od in out_dirs:
            pred = parse_prediction(od, name)
            if pred is not None:
                results[name] = pred
                break
    return results


def boltz_predict_batch(seq_by_name, smiles, work_dir, affinity=True,
                        recycling=None, sampling_steps=None, extra=None, parallel=1,
                        use_potentials=False, pocket=None):
    """Predict a batch of sequences with Boltz.

    seq_by_name: dict {name -> sequence}. Returns dict {name -> Prediction}.

    use_potentials: pass Boltz --use_potentials (inference steering) to every shard.
    pocket: optional pocket-constraint dict applied to every YAML in this batch
            (used to shape Phase-0 backbones; omitted for the NISE trajectory).

    parallel>1 shards the sequences round-robin into that many concurrent Boltz
    processes (each loads the model once). On Apple Silicon each MPS process uses
    ~5 GB, so keep parallel <= 4 and mind total memory.
    """
    work_dir = Path(work_dir).resolve()
    names = list(seq_by_name)
    n_shards = max(1, min(parallel, len(names)))

    shards = [[] for _ in range(n_shards)]
    for i, name in enumerate(names):
        shards[i % n_shards].append(name)

    cmds_and_logs = []
    shard_out_dirs = []
    for si, shard in enumerate(shards):
        if not shard:
            continue
        sdir = work_dir / (f"shard{si}" if n_shards > 1 else ".")
        yaml_dir = sdir / "yaml"
        out_dir = sdir / "out"
        yaml_dir.mkdir(parents=True, exist_ok=True)
        out_dir.mkdir(parents=True, exist_ok=True)
        for name in shard:
            write_boltz_yaml(yaml_dir / f"{name}.yaml", seq_by_name[name], smiles,
                             affinity=affinity, pocket=pocket)
        cmd = _boltz_cmd(yaml_dir, out_dir, recycling, sampling_steps, extra,
                         use_potentials=use_potentials)
        cmds_and_logs.append((cmd, sdir / "boltz.log"))
        shard_out_dirs.append((out_dir, shard))

    if n_shards == 1:
        cmd, log_path = cmds_and_logs[0]
        run(cmd, log_path=log_path)
    else:
        _run_parallel(cmds_and_logs)

    results = {}
    for out_dir, shard in shard_out_dirs:
        for name in shard:
            pred = parse_prediction(out_dir, name)
            if pred is not None:
                results[name] = pred
    return results


# ---------------------------------------------------------------------------
# ranking metric
# ---------------------------------------------------------------------------


def rank_score(pred: Prediction, mode="auto"):
    """Required ligand pLDDT/100 + P(bind), with finite values in range.

    The legacy 'auto' spelling remains an alias, but missing affinity is an
    error. Studio never substitutes a weaker score for the requested objective.
    """
    import math
    if mode not in ("auto", "ligand_plddt+pbind"):
        raise ValueError("Studio ligand NISE requires ligand pLDDT + P(bind)")
    if not math.isfinite(pred.ligand_plddt) or not 0 <= pred.ligand_plddt <= 100:
        raise ValueError(f"Invalid ligand pLDDT for {pred.name}")
    if pred.pbind is None or not math.isfinite(pred.pbind) or not 0 <= pred.pbind <= 1:
        raise ValueError(f"Missing or invalid affinity probability for {pred.name}")
    return pred.ligand_plddt / 100.0 + pred.pbind


# ---------------------------------------------------------------------------
# sequence design (LASErMPNN / LigandMPNN)
# ---------------------------------------------------------------------------


def _prepare_lasermpnn_input(struct_pdb, out_pdb, smiles, designed="all", log_path=None):
    cmd = [
        LASERMPNN_VENV / "bin" / "python", PREPARE_HELPER,
        "--in-pdb", struct_pdb, "--out-pdb", out_pdb,
        "--smiles", smiles, "--designed-positions", designed,
    ]
    run(cmd, log_path=log_path)
    return out_pdb


def _read_lasermpnn_fasta(fasta_path):
    """Return list of (sequence, score) for chain-A designs."""
    out = []
    header, seq = None, []
    for ln in Path(fasta_path).read_text().splitlines():
        if ln.startswith(">"):
            if header is not None and seq:
                m = re.search(r"score=(-?\d+(?:\.\d+)?)", header)
                out.append(("".join(seq), float(m.group(1)) if m else float("-inf")))
            header, seq = ln, []
        elif ln.strip():
            seq.append(ln.strip())
    if header is not None and seq:
        m = re.search(r"score=(-?\d+(?:\.\d+)?)", header)
        out.append(("".join(seq), float(m.group(1)) if m else float("-inf")))
    return out


def lasermpnn_design(struct_pdb, out_dir, n_designs, smiles,
                     seq_temp=0.5, fs_temp=0.7, fs_distance=10.0,
                     ala_budget=2, gly_budget=0, constrain_ss=True,
                     designed="all", device="cpu", seed=0):
    """Design n_designs sequences from a backbone+ligand structure with LASErMPNN.

    - seq_temp: general sampling temperature.
    - fs_temp: first-shell (binding-site) temperature; first shell = CA within
      fs_distance of a ligand heavy atom.
    - ala_budget/gly_budget with constrain_ss: cap Ala/Gly at surface residues in
      secondary structure (DSSP H/E), matching the NISE composition constraint.

    `seed` is accepted only so this matches ligandmpnn_design's signature and
    callers can pass one uniformly. IT HAS NO EFFECT: LASErMPNN's
    run_batch_inference exposes no seed/RNG argument at all, so its designs are
    NOT reproducible run-to-run. Do not describe a LASErMPNN NISE campaign as
    seed-reproducible on the inverse-folding step — only the folding side and the
    recorded sequences are replayable (via --resume, which reads sequences back
    from disk rather than re-sampling). Making this reproducible needs an upstream
    change to LASErMPNN.

    Returns list of (sequence, laser_score) sorted best-first.
    """
    del seed  # documented no-op; see above
    out_dir = Path(out_dir).resolve()
    struct_pdb = str(Path(struct_pdb).resolve())
    out_dir.mkdir(parents=True, exist_ok=True)
    prepared = out_dir / "prepared.pdb"
    _prepare_lasermpnn_input(struct_pdb, prepared, smiles, designed=designed,
                             log_path=out_dir / "prepare.log")
    designs_dir = out_dir / "designs"
    designs_dir.mkdir(exist_ok=True)
    cmd = [
        LASERMPNN_VENV / "bin" / "python", "-m", "LASErMPNN.run_batch_inference",
        prepared, designs_dir, str(n_designs),
        "--device", device,
        "--model_weights_path", LASERMPNN_WEIGHTS,
        "--sequence_temp", str(seq_temp),
        "--first_shell_sequence_temp", str(fs_temp),
        "--fs_calc_ca_distance", str(fs_distance),
        "--disabled_residues", "X,C",
        "--output_fasta_only", "--silent",
    ]
    if constrain_ss:
        cmd += ["-c", "--ala_budget", str(ala_budget), "--gly_budget", str(gly_budget)]
    env = {"KMP_USE_SHM": "0", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
    run(cmd, cwd=LASERMPNN_REPO.parent, env=env, log_path=out_dir / "lasermpnn.log")
    fasta = designs_dir / "designs.fasta"
    if not fasta.exists():
        raise RuntimeError(f"LASErMPNN produced no designs.fasta in {designs_dir}")
    pairs = _read_lasermpnn_fasta(fasta)
    pairs.sort(key=lambda x: x[1], reverse=True)
    return pairs


def ligandmpnn_design(struct_pdb, out_dir, n_designs, smiles=None,
                      temperature=0.5, seed=0, omit_aa="C", bias_aa=None):
    """Design n_designs sequences from a backbone+ligand structure with LigandMPNN.

    LigandMPNN reads the ligand directly from the PDB HETATM records and does not
    require ligand protonation. Binding-site temperature and Ala/Gly surface
    budgets are LASErMPNN-specific and are not applied here (bias_AA can softly
    disfavour residues). Returns list of (sequence, None) (LigandMPNN score not
    parsed) sorted arbitrarily.
    """
    out_dir = Path(out_dir).resolve()
    struct_pdb = str(Path(struct_pdb).resolve())
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        LIGANDMPNN_VENV / "bin" / "python", "run.py",
        "--model_type", "ligand_mpnn",
        "--checkpoint_ligand_mpnn", LIGANDMPNN_CHECKPOINT,
        "--pdb_path", struct_pdb,
        "--out_folder", out_dir,
        "--temperature", str(temperature),
        "--seed", str(seed),
        "--number_of_batches", str(n_designs),
        "--omit_AA", omit_aa,
    ]
    if bias_aa:
        cmd += ["--bias_AA", bias_aa]
    env = {"KMP_USE_SHM": "0", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
    run(cmd, cwd=LIGANDMPNN_REPO, env=env, log_path=out_dir / "ligandmpnn.log")
    seqs = []
    for fa in glob.glob(str(out_dir / "seqs" / "*.fa")):
        cur = []
        recs = []
        for ln in Path(fa).read_text().splitlines():
            s = ln.strip()
            if not s:
                continue
            if s.startswith(">"):
                if cur:
                    recs.append("".join(cur)); cur = []
            else:
                cur.append(s)
        if cur:
            recs.append("".join(cur))
        # record 0 is the input sequence; the rest are designs
        for r in recs[1:]:
            seqs.append((r.split(":", 1)[0] if ":" in r else r, None))
    return seqs


# ---------------------------------------------------------------------------
# optional FreeSASA filters
# ---------------------------------------------------------------------------


def ligand_sasa(pdb_path, chain="B"):
    """Total SASA of the ligand chain, via freesasa. Returns None if unavailable."""
    try:
        import freesasa
        freesasa.setVerbosity(freesasa.silent)
    except Exception:
        return None
    try:
        structure = freesasa.Structure(pdb_path, options={"hetatm": True})
        result = freesasa.calc(structure)
        total = 0.0
        for i in range(structure.nAtoms()):
            if structure.chainLabel(i) == chain:
                total += result.atomArea(i)
        return float(total)
    except Exception:
        return None
