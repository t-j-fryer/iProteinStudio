#!/usr/bin/env python3
"""Work out what a small molecule actually looks like before designing against it.

Handing RFdiffusion3 one arbitrary conformer of a flexible ligand is a silent
failure mode: the run succeeds, the numbers look fine, and the pocket was built
around a geometry the molecule may rarely adopt. This module turns a SMILES
string into an evidence-based recommendation instead.

What it does, in order:

1. **Chemistry QA** — unspecified stereocentres, formal charge, tautomer risk,
   atoms the force fields have no parameters for. Reported, never silently fixed.
2. **Recognition core vs presentation region** — for a conjugated ligand, the
   linker's flexibility is irrelevant to binder design and actively harmful if it
   is allowed to dominate conformer clustering. A BG-PEG4-DBCO conjugate has ~15
   rotatable bonds, of which maybe 3 matter.
3. **Conformer ensemble** — ETKDGv3 with a count scaled to the *core* rotatable
   bonds, MMFF94s minimisation with a UFF fallback, energy filtering.
4. **Clustering on core heavy atoms**, so PEG thrashing does not read as
   conformational diversity.
5. **Experimental evidence** — RCSB chemical search for the exact molecular
   graph, then the observed bound geometry of every instance, clustered the same
   way. Seventeen unrelated proteins agreeing on one geometry is far better
   evidence than any force field.
6. **A recommendation** — which states to design against, and how to split the
   design budget between them.

Force-field energies are used to rank and to discard obviously strained
geometries. They are **not** solution free energies and are never presented as
Boltzmann populations.

Usage:  ligand_intelligence.py request.json
Output: one JSON object on stdout. Errors: {"error": "..."} and exit 1.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

RCSB_SEARCH = "https://search.rcsb.org/rcsbsearch/v2/query"
RCSB_MODELS = "https://models.rcsb.org/v1"


def fail(message: str) -> None:
    print(json.dumps({"error": message}))
    sys.exit(1)


# ----------------------------------------------------------------- chemistry --

def load_molecule(req: dict):
    from rdkit import Chem

    smiles = (req.get("smiles") or "").strip()
    if not smiles:
        fail("No SMILES supplied.")
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        fail("That SMILES could not be parsed. Check for a typo or unbalanced brackets.")
    return mol


def canonical_atom_names(mol) -> list[str]:
    """RFD3 component names in original SMILES atom order."""
    from rdkit import Chem

    mol_h = Chem.AddHs(mol)
    ranks = list(Chem.CanonicalRankAtoms(mol_h))
    return [f"{atom.GetSymbol().upper()}{ranks[atom.GetIdx()] + 1}"
            for atom in mol.GetAtoms()]


def chemistry_qa(mol) -> list[dict]:
    """Everything a non-expert would want to be told before spending GPU hours."""
    from rdkit import Chem
    from rdkit.Chem import Descriptors, rdMolDescriptors

    notes: list[dict] = []

    unspecified = Chem.FindMolChiralCenters(mol, includeUnassigned=True, useLegacyImplementation=False)
    unassigned = [idx for idx, tag in unspecified if tag == "?"]
    if unassigned:
        notes.append({
            "level": "warning",
            "title": f"{len(unassigned)} unspecified stereocentre{'s' if len(unassigned) > 1 else ''}",
            "detail": "The design will use one arbitrary configuration. If the stereochemistry "
                      "matters for binding, write it into the SMILES.",
        })

    charge = Chem.GetFormalCharge(mol)
    if charge != 0:
        notes.append({
            "level": "info",
            "title": f"Net charge {charge:+d}",
            "detail": "Charge is taken from the SMILES exactly as written, so it encodes the "
                      "protonation state you will get. Change the SMILES to change it.",
        })

    # Tautomer risk: an enumerator that finds alternatives means hydrogen-bond
    # donors and acceptors could be assigned differently than intended.
    try:
        from rdkit.Chem.MolStandardize import rdMolStandardize
        enumerator = rdMolStandardize.TautomerEnumerator()
        enumerator.SetMaxTautomers(16)
        n_taut = len(enumerator.Enumerate(mol))
        if n_taut > 1:
            notes.append({
                "level": "warning",
                "title": f"{n_taut} plausible tautomers",
                "detail": "Which tautomer you supply decides which atoms donate and accept "
                          "hydrogen bonds, and therefore what pocket gets designed.",
            })
    except Exception:
        pass

    elements = {a.GetSymbol() for a in mol.GetAtoms()}
    exotic = elements - {"C", "N", "O", "S", "P", "F", "Cl", "Br", "I", "H"}
    if exotic:
        notes.append({
            "level": "warning",
            "title": f"Unusual element{'s' if len(exotic) > 1 else ''}: {', '.join(sorted(exotic))}",
            "detail": "MMFF may have no parameters for these; the slower, cruder UFF force "
                      "field will be used instead and the energies will be less reliable.",
        })

    mw = Descriptors.MolWt(mol)
    if mw > 900:
        notes.append({
            "level": "info",
            "title": f"Large molecule ({mw:.0f} Da)",
            "detail": "Big ligands make big pockets, which need longer binders and more "
                      "sampling to get right.",
        })
    if rdMolDescriptors.CalcNumHeavyAtoms(mol) < 6:
        notes.append({
            "level": "warning",
            "title": "Very small molecule",
            "detail": "There is little surface to build a pocket against, so binders will "
                      "tend to be weak and non-selective.",
        })
    return notes


# --------------------------------------------------- recognition core / linker --

def split_core_and_presentation(mol, core_atom: int | None,
                                linker_atom: int | None) -> tuple[set[int], set[int], str]:
    """Split an explicitly directed core→linker bond.

    One atom is not enough to identify a linker: every non-terminal atom has two
    or more possible sides, and choosing the largest branch can mislabel the
    recognition core.  The UI therefore records both ends of one acyclic bond.
    The side reached from ``linker_atom`` after cutting that bond is presentation;
    the side containing ``core_atom`` remains recognition core.
    """
    heavy = {a.GetIdx() for a in mol.GetAtoms()}
    if core_atom is None and linker_atom is None:
        return heavy, set(), "whole molecule (no linker specified)"
    if core_atom is None or linker_atom is None:
        raise ValueError("Choose both ends of the core-to-linker bond, or mark the molecule as free.")
    if core_atom not in heavy or linker_atom not in heavy:
        raise ValueError("The selected core-to-linker bond contains an atom that is not in this molecule.")
    bond = mol.GetBondBetweenAtoms(core_atom, linker_atom)
    if bond is None:
        raise ValueError("The selected core and linker atoms are not directly bonded.")
    if bond.IsInRing():
        raise ValueError("A ring bond cannot separate a linker. Choose an acyclic bond leaving the binding core.")

    presentation = reachable_without(mol, start=linker_atom, blocked=core_atom)
    if core_atom in presentation or not presentation:
        raise ValueError("That bond does not separate a linker side from the binding core.")
    core = heavy - presentation
    if not core or core_atom not in core:
        raise ValueError("That bond leaves no binding core. Reverse the bond direction.")
    return core, presentation, "explicit core-to-linker bond"


def reachable_without(mol, start: int, blocked: int) -> set[int]:
    seen = {start}
    stack = [start]
    while stack:
        idx = stack.pop()
        for nb in mol.GetAtomWithIdx(idx).GetNeighbors():
            j = nb.GetIdx()
            if j == blocked or j in seen:
                continue
            seen.add(j)
            stack.append(j)
    return seen


def rotatable_bonds(mol, restrict_to: set[int] | None = None) -> int:
    from rdkit import Chem
    pattern = Chem.MolFromSmarts("[!$(*#*)&!D1]-&!@[!$(*#*)&!D1]")
    count = 0
    for a, b in mol.GetSubstructMatches(pattern):
        if restrict_to is None or (a in restrict_to and b in restrict_to):
            count += 1
    return count


def conformer_budget(core_rotatable: int) -> int:
    """More sampling only where it can pay for itself."""
    if core_rotatable <= 1:
        return 20
    if core_rotatable <= 3:
        return 50
    if core_rotatable <= 6:
        return 100
    return 200


# ------------------------------------------------------------------ ensemble --

def generate_ensemble(mol, n_conformers: int, seed: int = 20260811):
    """ETKDGv3 embedding, force-field minimisation, energies."""
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol_h = Chem.AddHs(mol)
    params = AllChem.ETKDGv3()
    params.randomSeed = seed
    params.pruneRmsThresh = 0.25       # drop near-duplicates during embedding
    params.useSmallRingTorsions = True
    params.numThreads = 0

    ids = AllChem.EmbedMultipleConfs(mol_h, numConfs=n_conformers, params=params)
    if not ids:
        params.useRandomCoords = True
        ids = AllChem.EmbedMultipleConfs(mol_h, numConfs=n_conformers, params=params)
    if not ids:
        fail("No 3D conformer could be generated for this molecule. Supply an SDF or PDB instead.")

    field = "MMFF94s"
    try:
        if AllChem.MMFFHasAllMoleculeParams(mol_h):
            results = AllChem.MMFFOptimizeMoleculeConfs(mol_h, maxIters=800, mmffVariant="MMFF94s",
                                                        numThreads=0)
        else:
            raise ValueError("no MMFF parameters")
    except Exception:
        field = "UFF"
        results = AllChem.UFFOptimizeMoleculeConfs(mol_h, maxIters=800, numThreads=0)

    energies = []
    for conf_id, (converged, energy) in zip(ids, results):
        if math.isnan(energy) or math.isinf(energy):
            continue
        energies.append((int(conf_id), float(energy), int(converged) == 0))
    if not energies:
        fail("Every conformer failed to minimise. Supply an experimental structure instead.")
    return Chem.RemoveHs(mol_h), energies, field


def strain_window(core_rotatable: int) -> float:
    """How far above the best conformer is still worth keeping.

    A fixed window does not survive contact with real ligands: MMFF energies for
    a charged, floppy molecule like ATP span tens of kcal/mol on intramolecular
    electrostatics alone, and a 10 kcal/mol cut discarded 187 of 200 conformers.
    Scaling with flexibility keeps the filter doing its actual job -- removing
    obvious strain -- without pretending to resolve populations.
    """
    return min(30.0, 10.0 + 2.0 * core_rotatable)


def filter_by_strain(energies: list[tuple[int, float, bool]], window: float = 10.0):
    """Discard geometries far above the best one found.

    The window is generous on purpose. It is there to remove obvious strain, not
    to make a claim about populations -- a force field cannot support that.
    """
    best = min(e for _, e, _ in energies)
    kept = [(cid, e - best, ok) for cid, e, ok in energies if (e - best) <= window]
    return sorted(kept, key=lambda x: x[1]), best


# ---------------------------------------------------------------- clustering --

def core_rmsd_matrix(mol, conf_ids: list[int], core: set[int]):
    """Symmetry-aware RMSD over the recognition core only."""
    import numpy as np
    from rdkit.Chem import rdMolAlign

    atom_map_ids = sorted(core)
    n = len(conf_ids)
    matrix = np.zeros((n, n), dtype=float)
    for i in range(n):
        for j in range(i + 1, n):
            rmsd = rdMolAlign.GetBestRMS(mol, mol, prbId=conf_ids[i], refId=conf_ids[j],
                                         map=[[(a, a) for a in atom_map_ids]])
            matrix[i, j] = matrix[j, i] = rmsd
    return matrix


def butina_cluster(matrix, threshold: float) -> list[list[int]]:
    """Butina clustering — no sklearn needed, and deterministic."""
    from rdkit.ML.Cluster import Butina
    n = matrix.shape[0]
    if n <= 1:
        return [[0]] if n == 1 else []
    flat = [matrix[i, j] for i in range(1, n) for j in range(i)]
    clusters = Butina.ClusterData(flat, n, threshold, isDistData=True, reordering=True)
    return [list(c) for c in clusters]


def cluster_adaptively(matrix, max_states: int, start: float = 0.75):
    """Loosen the RMSD threshold until the ensemble collapses into usable states.

    A single fixed threshold does not work across ligands. At 1.0 A, ATP produced
    thirteen clusters from thirteen conformers -- every geometry its own state,
    which is the same as no clustering at all and gives the user nothing to
    choose between. Widening until the count is manageable produces states that
    are genuinely distinct at the resolution a designed pocket cares about.

    The threshold that was actually used is reported, because it changes what
    "distinct conformation" means and the user is entitled to know.
    """
    ladder = [start, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0]
    clusters = butina_cluster(matrix, ladder[0])
    used = ladder[0]
    for threshold in ladder:
        candidate = butina_cluster(matrix, threshold)
        clusters, used = candidate, threshold
        # Two states per slot we can actually recommend leaves room to discard
        # the strained and the rare without ending up with nothing.
        if len(candidate) <= max(2, max_states * 2):
            break
    return clusters, used


# ------------------------------------------------------- experimental evidence --

def rcsb_chemical_search(smiles: str, timeout: float) -> list[str]:
    """All CCD codes whose molecular graph matches this SMILES.

    RCSB paginates chemical searches.  A stereochemically rich graph may have
    many CCD variants, so examining only the first page can miss the exact
    molecule.  Retrieve every page and let :func:`confirm_identical_ccds`
    perform the full identity check.
    """
    import requests

    page_size = 100
    start = 0
    identifiers: list[str] = []
    seen: set[str] = set()
    while True:
        body = {
            "query": {"type": "terminal", "service": "chemical", "parameters": {
                "value": smiles, "type": "descriptor", "descriptor_type": "SMILES",
                "match_type": "graph-strict"}},
            "return_type": "mol_definition",
            "request_options": {"paginate": {"start": start, "rows": page_size}},
        }
        response = requests.post(RCSB_SEARCH, json=body, timeout=timeout)
        if response.status_code == 204:
            break
        if response.status_code != 200:
            raise RuntimeError(f"RCSB chemical search returned HTTP {response.status_code}")
        payload = response.json()
        rows = payload.get("result_set", [])
        count_before_page = len(identifiers)
        for row in rows:
            identifier = row.get("identifier")
            if identifier and identifier not in seen:
                seen.add(identifier)
                identifiers.append(identifier)

        start += len(rows)
        raw_total = payload.get("total_count")
        try:
            total = int(raw_total) if raw_total is not None else None
        except (TypeError, ValueError):
            total = None
        if not rows or len(identifiers) == count_before_page or (
                total is not None and start >= total) or (
                total is None and len(rows) < page_size):
            break
    return identifiers


def confirm_identical_ccds(candidates: list[str], query_mol, timeout: float) -> list[str]:
    """Keep only the components that really are this molecule.

    Graph-strict search can return stereoisomers and differently protonated
    variants. Full InChIKey equality preserves connectivity, stereochemistry
    and protonation. Every candidate is checked: result order and page size are
    not chemical identity guarantees.
    """
    import requests
    from rdkit import Chem

    try:
        want = Chem.MolToInchiKey(query_mol)
    except Exception:
        want = None
    if not want:
        raise RuntimeError("Exact chemical identity could not be computed for this ligand")

    confirmed = []
    unverified: list[str] = []
    for code in candidates:
        try:
            response = requests.get(
                f"https://data.rcsb.org/rest/v1/core/chemcomp/{code}", timeout=timeout)
            if response.status_code != 200:
                unverified.append(code)
                continue
            descriptors = response.json().get("rcsb_chem_comp_descriptor", {})
            key = descriptors.get("InChIKey") or descriptors.get("in_ch_i_key")
            if not key:
                unverified.append(code)
                continue
            if key and key.upper() == want.upper():
                confirmed.append(code)
        except Exception:
            unverified.append(code)
            continue
    if unverified:
        raise RuntimeError(
            f"Exact identity could not be verified for {len(unverified)} RCSB candidate(s)")
    return confirmed


def rcsb_entries_for_ccd(ccd: str, limit: int, timeout: float) -> list[str]:
    import requests
    body = {
        "query": {"type": "terminal", "service": "text_chem", "parameters": {
            "attribute": "rcsb_chem_comp_container_identifiers.comp_id",
            "operator": "exact_match", "value": ccd}},
        "return_type": "entry",
        "request_options": {"paginate": {"start": 0, "rows": limit}},
    }
    response = requests.post(RCSB_SEARCH, json=body, timeout=timeout)
    if response.status_code != 200:
        raise RuntimeError(f"RCSB entry search returned HTTP {response.status_code}")
    return [row["identifier"] for row in response.json().get("result_set", [])]


def fetch_ligand_instance(entry: str, ccd: str, timeout: float):
    """The ligand as actually observed in one structure."""
    import requests
    from rdkit import Chem
    url = f"{RCSB_MODELS}/{entry.lower()}/ligand?label_comp_id={ccd}&encoding=sdf"
    try:
        response = requests.get(url, timeout=timeout)
    except Exception:
        return None
    if response.status_code != 200 or not response.text.strip():
        return None
    # sanitize=False first: deposited ligands routinely fail strict valence
    # checks, and losing them all would quietly turn the experimental-evidence
    # feature into a no-op.
    mol = Chem.MolFromMolBlock(response.text, removeHs=True, sanitize=False)
    if mol is None or mol.GetNumAtoms() == 0:
        return None
    try:
        Chem.SanitizeMol(mol, Chem.SanitizeFlags.SANITIZE_ALL
                         ^ Chem.SanitizeFlags.SANITIZE_PROPERTIES)
    except Exception:
        return None
    return mol


def experimental_conformers(smiles: str, cfg: dict) -> dict:
    """Search the PDB for this exact molecule and collect its observed geometries."""
    timeout = float(cfg.get("network_timeout", 25))
    max_entries = int(cfg.get("max_pdb_entries", 30))
    result = {"searched": True, "ccd_codes": [], "n_entries": 0, "instances": [], "note": ""}

    try:
        from rdkit import Chem
        query_mol = Chem.MolFromSmiles(smiles)
        codes = confirm_identical_ccds(rcsb_chemical_search(smiles, timeout), query_mol, timeout)
    except Exception as exc:
        result["searched"] = False
        result["note"] = f"The PDB could not be searched ({exc.__class__.__name__}). Working from computation alone."
        return result

    result["ccd_codes"] = codes
    if not codes:
        result["note"] = "No exact match for this molecule in the PDB."
        return result

    seen_entries: set[str] = set()
    failed_entry_searches = 0
    for ccd in codes:
        remaining = max_entries - len(seen_entries)
        if remaining <= 0:
            break
        try:
            entries = rcsb_entries_for_ccd(ccd, remaining, timeout)
        except Exception:
            failed_entry_searches += 1
            continue
        for entry in entries:
            if entry in seen_entries:
                continue
            seen_entries.add(entry)
            mol = fetch_ligand_instance(entry, ccd, timeout)
            if mol is not None:
                result["instances"].append({"entry": entry, "ccd": ccd, "mol": mol})
            if len(seen_entries) >= max_entries:
                break
    result["n_entries"] = len(seen_entries)

    if failed_entry_searches:
        result["searched"] = False
        result["note"] = (
            f"Entry search failed for {failed_entry_searches} exact PDB component"
            f"{'s' if failed_entry_searches != 1 else ''}; experimental evidence is incomplete."
        )
    elif not result["instances"] and result["n_entries"]:
        result["note"] = ("This exact molecule appears in the PDB, but its coordinates could not be "
                          "retrieved. Working from computation alone.")
    elif not result["instances"] and codes:
        result["note"] = ("An exact Chemical Component Dictionary match exists, but no PDB entries "
                          "containing it were returned. Working from computation alone.")
    elif len(result["instances"]) < result["n_entries"]:
        result["note"] = (
            f"Retrieved coordinates for {len(result['instances'])} of {result['n_entries']} "
            "sampled PDB entries; experimental evidence is incomplete."
        )
    return result


def match_experimental_to_clusters(mol, conf_ids, clusters, core, instances,
                                  match_cutoff: float = 1.5) -> dict:
    """Attach PDB entries to whichever computed cluster they most resemble.

    Matching is by core-atom RMSD after a symmetry-aware alignment. Instances that
    do not resemble any computed cluster are reported separately rather than being
    forced into the nearest one.
    """
    from rdkit import Chem
    from rdkit.Chem import AllChem, rdMolAlign

    support: dict = {i: [] for i in range(len(clusters))}
    if not instances:
        return support

    template = Chem.Mol(mol)
    core_ordered = sorted(core)
    matched, unmatched = 0, 0

    for inst in instances:
        probe = inst["mol"]
        if probe.GetNumAtoms() != template.GetNumAtoms():
            unmatched += 1
            continue
        # A deposited SDF carries coordinates but unreliable bond orders, so it
        # will not substructure-match the SMILES-derived template as-is. Imposing
        # the template's bond orders is what makes the comparison possible at all
        # -- without it every RMSD call raises and the PDB evidence silently
        # disappears, which is exactly what happened the first time.
        try:
            probe = AllChem.AssignBondOrdersFromTemplate(template, probe)
        except Exception:
            unmatched += 1
            continue

        pairs = probe.GetSubstructMatch(template)
        if not pairs or len(pairs) != template.GetNumAtoms():
            unmatched += 1
            continue
        atom_map = [[(pairs[a], a)] for a in core_ordered]
        flat_map = [pair for group in atom_map for pair in group]

        best_cluster, best_rmsd = None, float("inf")
        for ci, members in enumerate(clusters):
            for member in members[:3]:      # a few members, not just one
                ref_conf = conf_ids[member]
                try:
                    rmsd = rdMolAlign.GetBestRMS(probe, template, refId=ref_conf, map=[flat_map])
                except Exception:
                    continue
                if rmsd < best_rmsd:
                    best_rmsd, best_cluster = rmsd, ci
        if best_cluster is not None and best_rmsd <= match_cutoff:
            support[best_cluster].append(inst["entry"])
            matched += 1
        else:
            unmatched += 1

    support["_matched"] = matched
    support["_unmatched"] = unmatched
    return support


# ------------------------------------------------------------ recommendation --

def classify_flexibility(n_states: int, core_rot: int) -> tuple[str, str]:
    if n_states <= 1 or core_rot <= 1:
        return "low", ("The part that matters for binding is essentially rigid, so one "
                       "geometry is enough.")
    if n_states <= 3:
        return "moderate", ("The binding core has a few distinct shapes. Designing against "
                            "two or three of them is worth the extra time.")
    return "high", ("The binding core adopts many shapes. Designing against a single "
                    "arbitrary one is a real risk — either spread the budget across "
                    "several, or pick a smaller recognition core.")


def allocate(states: list[dict]) -> list[dict]:
    """Split the design budget across the recommended states.

    Weighted by how common each state is in the ensemble and, much more heavily,
    by whether anyone has actually observed it. A geometry seen in fourteen
    unrelated crystal structures deserves more of the budget than a force field's
    opinion.
    """
    chosen = [s for s in states if s["recommended"]]
    if not chosen:
        return []
    weights = []
    for state in chosen:
        weight = max(state["ensemble_fraction"], 0.05)
        if state["pdb_entries"]:
            weight *= 1.0 + min(2.0, math.log1p(len(state["pdb_entries"])))
        weights.append(weight)
    total = sum(weights)
    shares = [w / total for w in weights]
    # Round to whole percent, then put the rounding error on the largest share.
    percents = [int(round(s * 100)) for s in shares]
    drift = 100 - sum(percents)
    percents[percents.index(max(percents))] += drift
    for state, percent in zip(chosen, percents):
        state["share"] = percent
    return chosen


# -------------------------------------------------------------------- driver --

def main() -> None:
    if len(sys.argv) < 2:
        fail("No request file given.")
    try:
        req = json.loads(Path(sys.argv[1]).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"Could not read the request: {exc}")

    from rdkit import Chem
    from rdkit import RDLogger
    RDLogger.DisableLog("rdApp.*")

    mol = load_molecule(req)
    smiles = Chem.MolToSmiles(mol)
    notes = chemistry_qa(mol)

    attachment = req.get("attachment_atom")
    attachment = int(attachment) if attachment is not None else None
    linker_atom = req.get("attachment_linker_atom")
    linker_atom = int(linker_atom) if linker_atom is not None else None

    # The picker and this script both index atoms by SMILES input order, which
    # RDKit preserves. Cross-checking the element makes a numbering mismatch
    # loud instead of silently splitting the molecule in the wrong place.
    expected_symbol = req.get("attachment_symbol")
    if attachment is not None and expected_symbol:
        if attachment >= mol.GetNumAtoms():
            fail(f"Atom {attachment} does not exist in this molecule.")
        actual = mol.GetAtomWithIdx(attachment).GetSymbol().upper()
        if actual != str(expected_symbol).upper():
            fail(f"The atom you picked reads as {expected_symbol} in the picture but "
                 f"{actual} here, so the numbering does not line up. Re-enter the SMILES.")
    expected_linker_symbol = req.get("attachment_linker_symbol")
    if linker_atom is not None and expected_linker_symbol:
        if linker_atom >= mol.GetNumAtoms():
            fail(f"Atom {linker_atom} does not exist in this molecule.")
        actual = mol.GetAtomWithIdx(linker_atom).GetSymbol().upper()
        if actual != str(expected_linker_symbol).upper():
            fail(f"The linker atom reads as {expected_linker_symbol} in the picture but "
                 f"{actual} here, so the numbering does not line up. Re-enter the SMILES.")
    try:
        core, presentation, split_rule = split_core_and_presentation(
            mol, attachment, linker_atom)
    except ValueError as exc:
        fail(str(exc))

    total_rot = rotatable_bonds(mol)
    core_rot = rotatable_bonds(mol, restrict_to=core)
    if presentation and total_rot > core_rot:
        notes.append({
            "level": "info",
            "title": f"{total_rot - core_rot} of {total_rot} rotatable bonds are in the linker",
            "detail": "Those are ignored when judging flexibility. A thrashing PEG tail is not "
                      "conformational diversity that matters for binding.",
        })

    budget = conformer_budget(core_rot)
    ensemble, energies, field = generate_ensemble(mol, budget)
    kept, _ = filter_by_strain(energies, window=strain_window(core_rot))
    conf_ids = [cid for cid, _, _ in kept]
    rel_energy = {cid: rel for cid, rel, _ in kept}

    # Cluster on the core only. 1.0 A is loose enough to merge cosmetic
    # differences and tight enough to separate genuinely different shapes.
    matrix = core_rmsd_matrix(ensemble, conf_ids, core)
    max_states = int(req.get("max_states", 4))
    if req.get("cluster_rmsd"):
        clusters = butina_cluster(matrix, threshold=float(req["cluster_rmsd"]))
        cluster_threshold = float(req["cluster_rmsd"])
    else:
        clusters, cluster_threshold = cluster_adaptively(matrix, max_states)

    pdb = experimental_conformers(smiles, req) if req.get("search_pdb", True) else \
        {"searched": False, "ccd_codes": [], "n_entries": 0, "instances": [],
         "note": "PDB search was switched off."}
    support = match_experimental_to_clusters(ensemble, conf_ids, clusters, core, pdb["instances"],
                                            match_cutoff=max(1.5, cluster_threshold))
    if pdb["instances"] and support.get("_matched", 0) == 0 and not pdb["note"]:
        pdb["note"] = (
            f"Found {len(pdb['instances'])} exact experimental ligand structure(s), "
            "but none matched a generated conformational state within the RMSD cutoff."
        )

    total_members = sum(len(c) for c in clusters) or 1
    states: list[dict] = []
    for index, members in enumerate(clusters):
        # Represent each cluster by its *lowest-energy* member, not by Butina's
        # centroid. The centroid is the most central geometry, which is not the
        # one you would want to design against, and reporting its energy makes
        # every cluster look strained.
        representative = min((conf_ids[m] for m in members),
                             key=lambda cid: rel_energy.get(cid, float("inf")))
        entries = support.get(index, [])
        states.append({
            "id": chr(ord("A") + index),
            "conformer_id": representative,
            "n_members": len(members),
            "ensemble_fraction": len(members) / total_members,
            "relative_energy": round(rel_energy.get(representative, 0.0), 2),
            "pdb_entries": entries,
            "recommended": False,
            "share": 0,
        })

    # Recommend: anything with experimental support, plus low-energy, well-
    # populated computed states, capped so the budget is not spread too thin.
    # Experimental support first, then how much of the ensemble a state accounts
    # for, then strain. Population beats a marginally lower force-field energy:
    # the energies are not accurate enough to order states that close together.
    ranked = sorted(states, key=lambda s: (-len(s["pdb_entries"]), -s["n_members"], s["relative_energy"]))
    for state in ranked[:max_states]:
        strained = state["relative_energy"] > 6.0
        rare = state["ensemble_fraction"] < 0.05
        if state["pdb_entries"] or not (strained and rare):
            state["recommended"] = True
    if not any(s["recommended"] for s in states) and states:
        ranked[0]["recommended"] = True
    allocate(states)

    level, rationale = classify_flexibility(sum(1 for s in states if s["recommended"]), core_rot)

    # Write the chosen geometries where the campaign can pick them up.
    out_dir = Path(req.get("output_dir") or ".").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    for state in states:
        if not state["recommended"]:
            continue
        path = out_dir / f"conformer_{state['id']}.sdf"
        writer = Chem.SDWriter(str(path))
        writer.write(ensemble, confId=state["conformer_id"])
        writer.close()
        state["sdf"] = str(path)

    print(json.dumps({
        "smiles": smiles,
        "atom_names": canonical_atom_names(mol),
        "force_field": field,
        "qa": notes,
        "core": {
            "core_atoms": sorted(core),
            "presentation_atoms": sorted(presentation),
            "rule": split_rule,
            "core_rotatable_bonds": core_rot,
            "total_rotatable_bonds": total_rot,
        },
        "ensemble": {
            "requested": budget,
            "kept_after_strain_filter": len(conf_ids),
            "strain_window_kcal": round(strain_window(core_rot), 1),
            "cluster_rmsd_used": round(cluster_threshold, 2),
            "clusters": len(clusters),
        },
        "pdb": {
            "searched": pdb["searched"],
            "ccd_codes": pdb["ccd_codes"],
            "n_entries": pdb["n_entries"],
            "n_instances_used": len(pdb["instances"]),
            "n_instances_matched": support.get("_matched", 0),
            "n_instances_unmatched": support.get("_unmatched", 0),
            "note": pdb["note"],
        },
        "flexibility": {"level": level, "rationale": rationale},
        "states": states,
    }))


if __name__ == "__main__":
    main()
