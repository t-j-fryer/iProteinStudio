#!/usr/bin/env python3
"""Turn a Studio RFdiffusion3 request into a campaign the RFD3 scripts can run.

Studio does not orchestrate RFdiffusion3 itself. The production pipeline lives
in the RFD3 repo and is already validated end to end; this script only prepares
its inputs:

    <campaign>/config/design.yaml      DesignInputSpecification + conditioning
    <campaign>/config/ligand.smi       SMILES (small-molecule campaigns)
    <campaign>/config/campaign.json    the config run_rfd3_nise_campaign.py reads
    <campaign>/assets/ligand/…         generated CCD component + PDB, for SMILES

after which the campaign is launched with the RFD3 repo's own
``launch_rfd3_nise_campaign.py``.

Two details are load-bearing and easy to get wrong:

1. **Do not write `length` into the YAML.** Foundry's ``length`` is the *total*
   component count, not the binder length, so a 65-aa binder against a contig
   carrying a fixed motif needs a larger total. ``design_from_yaml.py`` already
   computes that from the contig; writing our own ``length`` here reintroduces
   exactly the ``No valid selections possible with the given constraints``
   failure that this pipeline was fixed for.

2. **Do not add the ligand twice.** When the ligand is supplied through
   ``input:`` plus ``ligand:``, naming it again in the contig duplicates every
   ligand atom in the Foundry/MLX output. Small-molecule campaigns therefore
   carry no contig at all.

Reads the Studio request as JSON on argv[1]; prints ``PREPOK|<campaign.json>``
on success, or ``PREPFAIL|<reason>`` and exit 1.
"""

from __future__ import annotations

import json
import math
import re
import subprocess
import sys
from pathlib import Path


def fail(message: str) -> None:
    print(f"PREPFAIL|{message}")
    sys.exit(1)


def yaml_quote(value: str) -> str:
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def normalize_protein_target(req: dict, campaign: Path) -> dict[str, str]:
    """Normalize a target, or an existing binder-target complex, safely.

    De-novo mode selects only target chains and reserves A for generated matter.
    Existing-complex modes additionally retain the source binder/motif chain as A.
    """
    from protein_structure import read_protein_atoms, write_selected_pdb

    source_chains = req.get("target_chains") or [value.strip() for value in
                     str(req.get("target_chain", "B")).split(",") if value.strip()]
    if len(source_chains) > 25:
        fail("RFdiffusion3 supports at most 25 target chains because chain A is reserved for the binder.")
    assigned = [chr(ord("B") + index) for index in range(len(source_chains))]
    chain_map = dict(zip(source_chains, assigned))
    mode = req.get("design_mode", "deNovo")
    if mode in {"partialDiffusion", "motifScaffolding"}:
        source_binder = str(req.get("source_binder_chain", "A")).strip().upper()
        if source_binder in chain_map:
            fail("The source binder/motif chain must not also be listed as a fixed target chain.")
        chain_map[source_binder] = "A"
    try:
        normalized = write_selected_pdb(
            req["target_structure"], campaign / "assets" / "target" / "normalized_target.pdb",
            chain_map,
        )
    except (OSError, ValueError) as exc:
        fail(f"Could not normalize the selected protein target chains: {exc}")

    def remap_token(token: str) -> str:
        match = re.fullmatch(r"([^\d\s])(-?\d+)", token.strip())
        if not match or match.group(1) not in chain_map:
            return token
        return f"{chain_map[match.group(1)]}{match.group(2)}"

    req["conditions"] = {
        remap_token(site): values for site, values in req.get("conditions", {}).items()
    }
    req["surface_patch_residues"] = [
        remap_token(str(site)) for site in req.get("surface_patch_residues", [])
    ]
    contig = re.sub(
        r"(?<![A-Za-z0-9])([^\d\s])(?=\d)",
        lambda match: chain_map.get(match.group(1), match.group(1)),
        str(req.get("contig", "")),
    )
    req["contig"] = contig
    req["target_structure"] = str(normalized)
    req["target_chain"] = ",".join(assigned)
    req["target_chains"] = assigned
    atoms = read_protein_atoms(normalized)
    ranges = {}
    for chain in sorted({atom.chain for atom in atoms}):
        ids = sorted({atom.residue_number for atom in atoms if atom.chain == chain})
        if ids:
            ranges[chain] = f"{chain}{ids[0]}-{ids[-1]}"
    req["normalized_chain_ranges"] = ranges
    if mode in {"partialDiffusion", "motifScaffolding"}:
        req["source_binder_chain"] = "A"
        req["source_binder_contig"] = ranges.get("A", "")
        if not req["source_binder_contig"]:
            fail("The selected source binder/motif chain contains no protein residues.")
        req["source_binder_length"] = len({atom.residue_number for atom in atoms if atom.chain == "A"})
        # Motif selections were entered against the user's chain ID; remap them
        # only after the input structure itself has been normalized.
        if mode == "motifScaffolding":
            remapped = {}
            for residue, names in (req.get("motif_sites") or {}).items():
                remapped[remap_token(str(residue))] = names
            req["motif_sites"] = remapped
    return chain_map


def ligand_chain_resnum(pdb_path: Path, resname: str | None) -> str | None:
    """Find the chain+resnum key for the ligand, e.g. 'L1' or 'C1'.

    Selection keys in the design YAML address the ligand this way. Guessing
    wrong means the preflight in design_from_yaml.py rejects the spec, which is
    the intended failure mode -- loudly, in a second, rather than minutes into
    Foundry.
    """
    try:
        for line in pdb_path.read_text(errors="replace").splitlines():
            if not line.startswith("HETATM"):
                continue
            name = line[17:20].strip()
            if resname and name != resname.strip().upper():
                continue
            chain = line[21].strip() or "A"
            return f"{chain}{int(line[22:26])}"
    except (OSError, ValueError):
        return None
    return None


def write_design_yaml(req: dict, campaign: Path, ligand_input: Path | None,
                      selection_key: str | None) -> Path:
    lines = ["# Generated by iProteinStudio. Safe to edit and re-run by hand:",
             "#   .venv/bin/python scripts/design_from_yaml.py <this file> --lengths ...",
             ""]
    name = req["design_name"]
    lines.append(f"{name}:")

    def emit(key: str, value: str) -> None:
        lines.append(f"  {key}: {value}")

    def emit_selection(key: str, atoms: list[str]) -> None:
        if not atoms or not selection_key:
            return
        lines.append(f"  {key}:")
        lines.append(f"    {yaml_quote(selection_key)}: {yaml_quote(','.join(atoms))}")

    mode = req.get("design_mode", "deNovo")
    if req["target_kind"] == "small_molecule":
        if ligand_input is None:
            fail("No ligand structure was produced.")
        emit("input", yaml_quote(str(ligand_input)))
        emit("ligand", yaml_quote(req["component_id"]))
        # No contig: input + ligand already introduce the component. Naming it
        # again duplicates every ligand atom.
    elif mode == "deNovo":
        emit("input", yaml_quote(req["target_structure"]))
        # The complete selected target is fixed and the binder is generated in
        # front of it.  Derive this from the normalized structure rather than
        # asking an API client to know Foundry's comma-delimited contig dialect.
        # A Claude transcript supplied RFdiffusion1-style ``B1-236/0 45-75``;
        # that survived the cheap atom preflight and then failed in fixtures.
        # The canonical form here is ``45-75,/0,B1-236``.
        target_contig = ",/0,".join(req["normalized_chain_ranges"][chain]
                                     for chain in req["target_chains"])
        binder_contig = f"{min(req['lengths'])}-{max(req['lengths'])}"
        emit("contig", yaml_quote(f"{binder_contig},/0,{target_contig}"))
    elif mode == "partialDiffusion":
        emit("input", yaml_quote(req["target_structure"]))
        emit("partial_t", f"{float(req['partial_t']):.6g}")
        lines.append("  select_fixed_atoms:")
        for chain in req["target_chains"]:
            lines.append(f"    {yaml_quote(req['normalized_chain_ranges'][chain])}: {yaml_quote('ALL')}")
        # The source binder sequence remains conditioning during structural
        # perturbation. Optional sequence redesign happens later in MPNN.
    else:  # motifScaffolding
        emit("input", yaml_quote(req["target_structure"]))
        target_contig = ",/0,".join(req["normalized_chain_ranges"][c]
                                     for c in req["target_chains"])
        emit("contig", yaml_quote(f"{req['lengths'][0]}-{req['lengths'][-1]},/0,{target_contig}"))
        residues = list((req.get("motif_sites") or {}).keys())
        emit("unindex", yaml_quote(",".join(residues)))
        lines.append("  select_fixed_atoms:")
        for residue, atoms in sorted(req["motif_sites"].items()):
            lines.append(f"    {yaml_quote(residue)}: {yaml_quote(atoms)}")
        for chain in req["target_chains"]:
            lines.append(f"    {yaml_quote(req['normalized_chain_ranges'][chain])}: {yaml_quote('ALL')}")

    emit("redesign_motif_sidechains", "false")
    if req.get("is_non_loopy") is not None:
        emit("is_non_loopy", "true" if req["is_non_loopy"] else "false")
    # Partial diffusion must retain Foundry's diffused-region COM centering.
    # Applying the de-novo hotspot/origin override here can pull a small binder
    # toward the full target COM and defeats the upstream partial-diffusion fix.
    if mode == "deNovo" and req.get("infer_ori_strategy"):
        emit("infer_ori_strategy", str(req["infer_ori_strategy"]))
    if mode == "deNovo" and req.get("ori_token"):
        emit("ori_token", "[" + ", ".join(f"{v:.3f}" for v in req["ori_token"]) + "]")

    if req["target_kind"] == "small_molecule":
        lines.append("  select_fixed_atoms:")
        # "ALL", not an empty string: the pinned Foundry build treats "" as an
        # empty selection rather than as everything.
        lines.append(f"    {yaml_quote(req['component_id'])}: {yaml_quote('ALL')}")

    conditions = req.get("conditions", {})
    for spec_key, condition in (("select_buried", "buried"),
                                ("select_exposed", "exposed"),
                                ("select_hbond_donor", "hbondDonor"),
                                ("select_hbond_acceptor", "hbondAcceptor"),
                                ("select_hotspots", "hotspot")):
        atoms = sorted(site for site, applied in conditions.items() if condition in applied)
        if condition == "hotspot" and req["target_kind"] == "protein":
            # Protein hotspots are residues addressed directly, not atoms under
            # a ligand key.
            if atoms:
                lines.append("  select_hotspots:")
                for residue in atoms:
                    lines.append(f"    {yaml_quote(residue)}: {yaml_quote('ALL')}")
            continue
        emit_selection(spec_key, atoms)

    path = campaign / "config" / "design.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    return path


def prepare_ligand(req: dict, campaign: Path, rfd3_root: Path) -> tuple[Path, Path]:
    """SMILES -> explicit CCD component + chain-L PDB, via the RFD3 script."""
    spec = {"smiles": req["smiles"]}
    for key, condition in (("exposed", "exposed"), ("buried", "buried"),
                           ("hbond_donor", "hbondDonor"), ("hbond_acceptor", "hbondAcceptor"),
                           ("hotspots", "hotspot")):
        atoms = sorted(site for site, applied in req.get("conditions", {}).items()
                       if condition in applied)
        if atoms:
            spec[key] = {"LIGAND": ",".join(atoms)}

    spec_path = campaign / "config" / "ligand_spec.json"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(json.dumps(spec, indent=2) + "\n")

    out_dir = campaign / "assets" / "ligand"
    log = campaign / "logs" / "prepare_ligand.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(rfd3_root / "scripts" / "prepare_ligand_target.py"),
           "--spec", str(spec_path),
           "--component-id", req["component_id"],
           "--output-dir", str(out_dir),
           "--design-name", req["design_name"],
           "--base-json", str(campaign / "config" / "ligand_base_input.json")]
    with log.open("w") as handle:
        result = subprocess.run(cmd, cwd=rfd3_root, stdout=handle, stderr=subprocess.STDOUT,
                                env={**_env(), "DEBUG": "false"})
    if result.returncode:
        tail = "\n".join(log.read_text(errors="replace").splitlines()[-8:])
        fail(f"Could not build the ligand component.\n{tail}")

    pdb = out_dir / f"{req['component_id'].upper()}.pdb"
    ccd = out_dir / "ccd"
    if not pdb.exists():
        fail(f"Expected a ligand PDB at {pdb}.")
    return pdb, ccd


def conformers_to_pdb(conformers: list[dict], reference_pdb: Path, component_id: str,
                      out_dir: Path) -> list[dict]:
    """Rewrite each chosen conformer as a PDB that matches the generated component.

    The analysis writes conformers as SDF, but Foundry reads PDB/CIF and, more
    importantly, every atom must carry the *same* name as the CCD component the
    campaign generated -- otherwise the conditioning selections address atoms
    that do not exist. So the coordinates are transplanted onto the reference
    PDB's atom order rather than the SDF being handed over directly.
    """
    from rdkit import Chem

    reference = Chem.MolFromPDBFile(str(reference_pdb), removeHs=True, sanitize=False)
    if reference is None:
        fail(f"Could not read the generated ligand PDB at {reference_pdb}.")
    ref_lines = [l for l in reference_pdb.read_text().splitlines() if l.startswith("HETATM")]

    out_dir.mkdir(parents=True, exist_ok=True)
    rewritten = []
    for entry in conformers:
        sdf = Path(entry["path"])
        probe = Chem.MolFromMolFile(str(sdf), removeHs=True, sanitize=False)
        if probe is None:
            fail(f"Could not read the conformer at {sdf}.")
        if probe.GetNumAtoms() != reference.GetNumAtoms():
            fail(f"Conformer {entry.get('label', sdf.stem)} has {probe.GetNumAtoms()} atoms but the "
                 f"generated component has {reference.GetNumAtoms()}.")

        match = probe.GetSubstructMatch(reference)
        if not match or len(match) != reference.GetNumAtoms():
            # Fall back to input order. Both molecules come from the same SMILES
            # through the same RDKit, so the orders normally agree; a mismatch
            # here would silently scramble the geometry, hence the explicit check.
            match = list(range(reference.GetNumAtoms()))

        conf = probe.GetConformer()
        lines = []
        for ref_index, line in enumerate(ref_lines):
            pos = conf.GetAtomPosition(match[ref_index])
            lines.append(f"{line[:30]}{pos.x:8.3f}{pos.y:8.3f}{pos.z:8.3f}{line[54:]}")
        # Keep the CONECT records: they are what stops the component being
        # re-perceived as something else.
        lines += [l for l in reference_pdb.read_text().splitlines()
                  if l.startswith(("CONECT", "TER", "END"))]
        target = out_dir / f"{component_id}_{entry.get('label', sdf.stem)}.pdb"
        target.write_text("\n".join(lines) + "\n")
        rewritten.append({**entry, "path": str(target), "sdf": str(sdf)})
    return rewritten


def _env() -> dict:
    import os
    return dict(os.environ)


def validate_request(req: dict) -> None:
    mode = req.get("design_mode", "deNovo")
    if mode not in {"deNovo", "partialDiffusion", "motifScaffolding"}:
        fail("design_mode must be deNovo, partialDiffusion, or motifScaffolding.")
    kind = req.get("target_kind")
    if kind not in {"small_molecule", "protein"}:
        fail("target_kind must be small_molecule or protein.")
    lengths = req.get("lengths") or []
    if not lengths or any(not isinstance(value, int) or value < 1 for value in lengths):
        fail("At least one positive integer binder length is required.")
    for key in ("num_backbones", "batch_size", "queues_per_bin",
                "timesteps", "sequences_per_backbone", "top_n"):
        if not isinstance(req.get(key), int) or req[key] < 1:
            fail(f"{key} must be a positive integer.")
    if req["top_n"] > req["num_backbones"] * req["sequences_per_backbone"]:
        fail("top_n exceeds the number of sequences this campaign will create.")
    retired = {"alphafold3", "intellifold-jax"}
    selected = req.get("extra_predictors", [])
    blocked = [p for p in selected if p in retired]
    if blocked:
        fail("Retired verification predictor(s): " + ", ".join(blocked))
    allowed_predictors = {
        "boltz", "intellifold", "protenix-v2", "protenix-mini", "openfold-3-mlx"
    }
    unknown = [p for p in req.get("extra_predictors", []) if p not in allowed_predictors]
    if unknown:
        fail("Unsupported verification predictor(s): " + ", ".join(unknown))
    if sum(predictor.startswith("protenix-") for predictor in selected) > 1:
        fail("Choose either Protenix v2 or Mini, not both; they are one model family.")
    if req.get("precision") not in {"bf16", "fp32"}:
        fail("precision must be bf16 or fp32.")
    if "intellifold" in req.get("extra_predictors", []):
        if req.get("intellifold_model") not in {"v2-flash", "v2"}:
            fail("IntelliFold requires model v2-flash or v2.")
    if kind == "protein":
        if req.get("sequence_model") not in {"solublempnn", "proteinmpnn"}:
            fail("Protein campaigns require SolubleMPNN or ProteinMPNN.")
        if not Path(req.get("target_structure", "")).is_file():
            fail("The protein target structure does not exist.")
        if not str(req.get("target_sequence", "")).strip():
            fail("The protein target sequence is required for MSA generation and verification.")
        sequences = ["".join(c for c in part.upper() if not c.isspace())
                     for part in str(req.get("target_sequence", "")).split(":")]
        chains = req.get("target_chains") or [value.strip() for value in
                  str(req.get("target_chain", "B")).split(",") if value.strip()]
        if any(not sequence for sequence in sequences) or len(sequences) != len(chains):
            fail("Colon-separated target sequences and selected target chains must have the same non-zero count.")
        allowed = set("ACDEFGHIKLMNPQRSTVWYXBZJUO")
        if any(any(residue not in allowed for residue in sequence) for sequence in sequences):
            fail("A target chain contains a character that is not a supported amino-acid code.")
        if (len(set(chains)) != len(chains)
                or any(len(chain) != 1 or not chain.isalpha() for chain in chains)):
            fail("Protein target chain IDs must be unique single letters.")
        if not req.get("extra_predictors"):
            fail("Protein campaigns require at least one verification predictor.")
        if mode in {"partialDiffusion", "motifScaffolding"}:
            binder = str(req.get("source_binder_chain", "")).strip().upper()
            if len(binder) != 1 or not binder.isalpha() or binder in chains:
                fail("Choose one source binder/motif chain that is not a target chain.")
        if mode == "partialDiffusion":
            partial_t = req.get("partial_t")
            if not isinstance(partial_t, (int, float)) or not (0.1 <= partial_t <= 15):
                fail("partial_t must be between 0.1 and 15 Angstroms.")
        if mode == "motifScaffolding":
            sites = req.get("motif_sites") or {}
            if not sites or any(not str(v).strip() for v in sites.values()):
                fail("Motif scaffolding requires explicit fixed atoms for every motif residue.")
            import re
            invalid = [residue for residue in sites
                       if re.fullmatch(rf"{re.escape(binder)}[1-9][0-9]*",
                                       str(residue).strip().upper()) is None]
            if invalid:
                fail("Motif residues must use the source motif chain and residue number, "
                     f"for example {binder}42; invalid: {', '.join(map(str, invalid))}")
        if mode == "deNovo":
            _validate_binding_site_mode(req, chains)
    else:
        if req.get("sequence_model") not in {"lasermpnn", "ligandmpnn"}:
            fail("Small-molecule campaigns require LASErMPNN or LigandMPNN.")
        component = str(req.get("component_id", "")).strip().upper()
        if not (1 <= len(component) <= 3 and component.isalnum()) or component == "LIG":
            fail("Use a 1–3 character ligand component code other than LIG.")
        if not str(req.get("smiles", "")).strip():
            fail("A ligand SMILES is required for sequence design and verification.")
        if req.get("ligand_source") == "structure_file" and not Path(
                req.get("ligand_structure", "")).is_file():
            fail("The ligand structure file does not exist.")


def _validate_binding_site_mode(req: dict, chains: list[str]) -> None:
    """Normalize old requests and prohibit the unsafe protein-COM fallback."""
    conditions = req.get("conditions") or {}
    hotspots = sorted(site for site, values in conditions.items() if "hotspot" in values)
    mode = req.get("binding_site_mode")
    if mode is None:
        if req.get("ori_token") is not None:
            mode = "manual"
        elif hotspots or req.get("infer_ori_strategy") == "hotspots":
            mode = "targeted_epitope"
        elif req.get("infer_ori_strategy") == "com":
            fail("Target-centre ORI is unsafe for a fixed protein target. Choose surface_scan, surface_patch, targeted_epitope, or manual.")
        else:
            mode = "surface_scan"
    allowed = {"surface_scan", "surface_patch", "targeted_epitope", "manual"}
    if mode not in allowed:
        fail("binding_site_mode must be surface_scan, surface_patch, targeted_epitope, or manual.")
    patch = req.get("surface_patch_residues") or []
    if not isinstance(patch, list) or any(not isinstance(value, str) for value in patch):
        fail("surface_patch_residues must be an array of target residue IDs such as B42.")
    valid_residue = re.compile(r"^[^\d\s]-?\d+$")
    if mode == "surface_scan":
        if hotspots or patch or req.get("ori_token") is not None:
            fail("surface_scan cannot include hotspots, broad-region residues, or a manual ori_token.")
        req.pop("infer_ori_strategy", None)
        req.pop("ori_token", None)
    elif mode == "surface_patch":
        if hotspots:
            fail("surface_patch is positioning only; remove hotspot conditions or choose targeted_epitope.")
        if not patch or any(not valid_residue.fullmatch(value.strip()) for value in patch):
            fail("surface_patch requires explicit target residues such as B42 in surface_patch_residues.")
        if any(value.strip()[0] not in chains for value in patch):
            fail("Every broad-region residue must belong to a selected target chain.")
        req.pop("infer_ori_strategy", None)
        req.pop("ori_token", None)
    elif mode == "targeted_epitope":
        if not hotspots:
            fail("targeted_epitope requires at least one explicit hotspot condition.")
        if patch or req.get("ori_token") is not None:
            fail("targeted_epitope cannot also use broad-region residues or a manual ori_token.")
        req["infer_ori_strategy"] = "hotspots"
        req.pop("ori_token", None)
    else:
        xyz = req.get("ori_token")
        if (not isinstance(xyz, list) or len(xyz) != 3
                or any(not isinstance(value, (int, float)) or not math.isfinite(value)
                       for value in xyz)):
            fail("manual binding-site placement requires a finite three-number ori_token.")
        if hotspots or patch:
            fail("manual placement cannot also use hotspot or broad-region selections.")
        req.pop("infer_ori_strategy", None)
    req["binding_site_mode"] = mode


def prepare_surface_origins(req: dict, campaign: Path) -> Path | None:
    if req.get("target_kind") != "protein" or req.get("design_mode", "deNovo") != "deNovo":
        return None
    mode = req.get("binding_site_mode")
    if mode not in {"surface_scan", "surface_patch"}:
        return None
    try:
        from surface_origins import plan_surface_patch, plan_surface_scan
        if mode == "surface_scan":
            origins = plan_surface_scan(req["target_structure"], req["target_chains"],
                                        req["num_backbones"])
        else:
            origins = plan_surface_patch(req["target_structure"], req["target_chains"],
                                         req["surface_patch_residues"])
    except (OSError, ValueError) as exc:
        fail(f"Could not place protein-surface origins: {exc}")
    path = campaign / "config" / "surface_origins.json"
    path.write_text(json.dumps({
        "binding_site_mode": mode,
        "target_structure": req["target_structure"],
        "origins": origins,
    }, indent=2) + "\n")
    return path


def main() -> None:
    if len(sys.argv) < 2:
        fail("No request file given.")
    try:
        req = json.loads(Path(sys.argv[1]).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"Could not read the request: {exc}")
    validate_request(req)

    rfd3_root = Path(req["rfd3_root"]).resolve()
    if not (rfd3_root / "scripts" / "design_from_yaml.py").exists():
        fail(f"{rfd3_root} does not contain design_from_yaml.py — update your RFdiffusion3 checkout.")
    campaign = Path(req["campaign_dir"]).resolve()
    campaign.mkdir(parents=True, exist_ok=True)
    (campaign / "config").mkdir(exist_ok=True)

    ligand_input: Path | None = None
    ccd_mirror: Path | None = None
    selection_key: str | None = None

    if req["target_kind"] == "small_molecule":
        if req.get("ligand_source") == "structure_file":
            ligand_input = Path(req["ligand_structure"]).resolve()
            if not ligand_input.exists():
                fail(f"No such file: {ligand_input}")
            selection_key = ligand_chain_resnum(ligand_input, req.get("ligand_residue"))
            if selection_key is None:
                fail("Could not find that ligand residue in the structure file.")
        else:
            ligand_input, ccd_mirror = prepare_ligand(req, campaign, rfd3_root)
            selection_key = ligand_chain_resnum(ligand_input, req["component_id"]) or "L1"
        smi = campaign / "config" / "ligand.smi"
        if not req.get("smiles"):
            fail("A SMILES string is required: LASErMPNN and the Boltz affinity head both need it.")
        smi.write_text(req["smiles"].strip() + "\n")
    else:
        selection_key = None
        original_target_structure = req["target_structure"]
        target_chain_map = normalize_protein_target(req, campaign)

    origins_file = prepare_surface_origins(req, campaign)

    conformers = req.get("conformers") or []
    if conformers:
        missing = [c["path"] for c in conformers if not Path(c["path"]).exists()]
        if missing:
            fail("These conformer files are missing: " + ", ".join(missing))
        if ligand_input is None:
            fail("Conformers were supplied but no ligand component was generated.")
        conformers = conformers_to_pdb(conformers, ligand_input, req["component_id"].upper(),
                                       campaign / "assets" / "conformers")

    design_yaml = write_design_yaml(req, campaign, ligand_input, selection_key)

    config = {
        "campaign_dir": str(campaign),
        "design_name": req["design_name"],
        "design_mode": req.get("design_mode", "deNovo"),
        "design_yaml": str(design_yaml),
        "origins_file": str(origins_file) if origins_file else None,
        "component_id": req.get("component_id"),
        "lengths": req["lengths"],
        "num_backbones": req["num_backbones"],
        "rfd3_timesteps": req["timesteps"],
        "rfd3_recycles": req["recycles"],
        "rfd3_batch_size": req["batch_size"],
        "rfd3_queues_per_bin": req["queues_per_bin"],
        "rfd3_precision": req["precision"],
        "seed_base": req["seed_base"],
        "sequences_per_backbone": req["sequences_per_backbone"],
        # Inverse folder and its temperatures. The orchestrator dispatches on
        # sequence_model; it defaults to lasermpnn when absent, so an older
        # campaign config keeps its original behaviour.
        "sequence_model": req.get("sequence_model", "lasermpnn"),
        "sequence_temperature": req.get("sequence_temperature", 0.10),
        "first_shell_temperature": req.get("first_shell_temperature", 1.00),
        "use_potentials": req.get("use_potentials", True),
        "run_affinity": req.get("run_affinity", True),
        "run_apo": req.get("run_apo", True),
        "hit_filters": req.get("hit_filters", {}),
        "extra_predictors": req.get("extra_predictors", []),
        "intellifold_model": req.get("intellifold_model", "v2-flash"),
        # Ligand Intelligence may recommend designing across several ligand
        # geometries. Each becomes its own set of fixtures and its own share of
        # the design quota; absent, the single supplied structure is used.
        "conformers": conformers,
        "mpnn_max_parallel": req.get("mpnn_max_parallel", 6),
        "boltz_chunk_size": req.get("boltz_chunk_size", 50),
        "boltz_calibrate_n": req.get("boltz_calibrate_n", 12),
        "top_n": req["top_n"],
    }
    if req["target_kind"] == "small_molecule":
        config["smiles_file"] = str(campaign / "config" / "ligand.smi")
        if ccd_mirror is not None:
            config["ccd_mirror"] = str(ccd_mirror)
        elif req.get("ccd_mirror"):
            config["ccd_mirror"] = req["ccd_mirror"]
    else:
        config["target_kind"] = "protein"
        config["binding_site_mode"] = req.get("binding_site_mode")
        config["rfd3_root"] = str(rfd3_root)
        config["nanohunter_root"] = req["nanohunter_root"]
        config["target_sequence"] = req.get("target_sequence", "")
        config["target_chain"] = req.get("target_chain", "B")
        config["target_chains"] = req.get("target_chains") or [
            value.strip() for value in str(req.get("target_chain", "B")).split(",")
            if value.strip()
        ]
        config["source_target_structure"] = original_target_structure
        config["target_chain_map"] = target_chain_map
        # The predictor template needs a binder placeholder of the right length.
        config["max_length"] = (req.get("source_binder_length")
                                if req.get("design_mode") == "partialDiffusion"
                                else max(req["lengths"]))
        config["source_binder_length"] = req.get("source_binder_length")
        config["source_binder_contig"] = req.get("source_binder_contig")
        config["preserve_partial_sequence"] = req.get("preserve_partial_sequence", True)
        config["motif_sites"] = req.get("motif_sites", {})
        config["predict_max_parallel"] = req.get("predict_max_parallel", 4)

    config_path = campaign / "config" / "campaign.json"
    config_path.write_text(json.dumps(config, indent=2) + "\n")

    # Cheap, GPU-free validation: design_from_yaml's preflight resolves every
    # selection key and atom name against the input structure. A mistyped atom
    # fails here in a second instead of minutes into Foundry.
    check_cmd = [sys.executable, str(rfd3_root / "scripts" / "design_from_yaml.py"), str(design_yaml),
                 "--name", req["design_name"], "--output", str(campaign),
                 "--lengths", ",".join(map(str, req["lengths"])), "--stage", "check"]
    if origins_file:
        check_cmd += ["--origins", str(origins_file)]
    check = subprocess.run(
        check_cmd,
        cwd=rfd3_root, capture_output=True, text=True,
        env={**_env(), "DEBUG": "false", "TOKENIZERS_PARALLELISM": "false",
             **({"CCD_MIRROR_PATH": str(ccd_mirror)} if ccd_mirror else {})},
    )
    if check.returncode:
        message = (check.stderr or check.stdout or "").strip().splitlines()
        fail("Your design settings were rejected:\n" + "\n".join(message[-8:]))

    print(f"PREPOK|{config_path}")


if __name__ == "__main__":
    main()
