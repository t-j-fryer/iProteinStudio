#!/usr/bin/env python3
"""Geometry metrics for the beta NISE variants.

**Preorganisation** — compare a holo (ligand-bound) prediction against an apo
prediction of the same sequence. Three numbers, because they fail differently:

  preorg_rmsd            superpose pocket BACKBONE, measure pocket ALL-HEAVY atoms.
                         The primary score. Preorganisation is largely a side-chain
                         rotamer question, so a CA-only measure is near-blind to it.
  pocket_displacement    superpose SCAFFOLD CA, measure pocket CA. Catches a pocket
                         that kept its shape but swung away or collapsed inward.
  global_ca_rmsd         superpose whole binder CA, measure whole binder CA. Catches
                         ligand-dependent folding - the design is not a protein
                         without its ligand.

**Interface self-consistency** — the protein-protein analogue of NISE's ligand
RMSD: superpose the binder onto its parent prediction, then measure the target's
displacement in that same frame, with no re-alignment of the target.

Atom correspondence is keyed on (chain, residue number, atom name), never on array
order, so it survives any reordering between two predictions.

Run under the main install's boltz venv (needs gemmi + numpy).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import gemmi
import numpy as np

BACKBONE = frozenset(("N", "CA", "C", "O"))


@dataclass(frozen=True)
class AtomKey:
    chain: str
    resnum: int
    atom: str


def load_structure(path):
    """(keys, coords, elements, bfactors) over heavy atoms; H/waters dropped."""
    st = gemmi.read_structure(str(path))
    st.setup_entities()
    st.remove_alternative_conformations()
    st.remove_hydrogens()
    st.remove_waters()
    keys, xyz, elems, bfac = [], [], [], []
    for chain in st[0]:
        for res in chain:
            for atom in res:
                keys.append(AtomKey(chain.name, res.seqid.num, atom.name.strip()))
                xyz.append([atom.pos.x, atom.pos.y, atom.pos.z])
                elems.append(atom.element.name.upper())
                bfac.append(atom.b_iso)
    if not keys:
        raise ValueError(f"no atoms parsed from {path}")
    return keys, np.asarray(xyz, float), elems, np.asarray(bfac, float)


def _index(keys):
    return {k: i for i, k in enumerate(keys)}


def kabsch(P, Q):
    """Transform taking P onto Q. Returns (rmsd, R, P_centroid, Q_centroid)."""
    if len(P) != len(Q):
        raise ValueError(f"atom count mismatch: {len(P)} vs {len(Q)}")
    if len(P) < 3:
        raise ValueError(f"need >=3 atoms to superpose, got {len(P)}")
    pc, qc = P.mean(0), Q.mean(0)
    A, B = P - pc, Q - qc
    V, _, Wt = np.linalg.svd(A.T @ B)
    if np.linalg.det(V @ Wt) < 0:
        V[:, -1] *= -1
    R = V @ Wt
    return float(np.sqrt((((A @ R) - B) ** 2).sum(1).mean())), R, pc, qc


def apply_transform(X, R, from_centroid, to_centroid):
    return (X - from_centroid) @ R + to_centroid


def rmsd_after(P_sel, Q_sel, P_meas, Q_meas):
    """Superpose on the *_sel sets, then measure RMSD over the *_meas sets."""
    _, R, pc, qc = kabsch(P_sel, Q_sel)
    return float(np.sqrt(
        ((apply_transform(P_meas, R, pc, qc) - Q_meas) ** 2).sum(1).mean()))


def pocket_residues(holo_path, protein_chain="A", ligand_chain="B", cutoff=4.5):
    """Protein residue numbers with any heavy atom within `cutoff` of the ligand.

    Contact-based on purpose, and a deliberately separate knob from the ~10 A CA
    definition used for MPNN binding-site temperature: that one asks "which
    residues should be diversified", this asks "which residues form the site".
    """
    keys, xyz, _, _ = load_structure(holo_path)
    prot = np.array([i for i, k in enumerate(keys) if k.chain == protein_chain])
    lig = np.array([i for i, k in enumerate(keys) if k.chain == ligand_chain])
    if len(lig) == 0:
        raise ValueError(f"no atoms in ligand chain {ligand_chain} of {holo_path}")
    if len(prot) == 0:
        raise ValueError(f"no atoms in protein chain {protein_chain} of {holo_path}")
    d = np.linalg.norm(xyz[prot][:, None, :] - xyz[lig][None, :, :], axis=-1)
    return sorted({keys[i].resnum for i in prot[(d < cutoff).any(axis=1)]})


@dataclass
class Preorg:
    preorg_rmsd: float
    pocket_displacement: float
    global_ca_rmsd: float
    apo_pocket_plddt: float
    apo_global_plddt: float
    n_pocket_residues: int
    n_pocket_atoms: int

    def as_dict(self):
        return asdict(self)


def preorganisation(holo_path, apo_path, pocket_res, protein_chain="A"):
    """Compare the binder chain of a holo prediction with its apo prediction.

    `pocket_res` must come from pocket_residues() on the HOLO structure - the apo
    structure has no ligand from which to define a pocket.
    """
    hk, hx, _, _ = load_structure(holo_path)
    ak, ax, _, ab = load_structure(apo_path)
    hi, ai = _index(hk), _index(ak)
    pset = set(pocket_res)
    shared = [k for k in hk if k.chain == protein_chain and k in ai]
    if not shared:
        raise ValueError("holo and apo share no protein atoms - sequence mismatch?")

    def pair(sel):
        idx = [(hi[k], ai[k]) for k in shared if sel(k)]
        if not idx:
            return None, None
        return (np.array([hx[a] for a, _ in idx]),
                np.array([ax[b] for _, b in idx]))

    p_bb_h, p_bb_a = pair(lambda k: k.resnum in pset and k.atom in BACKBONE)
    p_all_h, p_all_a = pair(lambda k: k.resnum in pset)
    p_ca_h, p_ca_a = pair(lambda k: k.resnum in pset and k.atom == "CA")
    s_ca_h, s_ca_a = pair(lambda k: k.resnum not in pset and k.atom == "CA")
    a_ca_h, a_ca_a = pair(lambda k: k.atom == "CA")

    if p_bb_h is None or len(p_bb_h) < 3:
        raise ValueError("fewer than 3 shared pocket backbone atoms")

    preorg = rmsd_after(p_bb_h, p_bb_a, p_all_h, p_all_a)
    # Needs enough scaffold to define a frame; a tiny binder may not have it.
    disp = (rmsd_after(s_ca_h, s_ca_a, p_ca_h, p_ca_a)
            if s_ca_h is not None and len(s_ca_h) >= 3 and p_ca_h is not None
            else float("nan"))
    global_ca = kabsch(a_ca_h, a_ca_a)[0]

    apo_pocket_b = [ab[ai[k]] for k in shared
                    if k.resnum in pset and k.atom == "CA"]
    apo_all_b = [ab[ai[k]] for k in shared if k.atom == "CA"]

    return Preorg(
        preorg_rmsd=round(preorg, 3),
        pocket_displacement=round(disp, 3) if disp == disp else float("nan"),
        global_ca_rmsd=round(global_ca, 3),
        apo_pocket_plddt=(round(float(np.mean(apo_pocket_b)), 2)
                          if apo_pocket_b else float("nan")),
        apo_global_plddt=(round(float(np.mean(apo_all_b)), 2)
                          if apo_all_b else float("nan")),
        n_pocket_residues=len(pset),
        n_pocket_atoms=len(p_all_h) if p_all_h is not None else 0,
    )
