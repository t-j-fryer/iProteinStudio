#!/usr/bin/env python3
"""Deterministic solvent-surface ORI placement for protein binder campaigns.

Foundry's ``ori_token`` is a spatial starting centre, not a request to search a
whole target.  A fixed protein's centre of mass is commonly buried, so Studio
creates explicit centres outside solvent-accessible patches and records every
one in the campaign manifest.  Residues used for ``surface_patch`` are only
geometric anchors; this module never creates ``select_hotspots`` conditioning.
"""

from __future__ import annotations

import math
from pathlib import Path


PROBE_RADIUS = 1.4
MIN_RESIDUE_SASA = 15.0
PATCH_RADIUS = 9.0
REGION_RADIUS = 12.0
ORI_OFFSET = 10.0
MIN_ORI_CLEARANCE = 4.0
AREA_PER_ORIGIN = 500.0
DESIGNS_PER_ORIGIN = 5
MAX_ORIGINS = 32


def _structure(path: str | Path, chains: list[str]):
    try:
        import numpy as np
        import biotite.structure as struc
        from biotite.structure.io.pdb import PDBFile
    except ImportError as exc:  # RFD3's managed environment includes both
        raise ValueError("Surface placement requires the managed RFdiffusion3 Biotite environment.") from exc

    source = Path(path)
    try:
        array = PDBFile.read(source).get_structure(model=1)
    except Exception as exc:
        raise ValueError(f"Could not read the normalized protein target: {exc}") from exc
    chain_mask = np.isin(array.chain_id, np.asarray(chains))
    heavy = array[chain_mask & ~array.hetero & (array.element != "H")]
    if heavy.array_length() == 0:
        raise ValueError("The selected target chains contain no protein heavy atoms.")
    try:
        sasa = struc.sasa(heavy, probe_radius=PROBE_RADIUS, point_number=500)
    except Exception as exc:
        raise ValueError(f"Could not calculate the target solvent-accessible surface: {exc}") from exc
    return np, heavy, np.nan_to_num(sasa, nan=0.0)


def _surface_residues(path: str | Path, chains: list[str]):
    np, atoms, atom_sasa = _structure(path, chains)
    all_xyz = np.asarray(atoms.coord, dtype=float)
    protein_com = all_xyz.mean(axis=0)
    residues = []
    keys = sorted(set(zip(atoms.chain_id.tolist(), atoms.res_id.tolist())))
    for chain, number in keys:
        mask = (atoms.chain_id == chain) & (atoms.res_id == number)
        area = float(atom_sasa[mask].sum())
        if area < MIN_RESIDUE_SASA:
            continue
        exposed = atom_sasa[mask] > 0
        xyz = np.asarray(atoms.coord[mask], dtype=float)
        weights = np.asarray(atom_sasa[mask], dtype=float)
        if exposed.any() and weights.sum() > 0:
            representative = np.average(xyz[exposed], axis=0, weights=weights[exposed])
        else:
            representative = xyz.mean(axis=0)
        residues.append({
            "key": f"{chain}{int(number)}",
            "coord": representative,
            "sasa": area,
        })
    if not residues:
        raise ValueError("No solvent-accessible target residues were found; check the selected chains and structure.")
    return np, all_xyz, protein_com, residues


def _normal(np, points, centre, protein_com):
    """Local PCA normal, signed away from the protein interior."""
    points = np.asarray(points, dtype=float)
    radial = centre - protein_com
    radial_norm = float(np.linalg.norm(radial))
    radial = radial / radial_norm if radial_norm > 1e-8 else np.asarray([0.0, 0.0, 1.0])
    if len(points) >= 3:
        covariance = np.cov((points - points.mean(axis=0)).T)
        values, vectors = np.linalg.eigh(covariance)
        normal = vectors[:, int(np.argmin(values))]
        if float(np.dot(normal, radial)) < 0:
            normal = -normal
        # Nearly spherical/noisy local neighbourhoods can produce an unstable
        # PCA axis. Blend with the outward direction while preserving the local
        # surface orientation.
        normal = normal + 0.35 * radial
        length = float(np.linalg.norm(normal))
        if length > 1e-8:
            return normal / length
    return radial


def _safe_origin(np, surface_centre, normal, all_xyz):
    """Move outward until the origin clears all target atoms."""
    for offset in (ORI_OFFSET, 12.0, 14.0, 16.0, 18.0):
        ori = surface_centre + offset * normal
        clearance = float(np.linalg.norm(all_xyz - ori, axis=1).min())
        if clearance >= MIN_ORI_CLEARANCE:
            return ori, clearance, offset
    return None


def _candidates(path: str | Path, chains: list[str]):
    np, all_xyz, protein_com, residues = _surface_residues(path, chains)
    reps = np.asarray([residue["coord"] for residue in residues], dtype=float)
    candidates = []
    for index, residue in enumerate(residues):
        distances = np.linalg.norm(reps - residue["coord"], axis=1)
        neighbours = np.where(distances <= PATCH_RADIUS)[0]
        patch = [residues[int(i)] for i in neighbours]
        weights = np.asarray([item["sasa"] for item in patch], dtype=float)
        points = np.asarray([item["coord"] for item in patch], dtype=float)
        centre = np.average(points, axis=0, weights=weights)
        normal = _normal(np, points, centre, protein_com)
        safe = _safe_origin(np, centre, normal, all_xyz)
        if safe is None:
            # Concave local PCA normals can point through another lobe. A radial
            # retry is deterministic and still places the token outside.
            normal = _normal(np, [], centre, protein_com)
            safe = _safe_origin(np, centre, normal, all_xyz)
        if safe is None:
            continue
        ori, clearance, offset = safe
        candidates.append({
            "centre": centre,
            "ori": ori,
            "clearance": clearance,
            "offset": offset,
            "patch_sasa": float(weights.sum()),
            "anchors": sorted(item["key"] for item in patch),
        })
    if not candidates:
        raise ValueError("No unobstructed solvent-surface ORI could be placed around this target.")
    return np, candidates, residues, all_xyz, protein_com


def _serialise(candidate: dict, index: int, mode: str) -> dict:
    return {
        "label": f"{mode}-{index + 1:02d}",
        "xyz": [round(float(value), 3) for value in candidate["ori"]],
        "surface_centre": [round(float(value), 3) for value in candidate["centre"]],
        "anchor_residues": candidate["anchors"],
        "patch_sasa_a2": round(float(candidate["patch_sasa"]), 1),
        "target_clearance_a": round(float(candidate["clearance"]), 2),
        "offset_a": round(float(candidate["offset"]), 1),
        "placement_mode": mode,
    }


def plan_surface_scan(path: str | Path, chains: list[str], num_designs: int) -> list[dict]:
    """Cover the accessible target surface with deterministic farthest points."""
    np, candidates, residues, _all_xyz, _protein_com = _candidates(path, chains)
    total_sasa = sum(item["sasa"] for item in residues)
    # One trajectory is not evidence about a patch. Keep roughly five samples
    # per location (the policy supplied with this feature), while target area
    # and the exact requested budget remain hard upper bounds.
    budget_origins = int(math.ceil(int(num_designs) / DESIGNS_PER_ORIGIN))
    wanted = max(1, min(budget_origins, MAX_ORIGINS,
                        int(math.ceil(total_sasa / AREA_PER_ORIGIN))))
    first = max(range(len(candidates)), key=lambda i: candidates[i]["patch_sasa"])
    chosen = [first]
    centres = np.asarray([item["centre"] for item in candidates], dtype=float)
    while len(chosen) < wanted:
        remaining = [i for i in range(len(candidates)) if i not in chosen]
        if not remaining:
            break
        distances = np.linalg.norm(
            centres[remaining, None, :] - centres[np.asarray(chosen), :][None, :, :], axis=2
        )
        next_index = remaining[int(np.argmax(distances.min(axis=1)))]
        chosen.append(next_index)
    return [_serialise(candidates[index], i, "surface-scan") for i, index in enumerate(chosen)]


def plan_surface_patch(path: str | Path, chains: list[str], selected: list[str]) -> list[dict]:
    """Place one ORI near a broad selected region, without hotspot conditioning."""
    np, candidates, residues, all_xyz, protein_com = _candidates(path, chains)
    residue_by_key = {item["key"]: item for item in residues}
    missing = sorted(set(selected) - set(residue_by_key))
    # A selected residue may itself have little SASA. Locate it from the full
    # structure and use nearby exposed residues instead of silently dropping it.
    if missing:
        _np, atoms, _sasa = _structure(path, chains)
        for key in list(missing):
            chain = key[:1]
            try:
                number = int(key[1:])
            except ValueError:
                continue
            mask = (atoms.chain_id == chain) & (atoms.res_id == number)
            if mask.any():
                residue_by_key[key] = {"key": key, "coord": np.asarray(atoms.coord[mask]).mean(axis=0), "sasa": 1.0}
                missing.remove(key)
    if missing:
        raise ValueError("Broad-region residue(s) are absent from the selected target: " + ", ".join(missing))
    selected_points = np.asarray([residue_by_key[key]["coord"] for key in selected], dtype=float)
    exposed = [item for item in residues if float(
        np.linalg.norm(selected_points - item["coord"], axis=1).min()) <= REGION_RADIUS]
    if not exposed:
        raise ValueError("The broad region has no nearby solvent-accessible residues; select a surface-facing region.")
    weights = np.asarray([item["sasa"] for item in exposed], dtype=float)
    points = np.asarray([item["coord"] for item in exposed], dtype=float)
    centre = np.average(points, axis=0, weights=weights)
    normal = _normal(np, points, centre, protein_com)
    safe = _safe_origin(np, centre, normal, all_xyz)
    if safe is None:
        radial = _normal(np, [], centre, protein_com)
        safe = _safe_origin(np, centre, radial, all_xyz)
    if safe is None:
        raise ValueError("The selected broad region has no unobstructed outward ORI; choose a more exposed region.")
    ori, clearance, offset = safe
    candidate = {
        "centre": centre, "ori": ori, "clearance": clearance, "offset": offset,
        "patch_sasa": float(weights.sum()), "anchors": sorted(set(selected)),
    }
    return [_serialise(candidate, 0, "surface-patch")]
