#!/usr/bin/env python
"""Ported small-molecule Neural Iterative Selection-Expansion search.

The original source revision and hash are recorded in UPSTREAM.json. Studio
supplies managed model execution and atomic operation receipts through Backend;
use campaign.py via the typed plan/job bridge to execute a saved request.
"""

from __future__ import annotations

import re
import sys
import csv
import json
import argparse
import copy
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass, asdict
from typing import Optional

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nise_lib as L


def log(msg):
    print(f"[nise] {msg}", flush=True)


def extract_ligand_smiles(template_yaml):
    import yaml
    document = yaml.safe_load(Path(template_yaml).read_text())
    ligands = [entry["ligand"] for entry in document.get("sequences", []) if "ligand" in entry]
    if len(ligands) != 1:
        raise ValueError("NISE requires exactly one ligand")
    return ligands[0].get("smiles")


@dataclass
class Node:
    name: str
    sequence: str
    pdb: str                 # this design's predicted structure
    ref_pdb: str             # structure it was designed from (self-consistency ref)
    ca_rmsd: float
    ligand_rmsd: float
    ligand_plddt: float
    pbind: Optional[float]
    score: Optional[float]
    cycle: int
    traj: int = -1          # independent-trajectory id this design belongs to
    origin: str = ""        # originating hallucinated start
    score_status: str = "scored"
    geometry_passed: bool = True
    branch: str = "mpnn"


def design_sequences(designer, struct_pdb, out_dir, n, smiles, args,
                     seq_temp, fs_temp, seed, designed="all", constrain_ss=True):
    if args.backend is not None:
        return args.backend.design(struct_pdb, out_dir, n, smiles, args, seq_temp, fs_temp, seed, designed, constrain_ss)
    if designer == "lasermpnn":
        pairs = L.lasermpnn_design(
            struct_pdb, out_dir, n, smiles,
            seq_temp=seq_temp, fs_temp=fs_temp, fs_distance=args.fs_distance,
            ala_budget=args.ala_budget, gly_budget=args.gly_budget,
            constrain_ss=constrain_ss, designed=designed, device=args.device, seed=seed,
        )
        return [s for s, _ in pairs]
    else:
        pairs = L.ligandmpnn_design(
            struct_pdb, out_dir, n, smiles=smiles, temperature=seq_temp, seed=seed,
        )
        return [s for s, _ in pairs]


def fold_and_score(seq_by_name, smiles, work_dir, args, pocket=None):
    if args.backend is not None:
        if getattr(args, "selective_affinity", False):
            args = copy.copy(args)
            args.boltz_phase = "structure"
        return args.backend.fold(seq_by_name, smiles, work_dir, args, pocket)
    preds = L.boltz_predict_batch(
        seq_by_name, smiles, work_dir, affinity=args.affinity,
        recycling=args.recycling, sampling_steps=args.sampling_steps,
        parallel=args.boltz_parallel, use_potentials=args.use_potentials, pocket=pocket,
    )
    return preds


def evaluate_candidates(preds, seq_by_name, ref_by_name, args, cycle, ca_thresh, lig_thresh):
    """Turn predictions into self-consistent Nodes."""
    nodes = []
    for name, pred in preds.items():
        ref = ref_by_name[name]
        try:
            sc = L.self_consistency(pred.pdb, ref, ca_thresh=ca_thresh, lig_thresh=lig_thresh)
        except Exception as e:
            raise RuntimeError(f"{name}: self-consistency could not be measured") from e
        score = None if getattr(args, "selective_affinity", False) else L.rank_score(pred, args.rank_metric)
        passed = sc.ok
        if args.backend is not None and hasattr(args.backend, "check_atom_requirements"):
            passed = args.backend.check_atom_requirements(pred) and passed
        # optional ligand-SASA filter (buried-ligand enrichment)
        if passed and args.ligand_sasa_max is not None:
            lsasa = L.ligand_sasa(pred.pdb)
            if lsasa is not None and lsasa > args.ligand_sasa_max:
                passed = False
        node = Node(
            name=name, sequence=seq_by_name[name], pdb=pred.pdb, ref_pdb=ref,
            ca_rmsd=sc.ca_rmsd, ligand_rmsd=sc.ligand_rmsd,
            ligand_plddt=pred.ligand_plddt, pbind=pred.pbind, score=score, cycle=cycle,
            score_status="not_evaluated" if getattr(args, "selective_affinity", False) else "scored",
            geometry_passed=passed, branch=getattr(args, "candidate_branch", "mpnn"),
        )
        if args.backend is not None:
            args.backend.record_candidate(node, passed, pred)
        if passed:
            nodes.append(node)
    return nodes


def select_scores(nodes, preds, args, directory, owners, *, per_group=1,
                  total_groups=None, minimum=0.0, previous=(), geometry_only=False):
    """Shared by both backbone sources and by NESSO-screened/Boltz-only routes."""
    if not getattr(args, "selective_affinity", False):
        for node in nodes:
            if node.score < minimum:
                node.score_status = "below_early_score_gate"
                args.backend.record_candidate(node, False, preds[node.name])
        return [n for n in nodes if n.score >= minimum]
    from search_policy import affinity_selection
    try:
        if geometry_only:
            for n in nodes:
                n.score_status = "omitted_geometry_only_stage"
                args.backend.record_candidate(n, True, preds[n.name])
            return nodes
        def score_batch(batch):
            scored = args.backend.affinity({n.name: preds[n.name] for n in batch}, directory, args)
            for node in batch:
                pred = scored[node.name]
                node.pbind, node.score = pred.pbind, L.rank_score(pred, args.rank_metric)
                node.score_status = "scored" if node.score >= minimum else "below_early_score_gate"
                args.backend.record_candidate(node, node.score >= minimum, pred)
        scored, skipped = affinity_selection(nodes, score_batch, lambda n: owners.get(n.name, n.traj),
            per_group=per_group, total_groups=total_groups, minimum=minimum,
            batch_size=args.affinity_batch_size, previous=previous)
        for n in nodes:
            if n.name in skipped:
                n.score_status = skipped[n.name]
                args.backend.record_candidate(n, False, preds[n.name])
        return [n for n in scored if n.score >= minimum]
    finally:
        args.backend.finish_scoring_stage()


def write_trajectory_row(writer, phase, node: Node, passed=True):
    writer.writerow([
        phase, node.cycle, node.traj, node.origin, node.name,
        f"{node.ca_rmsd:.3f}", f"{node.ligand_rmsd:.3f}",
        f"{node.ligand_plddt:.2f}", "" if node.pbind is None else f"{node.pbind:.3f}",
        "" if node.score is None else f"{node.score:.4f}", int(passed), node.sequence,
    ])


def pairwise_identity(a, b):
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    return 100.0 * sum(1 for i in range(n) if a[i] == b[i]) / n


# ----------------------------------------------------------------------
# resume support
# ----------------------------------------------------------------------


def find_pred_pdb(out, name):
    """Locate a Boltz prediction PDB anywhere under the run dir by design name."""
    import glob as _glob
    hits = _glob.glob(str(Path(out) / "**" / "predictions" / name / f"{name}_model_0.pdb"),
                      recursive=True)
    return hits[0] if hits else None


def _node_from_row(row, out):
    pb = row.get("pbind", "")
    return Node(
        name=row["name"], sequence=row["sequence"],
        pdb=find_pred_pdb(out, row["name"]) or "",
        ref_pdb="", ca_rmsd=float(row["ca_rmsd"]), ligand_rmsd=float(row["ligand_rmsd"]),
        ligand_plddt=float(row["ligand_plddt"]), pbind=float(pb) if pb not in ("", None) else None,
        score=float(row["score"]), cycle=int(row["cycle"]),
        traj=int(row["trajectory"]), origin=row["origin"],
    )


def read_folded_sequences(fold_dir):
    """Read {name: protein sequence} back from the Boltz input YAMLs of a fold step.

    Used on resume so we score exactly the sequences that were folded rather than
    regenerating (stochastic) ones.
    """
    seqs = {}
    for yml in Path(fold_dir).glob("**/yaml/*.yaml"):
        seq = None
        for line in yml.read_text().splitlines():
            m = re.match(r"\s*sequence:\s*(\S+)\s*$", line)
            if m:
                seq = m.group(1)
                break
        if seq:
            seqs[yml.stem] = seq
    return seqs


def rebuild_trajectories(out, args):
    """Replay an existing trajectory.csv to reconstruct per-trajectory NISE state.

    Returns (trajs, last_scored_cycle). Mirrors the improvement/patience logic of
    the main loop so counters match exactly.
    """
    rows = list(csv.DictReader(open(Path(out) / "trajectory.csv")))
    nise = [r for r in rows if r["phase"] == "nise"]
    if not nise:
        raise SystemExit("--resume: trajectory.csv has no 'nise' rows to resume from.")
    p0 = [r for r in rows if r["phase"].startswith("phase0")]

    origin = {}
    for r in nise:
        origin.setdefault(int(r["trajectory"]), r["origin"])

    # The seed came from the Phase-0 *expand* cycle (the last phase0.* stage), so
    # restrict to that phase; using earlier refine cycles would overstate the
    # seed score and wrongly inflate the no-improve counters.
    if p0:
        last_p0_phase = max({r["phase"] for r in p0},
                            key=lambda s: int(re.sub(r"\D", "", s) or 0))
        p0 = [r for r in p0 if r["phase"] == last_p0_phase]

    # seed node per trajectory = best-scoring expand-cycle design from that lineage
    trajs = []
    for tid in sorted(origin):
        o = origin[tid]
        cand = [r for r in p0 if r.get("origin") == o]
        seed_score = max((float(r["score"]) for r in cand), default=0.0)
        seed_node = None
        if cand:
            best_row = max(cand, key=lambda r: float(r["score"]))
            seed_node = _node_from_row(dict(best_row, trajectory=str(tid), origin=o), out)
        trajs.append(dict(tid=tid, origin=o, current=[], best_score=seed_score,
                          best_node=seed_node, no_improve=0, alive=True))
    by_tid = {t["tid"]: t for t in trajs}

    cycles = sorted({int(r["cycle"]) for r in nise})
    for cyc in cycles:
        for t in trajs:
            if not t["alive"]:
                continue
            rs = [r for r in nise if int(r["cycle"]) == cyc and int(r["trajectory"]) == t["tid"]]
            if not rs:
                t["alive"] = False
                continue
            rs.sort(key=lambda r: float(r["score"]), reverse=True)
            nodes = [_node_from_row(r, out) for r in rs[: args.beam]]
            t["current"] = [n for n in nodes if n.pdb]
            cbest = float(rs[0]["score"])
            if cbest > t["best_score"] + args.min_improvement:
                t["best_score"] = cbest
                t["best_node"] = _node_from_row(rs[0], out)
                t["no_improve"] = 0
            else:
                t["no_improve"] += 1
                if t["no_improve"] >= args.patience:
                    t["alive"] = False
    return trajs, (cycles[-1] if cycles else 0)


def main(argv=None, backend=None):
    if backend is None:
        raise ValueError("Use the managed NISE campaign.py entry point with a saved request")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--template-yaml", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--resume", action="store_true",
                    help="Resume an interrupted run in --out-dir: skip Phase 0, rebuild per-trajectory "
                         "state from trajectory.csv, ingest any already-folded structures for the next "
                         "cycle, and continue. Appends to trajectory.csv.")
    ap.add_argument("--designer", choices=["lasermpnn", "ligandmpnn"], default="lasermpnn")
    ap.add_argument("--device", default="cpu", help="LASErMPNN device (cpu on Apple Silicon).")
    ap.add_argument("--seed", type=int, default=0)

    # hallucination
    ap.add_argument("--num-starts", type=int, default=100)
    ap.add_argument("--backbone-method", choices=["protein-hunter", "rfdiffusion3"], default="protein-hunter")
    ap.add_argument("--binder-min-len", type=int, default=65)
    ap.add_argument("--binder-max-len", type=int, default=150)
    ap.add_argument("--binder-percent-x", type=int, default=50)

    # phase 0
    ap.add_argument("--phase0-seqs1", type=int, default=3)
    ap.add_argument("--phase0-gate-seqs", type=int, default=None)
    ap.add_argument("--phase0-seqs2", type=int, default=5)
    ap.add_argument("--phase0-temp", type=float, default=0.5)
    ap.add_argument("--phase0-sc-ca", type=float, default=2.0)
    ap.add_argument("--phase0-sc-lig", type=float, default=2.0)
    ap.add_argument("--phase0-refine-cycles", type=int, default=2,
                    help="Metric-greedy refinement cycles (pocket on, best-1/lineage) before the "
                         "Cα self-consistency gate cycle. Funnel = cycle00 + R refine + gate + expand.")
    ap.add_argument("--phase0-require-ligand-sc", dest="phase0_ligand_sc", action="store_true",
                    help="Gate Phase 0 on ligand self-consistency too. OFF by default: the "
                         "hallucinated cycle00 ligand pose is uninformative, so Phase 0 uses "
                         "Cα self-consistency only and ranks by ligand pLDDT + P(bind).")
    ap.set_defaults(phase0_ligand_sc=False)

    # phase 1 (NISE) — independent trajectories, one per distinct start
    ap.add_argument("--trajectories", type=int, default=3,
                    help="Number of independent NISE trajectories (distinct starting points). "
                         "Each keeps its own beam; there is no cross-trajectory pooling per cycle.")
    ap.add_argument("--beam", type=int, default=1,
                    help="Within-trajectory beam width (structures carried per cycle). "
                         "The paper used 3 (with ~1000 seqs each); 1 is a cheaper hill-climb.")
    ap.add_argument("--nise-seqs", type=int, default=64)
    ap.add_argument("--first-cycle-seqs", type=int, default=None)
    ap.add_argument("--partial-noising", action="store_true")
    ap.add_argument("--noise-radius", type=float, default=6.0)
    ap.add_argument("--noise-percent", type=float, default=25.0)
    ap.add_argument("--noise-predictions", type=int, default=32)
    ap.add_argument("--noise-mpnn-seqs", type=int, default=32)
    ap.add_argument("--noise-advance", type=int, default=1)
    ap.add_argument("--nise-sc-ca", type=float, default=2.5)
    ap.add_argument("--nise-sc-lig", type=float, default=2.5)
    ap.add_argument("--nise-ligand-sc-from-cycle", type=int, default=3,
                    help="Cycle at which ligand self-consistency turns on (ramp). Before this, "
                         "only Cα self-consistency is enforced so the pose can settle.")
    ap.add_argument("--seq-temp", type=float, default=0.5)
    ap.add_argument("--bindingsite-temp", type=float, default=0.7)
    ap.add_argument("--fs-distance", type=float, default=10.0)
    ap.add_argument("--ala-budget", type=int, default=2)
    ap.add_argument("--gly-budget", type=int, default=0)
    ap.add_argument("--max-cycles", type=int, default=30)
    ap.add_argument("--patience", type=int, default=5)
    ap.add_argument("--min-improvement", type=float, default=1e-4)
    ap.add_argument("--early-score-gate", type=float, default=0.0)
    ap.add_argument("--selective-affinity", action="store_true")
    ap.add_argument("--affinity-batch-size", type=int, default=8)
    ap.add_argument("--adaptive-proposals", action="store_true")
    ap.add_argument("--initial-proposals", type=int, default=16)

    # ranking / prediction
    ap.add_argument("--rank-metric", choices=["auto", "ligand_plddt", "ligand_plddt+pbind"], default="auto")
    ap.add_argument("--no-affinity", dest="affinity", action="store_false",
                    help="Disable Boltz-2 affinity (P(bind)); ranking falls back to ligand pLDDT.")
    ap.add_argument("--recycling", type=int, default=None)
    ap.add_argument("--sampling-steps", type=int, default=None)
    # Boltz inference-steering potentials (physical plausibility), applied to all folds.
    ap.add_argument("--no-use-potentials", dest="use_potentials", action="store_false",
                    help="Disable Boltz --use_potentials steering (on by default).")
    ap.set_defaults(use_potentials=True)
    # Phase-0-only pocket constraint: fold the initial backbone AROUND the ligand,
    # then drop it for the NISE trajectory so refinement/self-consistency stay honest.
    ap.add_argument("--no-phase0-constraints", dest="phase0_constraints", action="store_false",
                    help="Disable the Phase-0 pocket constraint (on by default).")
    ap.set_defaults(phase0_constraints=True)
    ap.add_argument("--phase0-pocket-distance", type=float, default=6.0,
                    help="max_distance (Å) for the Phase-0 pocket constraint.")
    ap.add_argument("--phase0-pocket-contacts", type=int, default=5,
                    help="Number of ligand atoms (spanning the molecule) used as pocket contacts in Phase 0.")
    ap.add_argument("--phase0-pocket-ligand-atoms", default=None,
                    help="Explicit comma-separated ligand atom names (Boltz naming, e.g. 'C26,O22,...') "
                         "to use as Phase-0 pocket contacts, overriding auto-selection.")
    ap.add_argument("--no-phase0-pocket-force", dest="phase0_pocket_force", action="store_false",
                    help="Make the Phase-0 pocket constraint a soft bias instead of forced.")
    ap.set_defaults(phase0_pocket_force=True)
    ap.add_argument("--boltz-parallel", type=int, default=2,
                    help="Concurrent Boltz processes per fold step (shards the batch). "
                         "Each MPS process uses ~5 GB; up to 4 is a big speedup with enough RAM.")

    # optional filters
    ap.add_argument("--ligand-sasa-max", type=float, default=None,
                    help="If set, drop designs whose ligand SASA exceeds this (buried-ligand enrichment).")
    ap.set_defaults(affinity=True)
    args = ap.parse_args(argv)
    if args.phase0_gate_seqs is None:
        args.phase0_gate_seqs = args.phase0_seqs1
    if args.first_cycle_seqs is None:
        args.first_cycle_seqs = args.nise_seqs
    if args.partial_noising and (backend is None or args.adaptive_proposals or args.noise_advance >= args.beam):
        raise ValueError("Partial noising requires the managed backend, fixed sampling and a normal beam place")
    args.backend = backend
    # Replay the deterministic search over atomic operation receipts, including Phase 0.
    # Never reconstruct patience from a partially appended CSV.
    args.resume = False

    # Absolute so subprocesses launched with a different cwd (LASErMPNN in src/,
    # LigandMPNN in its repo) resolve the paths we hand them.
    out = Path(args.out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    smiles = extract_ligand_smiles(args.template_yaml)
    if not smiles:
        raise SystemExit(f"No ligand SMILES found in {args.template_yaml}")
    log(f"ligand SMILES: {smiles}")
    log(f"designer={args.designer} device={args.device} rank_metric={args.rank_metric} affinity={args.affinity}")
    log(f"potentials={args.use_potentials}  phase0_pocket_constraint={args.phase0_constraints} "
        f"(binder=protein A around specific ligand-B atoms; off in NISE)")
    backend.freeze_config({k: v for k, v in vars(args).items() if k != "backend"})
    rng = np.random.default_rng(args.seed)

    # Phase-0-only pocket constraint: the designed protein (binder A) must form a
    # pocket contacting specific ligand-B atoms, so the initial backbone folds
    # around the ligand. Dropped for the NISE trajectory.
    phase0_pocket = None
    if args.phase0_constraints:
        if backend is not None and hasattr(backend, "initial_contacts"):
            atoms = backend.initial_contacts(smiles, args.phase0_pocket_contacts)
        elif args.phase0_pocket_ligand_atoms:
            atoms = [a.strip() for a in args.phase0_pocket_ligand_atoms.split(",") if a.strip()]
        else:
            atoms = L.ligand_contact_atoms(smiles, k=args.phase0_pocket_contacts, affinity=args.affinity)
        log(f"Phase-0 pocket: binder=A contacts (ligand atoms)={atoms} "
            f"dist={args.phase0_pocket_distance} force={args.phase0_pocket_force}")
        phase0_pocket = {"binder": "A", "contacts": [["B", a] for a in atoms],
                         "max_distance": args.phase0_pocket_distance, "force": args.phase0_pocket_force}

    traj = open(out / "trajectory.csv.part", "w", newline="")
    tw = csv.writer(traj)
    if not args.resume:
        tw.writerow(["phase", "cycle", "trajectory", "origin", "name", "ca_rmsd", "ligand_rmsd",
                     "ligand_plddt", "pbind", "score", "passed", "sequence"])

    def origin_of(nm):
        return nm.split("_d1")[0]

    # Phase 0 is backbone-only by default: the hallucinated ligand pose is
    # uninformative, so we don't gate on ligand self-consistency there.
    p0_lig = args.phase0_sc_lig if args.phase0_ligand_sc else 1e9

    # ------------------------------------------------------------------
    # Phase 0 - broad FUNNEL (replaces the old 0.1/0.2/0.3):
    #   cycle00        hallucinate N starts (pocket on)           -> N lineages
    #   cycle01..R     3 seqs/lineage, fold (pocket on), keep      -> N lineages
    #                  best-1 per lineage by ligand pLDDT+P(bind); no RMSD gate
    #   gate cycle     3 seqs/lineage, fold (pocket OFF), keep all -> survivors
    #                  passing a Cα self-consistency gate vs the prior structure
    #   expand cycle   5 seqs/survivor, fold, rank; take top       -> seeds
    #                  `trajectories`, max 1 per lineage (diversity)
    # Pocket stays on cycles 00..R and off from the gate cycle so self-consistency
    # is judged on unconstrained folds. Potentials stay on throughout.
    # ------------------------------------------------------------------
    def p0dir(cyc, *parts):
        return (out / "phase0" / f"cycle{cyc:02d}").joinpath(*parts)

    if args.resume:
        trajs, last_cycle = rebuild_trajectories(out, args)
        alive_n = sum(1 for t in trajs if t["alive"])
        log(f"RESUME: rebuilt {len(trajs)} trajectories from trajectory.csv "
            f"(last scored cycle {last_cycle}; {alive_n} still alive)")
        for t in trajs:
            log(f"  T{t['tid']}({t['origin']}): best={t['best_score']:.4f} "
                f"no_improve={t['no_improve']}/{args.patience} alive={t['alive']} "
                f"beam={len(t['current'])}")
        seeds = [t for t in trajs]  # only used for the count in the Phase 1 banner
        start_cycle = last_cycle + 1
        ingest_cycle = start_cycle  # this cycle's folds may already exist on disk
    else:
        start_cycle, ingest_cycle = 1, None

    if not args.resume:
        if args.backbone_method == "rfdiffusion3":
            log(f"Phase 0 cycle00: generating {args.num_starts} RFdiffusion3 backbones")
            lineages = backend.initial_backbones(smiles, p0dir(0), args)
            if len(lineages) != args.num_starts:
                raise RuntimeError("RFdiffusion3 returned the wrong number of initial backbones")
        else:
            log(f"Phase 0 cycle00: hallucinating {args.num_starts} starts (pocket={'on' if phase0_pocket else 'off'})")
            halluc = {f"L{j:03d}": L.generate_random_binder(
                rng, args.binder_min_len, args.binder_max_len, args.binder_percent_x)
                for j in range(args.num_starts)}
            hpreds = fold_and_score(halluc, smiles, p0dir(0), args, pocket=phase0_pocket)
            lineages = {}  # lineage_id -> current structure pdb
            for name, pred in hpreds.items():
                ref = p0dir(0) / f"{name}_ref.pdb"
                L.patch_unk_pdb(pred.pdb, ref)
                lineages[name] = str(ref)
            if getattr(args, "selective_affinity", False):
                backend.finish_scoring_stage()
        if getattr(args, "selective_affinity", False):
            from types import SimpleNamespace
            from runtime import atomic
            checks = {name: backend.check_atom_requirements(SimpleNamespace(name=name, pdb=pdb))
                      for name, pdb in lineages.items()}
            atomic(p0dir(0, "initial_geometry.json"), dict(passed=checks,
                   atom_checks=getattr(backend, "atom_checks", {}), affinity="omitted"))
            lineages = {name: pdb for name, pdb in lineages.items() if checks[name]}
        log(f"  prepared {len(lineages)}/{args.num_starts} starts")
        if not lineages:
            raise SystemExit("Hallucination produced no foldable starts.")

        # metric-greedy refinement cycles (pocket on), best-1 per lineage, no gate
        for cyc in range(1, args.phase0_refine_cycles + 1):
            log(f"Phase 0 cycle{cyc:02d}: {args.phase0_seqs1} seqs/lineage, fold (pocket=on), keep best-1/lineage")
            seq_by_name, ref_by_name, owner = {}, {}, {}
            for lid, pdb in lineages.items():
                seqs = design_sequences(args.designer, pdb, p0dir(cyc, "design", lid),
                                        args.phase0_seqs1, smiles, args,
                                        seq_temp=args.phase0_temp, fs_temp=args.phase0_temp,
                                        seed=args.seed + cyc, constrain_ss=(args.designer == "lasermpnn"))
                for k, s in enumerate(seqs):
                    nm = f"{lid}_c{cyc}_{k}"
                    seq_by_name[nm] = s; ref_by_name[nm] = pdb; owner[nm] = lid
            if backend is not None and hasattr(backend, "screen_initial"):
                sampled = len(seq_by_name)
                seq_by_name = backend.screen_initial(seq_by_name, smiles, p0dir(cyc, "nesso"), owner, "refinement")
                log(f"  refinement: {len(seq_by_name)}/{sampled} sequences sent to Boltz; atom checks follow folding")
            preds = fold_and_score(seq_by_name, smiles, p0dir(cyc, "fold"), args, pocket=phase0_pocket)
            nodes = evaluate_candidates(preds, seq_by_name, ref_by_name, args, cyc, 1e9, 1e9)  # no gate
            nodes = select_scores(nodes, preds, args, p0dir(cyc, "fold"), owner,
                                  minimum=args.early_score_gate if cyc == 1 else 0.0)
            best = {}
            for n in nodes:
                lid = owner[n.name]; n.origin = lid
                if lid not in best or (-n.score, n.name) < (-best[lid].score, best[lid].name):
                    best[lid] = n
            for n in best.values():
                write_trajectory_row(tw, f"phase0.c{cyc}", n, True)
            traj.flush()
            lineages = {lid: n.pdb for lid, n in best.items()}
            log(f"  {len(lineages)} lineages advanced")
            if not lineages:
                raise SystemExit(f"Phase 0 cycle{cyc:02d} produced no designs passing selection. Inspect candidates/ and atom_checks.csv.")

        # gate cycle (pocket OFF): keep all designs passing a Cα self-consistency gate
        gate_cyc = args.phase0_refine_cycles + 1
        log(f"Phase 0 cycle{gate_cyc:02d} (gate): {args.phase0_gate_seqs} seqs/lineage, fold (pocket=off), "
            f"keep Cα-SC < {args.phase0_sc_ca} Å vs prior structure")
        seq_by_name, ref_by_name, owner = {}, {}, {}
        for lid, pdb in lineages.items():
            seqs = design_sequences(args.designer, pdb, p0dir(gate_cyc, "design", lid),
                                    args.phase0_gate_seqs, smiles, args,
                                    seq_temp=args.phase0_temp, fs_temp=args.phase0_temp,
                                    seed=args.seed + gate_cyc, constrain_ss=(args.designer == "lasermpnn"))
            for k, s in enumerate(seqs):
                nm = f"{lid}_c{gate_cyc}_{k}"
                seq_by_name[nm] = s; ref_by_name[nm] = pdb; owner[nm] = lid
        preds = fold_and_score(seq_by_name, smiles, p0dir(gate_cyc, "fold"), args, pocket=None)
        survivors = evaluate_candidates(preds, seq_by_name, ref_by_name, args, gate_cyc, args.phase0_sc_ca, 1e9)
        survivors = select_scores(survivors, preds, args, p0dir(gate_cyc, "fold"), owner, geometry_only=True)
        for n in survivors:
            n.origin = owner[n.name]
            write_trajectory_row(tw, f"phase0.c{gate_cyc}", n, True)
        traj.flush()
        n_lin = len({n.origin for n in survivors})
        log(f"  {len(survivors)}/{len(seq_by_name)} passed structural/atom checks, from {n_lin} distinct lineages")
        if not survivors:
            raise SystemExit("Phase 0 gate produced no designs passing structural and requested atom checks. Inspect candidates/ and atom_checks.csv before changing settings.")

        # expand cycle (pocket OFF): 5 seqs/survivor, rank, diverse top-N (max 1/lineage)
        exp_cyc = args.phase0_refine_cycles + 2
        log(f"Phase 0 cycle{exp_cyc:02d} (expand): {args.phase0_seqs2} seqs/survivor, fold, "
            f"rank -> top {args.trajectories} seeds (max 1/lineage)")
        seq_by_name, ref_by_name, owner = {}, {}, {}
        for i, sv in enumerate(survivors):
            seqs = design_sequences(args.designer, sv.pdb, p0dir(exp_cyc, "design", sv.name),
                                    args.phase0_seqs2, smiles, args,
                                    seq_temp=args.phase0_temp, fs_temp=args.phase0_temp,
                                    seed=args.seed + exp_cyc + i, constrain_ss=(args.designer == "lasermpnn"))
            for k, s in enumerate(seqs):
                nm = f"{sv.name}_e{k}"
                seq_by_name[nm] = s; ref_by_name[nm] = sv.pdb; owner[nm] = sv.origin
        if backend is not None and hasattr(backend, "screen_initial"):
            sampled = len(seq_by_name)
            seq_by_name = backend.screen_initial(seq_by_name, smiles, p0dir(exp_cyc, "nesso"), owner, "expansion")
            log(f"  expansion: {len(seq_by_name)}/{sampled} sequences sent to Boltz; original-lineage identity retained")
        preds = fold_and_score(seq_by_name, smiles, p0dir(exp_cyc, "fold"), args, pocket=None)
        ranked = evaluate_candidates(preds, seq_by_name, ref_by_name, args, exp_cyc, 1e9, 1e9)  # rank only
        ranked = select_scores(ranked, preds, args, p0dir(exp_cyc, "fold"), owner,
                               total_groups=args.trajectories)
        for n in ranked:
            n.origin = owner[n.name]
            write_trajectory_row(tw, f"phase0.c{exp_cyc}", n, True)
        traj.flush()
        if not ranked:
            raise SystemExit("Phase 0 expand cycle produced no designs passing selection. Inspect candidates/ and atom_checks.csv.")
        ranked.sort(key=lambda n: (-n.score, n.name))
        seeds, used = [], set()
        for n in ranked:
            if n.origin in used:            # max 1 per lineage -> structural diversity
                continue
            used.add(n.origin); n.traj = len(seeds); seeds.append(n)
            if len(seeds) >= args.trajectories:
                break
        log(f"  {len(seeds)} diverse seeds selected (from {len({n.origin for n in ranked})} surviving lineages):")
        for n in seeds:
            log(f"    T{n.traj}<-{n.origin} score={n.score:.3f} ligpLDDT={n.ligand_plddt:.1f} pbind={n.pbind}")

    # ------------------------------------------------------------------
    # Phase 1 - INDEPENDENT NISE trajectories (no cross-trajectory pooling).
    #   Each trajectory keeps its own beam; we advance all of them one cycle
    #   at a time only so their folds share one parallel Boltz batch.
    # ------------------------------------------------------------------
    log(f"Phase 1: {len(seeds)} independent trajectories, beam {args.beam}, "
        f"{args.first_cycle_seqs} proposals in cycle 1; {args.nise_seqs} per parent later, ligand-SC from cycle {args.nise_ligand_sc_from_cycle} "
        f"(max {args.max_cycles} cycles, patience {args.patience})")
    if not args.resume:
        trajs = [dict(tid=n.traj, origin=n.origin, current=[n], best_score=n.score,
                      best_node=n, best_beam=[n], no_improve=0, alive=True) for n in seeds]

    for cycle in range(start_cycle, args.max_cycles + 1):
        alive = [t for t in trajs if t["alive"]]
        if not alive:
            break
        lig_thresh = args.nise_sc_lig if cycle >= args.nise_ligand_sc_from_cycle else 1e9
        from search_policy import proposal_levels
        from runtime import atomic
        cap = args.first_cycle_seqs if cycle == 1 else args.nise_seqs
        levels = proposal_levels(cap, args.adaptive_proposals, args.initial_proposals)
        noising_active = args.partial_noising and cycle >= 2
        normal_places = args.beam - args.noise_advance if noising_active else args.beam
        by_tid = defaultdict(list)
        pending = list(alive)
        previous_level = 0
        for level in levels:
            if not pending:
                break
            round_dir = out / f"cycle{cycle:02d}"
            if args.adaptive_proposals:
                round_dir = round_dir / f"topup{level:04d}"
            fold_dir = round_dir / "fold"
            seq_by_name, ref_by_name, owner = {}, {}, {}
            # A reserved noising place also replaces an ordinary sampling parent.
            # Rank across the complete current beam: a successful repair can
            # become an ordinary parent in the next cycle.
            sampling_parents = {
                t["tid"]: (sorted(t["current"], key=lambda n: (-n.score, n.name))[:normal_places]
                           if noising_active else t["current"])
                for t in pending}
            parents = {tid: [asdict(n) for n in nodes] for tid, nodes in sampling_parents.items()}
            for t in pending:
                for j, node in enumerate(sampling_parents[t["tid"]]):
                    seqs = design_sequences(args.designer, node.pdb,
                        round_dir / "design" / f"T{t['tid']}_n{j}",
                        level - previous_level, smiles, args,
                        seed=(args.seed + cycle * 1000000 + t["tid"] * 10000 + j * 100 + previous_level
                              if args.adaptive_proposals else args.seed + cycle * 1000 + t["tid"] * 10 + j),
                        constrain_ss=(args.designer == "lasermpnn"),
                        seq_temp=args.seq_temp, fs_temp=args.bindingsite_temp)
                    for k, sequence in enumerate(seqs, start=previous_level):
                        name = f"c{cycle:02d}_t{t['tid']}_n{j}_s{k}"
                        seq_by_name[name] = sequence
                        ref_by_name[name] = node.pdb
                        owner[name] = t["tid"]
            preds = fold_and_score(seq_by_name, smiles, fold_dir, args)
            cands = evaluate_candidates(preds, seq_by_name, ref_by_name, args, cycle,
                                        args.nise_sc_ca, lig_thresh)
            cands = select_scores(cands, preds, args, fold_dir, owner, per_group=normal_places,
                                 previous=[n for pool in by_tid.values() for n in pool])
            by_id = {t["tid"]: t for t in alive}
            for n in cands:
                t = by_id[owner[n.name]]
                n.traj, n.origin = t["tid"], t["origin"]
                by_tid[t["tid"]].append(n)
                write_trajectory_row(tw, "nise", n, True)
            traj.flush()
            continuing = [t for t in pending if not by_tid[t["tid"]] or
                          max(n.score for n in by_tid[t["tid"]]) <= t["best_score"] + args.min_improvement]
            atomic(round_dir / "proposal_round.json", dict(
                cycle=cycle, cumulative_proposals_per_parent=level,
                additional_proposals_per_parent=level - previous_level,
                sampled=len(seq_by_name), folded=len(preds), affinity_scored=len(cands),
                parents=parents, normal_parent_limit=normal_places,
                pooled_beams={str(t["tid"]): [asdict(n) for n in
                    sorted(by_tid[t["tid"]], key=lambda n: (-n.score, n.name))[:args.beam]] for t in alive},
                needs_topup=[t["tid"] for t in continuing], rollback=False))
            log(f"  cycle {cycle}: {level} proposals/parent reached; "
                f"{len(continuing)} trajectories without sufficient improvement")
            pending, previous_level = continuing, level
        noise_pools = {}
        if noising_active:
            from partial_noising import run_branch
            noise_pools = run_branch(alive, out, smiles, args, cycle, lig_thresh, tw)
            traj.flush()
        lig_state = "on" if cycle >= args.nise_ligand_sc_from_cycle else "off"
        for t in alive:
            normal = sorted(by_tid.get(t["tid"], []), key=lambda n: (-n.score, n.name))
            noisy = noise_pools.get(t["tid"], [])
            tc = sorted(normal[:normal_places] + noisy[:args.noise_advance], key=lambda n: (-n.score, n.name))
            if not tc:
                t["alive"] = False
                log(f"  cycle {cycle} T{t['tid']}: no self-consistent designs; trajectory stops.")
                continue
            t["current"] = tc[: args.beam]
            cbest = tc[0].score
            if cbest > t["best_score"] + args.min_improvement:
                t["no_improve"] = 0
                t["best_beam"] = list(t["current"])
                flag = "IMPROVED"
            else:
                t["no_improve"] += 1
                flag = f"no-improve {t['no_improve']}/{args.patience}"
                if t["no_improve"] >= args.patience:
                    t["alive"] = False
                    flag += " -> stop"
            if cbest > t["best_score"]:
                t["best_score"], t["best_node"] = cbest, tc[0]
            log(f"  cycle {cycle} T{t['tid']}({t['origin']}): {len(normal) + len(noisy)} scored survivors, {len(t['current'])} advancing [lig-SC {lig_state}]; "
                f"best={cbest:.4f} (ligpLDDT={tc[0].ligand_plddt:.1f}, pbind={tc[0].pbind}) {flag}")

        if hasattr(backend, "record_advancement"):
            backend.record_advancement(cycle, trajs)

    traj.close()
    (out / "trajectory.csv.part").replace(out / "trajectory.csv")

    # ------------------------------------------------------------------
    # outputs: best design PER trajectory (diverse by construction), plus
    #          pooled global best and a pairwise-identity diversity report.
    # ------------------------------------------------------------------
    best_dir = out / "best"
    best_dir.mkdir(exist_ok=True)
    import shutil
    # A trajectory can legitimately have no best_node: rebuild_trajectories leaves
    # seed_node None when a resumed trajectory finds no matching phase-0 rows, and a
    # trajectory killed in its first cycle never sets one. Dropping those here
    # instead of sorting over None avoids losing a whole campaign at the very last
    # step. Also skip nodes whose structure has gone missing.
    winners = sorted(
        (t["best_node"] for t in trajs
         if t["best_node"] is not None and t["best_node"].pdb
         and Path(t["best_node"].pdb).is_file()),
        key=lambda n: n.score, reverse=True)
    dropped = len(trajs) - len(winners)
    if dropped:
        print(f"[nise]   note: {dropped} trajectory(ies) contributed no usable "
              f"winner (no scored design, or its structure is missing)")
    if not winners:
        print("[nise] DONE, but no trajectory produced a usable design; "
              "wrote no best/ outputs.")
        return
    for rank, node in enumerate(winners):
        tag = f"rank{rank}_T{node.traj}_{node.origin}"
        shutil.copy(node.pdb, best_dir / f"{tag}.pdb")
        (best_dir / f"{tag}.fasta").write_text(
            f">{tag} score={node.score:.4f} ligpLDDT={node.ligand_plddt:.1f} pbind={node.pbind}\n{node.sequence}\n")
    # pairwise identity across the per-trajectory winners
    ident = []
    for i in range(len(winners)):
        for j in range(i + 1, len(winners)):
            ident.append(round(pairwise_identity(winners[i].sequence, winners[j].sequence), 1))
    mean_ident = round(sum(ident) / len(ident), 1) if ident else None
    best = winners[0]
    summary = {
        "best_score": best.score, "best_trajectory": best.traj, "best_origin": best.origin,
        "best_sequence": best.sequence, "best_ligand_plddt": best.ligand_plddt, "best_pbind": best.pbind,
        "n_trajectories": len(trajs),
        "trajectory_winners": [
            dict(trajectory=t["tid"], origin=t["origin"], score=t["best_node"].score,
                 ligand_plddt=t["best_node"].ligand_plddt, pbind=t["best_node"].pbind,
                 sequence=t["best_node"].sequence) for t in trajs],
        "pairwise_identity_pct": ident,
        "mean_pairwise_identity_pct": mean_ident,
    }
    backend.write_summary(summary)
    log(f"DONE. Best score={best.score:.4f} (T{best.traj}<-{best.origin}, "
        f"ligpLDDT={best.ligand_plddt:.1f}, pbind={best.pbind})")
    log(f"  {len(winners)} trajectory winners, mean pairwise identity {mean_ident}%")
    log(f"Outputs: {out}/trajectory.csv, {out}/summary.json, {best_dir}/")


if __name__ == "__main__":
    main()
