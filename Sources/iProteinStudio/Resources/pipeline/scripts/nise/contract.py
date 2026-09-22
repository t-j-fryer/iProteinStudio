"""Lightweight, shared native/MCP ligand-NISE request contract."""
from pathlib import Path
import importlib.util


def nesso_contract():
    spec = importlib.util.spec_from_file_location("studio_nesso_contract", Path(__file__).with_name("nesso_contract.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def saved_request(request):
    """A saved pre-v2 request is different from a new minimal MCP request."""
    if isinstance(request, dict) and "search_policy_version" not in request:
        return {**LEGACY_POLICY, "num_starts": 100, "max_cycles": 30, "patience": 5, "trajectories": 6, "beam": 1, **request}
    return request

# Studio defaults; historical saved runs retain their explicit settings.
LEGACY_POLICY = dict(search_policy_version=1, early_score_gate=0.0, selective_affinity=False,
                     adaptive_proposals=False, initial_proposals=16, affinity_batch_size=8, min_improvement=0.0001)
DEFAULTS = dict(search_policy_version=3, early_score_gate=0.80, selective_affinity=True,
                adaptive_proposals=False, initial_proposals=16, affinity_batch_size=8, min_improvement=0.01, smiles="", num_starts=1000, trajectories=8, nise_seqs=32, first_cycle_seqs=64,
                partial_noising=False, noise_radius=6.0, noise_percent=25.0, noise_predictions=32, noise_mpnn_seqs=32, noise_advance=1,
                max_cycles=30, patience=4, binder_min_len=65, binder_max_len=150,
                seed=0, preorganisation=False, top_x=8, scheduler="cycle-wave",
                phase0_refine_cycles=2, phase0_seqs1=3, phase0_seqs2=5, beam=3,
                screening_engine="nesso", nesso_screen=False, nesso_top_k=16, phase0_nesso_screen=False,
                phase0_nesso_refine_top_k=1, phase0_nesso_expand_top_k=20, phase0_gate_seqs=3,
                phase0_sc_ca=2.0, nise_sc_ca=2.5, nise_sc_lig=2.5, nise_ligand_sc_from_cycle=3, backbone_method="protein-hunter", rfd3_num_bins=5,
                exposure_mode="sasa", geometry_workers=0, hotspot_atoms=[], exposed_atoms=[], hotspot_distance=6.0, exposure_min_fraction=0.5,
                ligand_atom_signature="", ligand_atoms_generated_for="")
BOUNDS = dict(geometry_workers=(0, 64), search_policy_version=(1, 3), first_cycle_seqs=(1, 4096), noise_predictions=(1, 1024), noise_mpnn_seqs=(1, 4096), noise_advance=(1, 63), initial_proposals=(1, 4096), affinity_batch_size=(1, 128), num_starts=(1, 10000), trajectories=(1, 1000), nise_seqs=(1, 4096),
              max_cycles=(1, 1000), patience=(1, 1000), binder_min_len=(60, 250),
              binder_max_len=(60, 250), seed=(0, 2147483647), top_x=(1, 64),
              phase0_refine_cycles=(0, 20), phase0_seqs1=(1, 1024), phase0_seqs2=(1, 1024),
              phase0_nesso_refine_top_k=(1, 1024), phase0_nesso_expand_top_k=(1, 10000),
              phase0_gate_seqs=(1, 1024), nise_ligand_sc_from_cycle=(1, 1001), beam=(1, 64), nesso_top_k=(1, 4096), rfd3_num_bins=(1, 20))


def normalize(request):
    if not isinstance(request, dict) or set(request) - set(DEFAULTS):
        raise ValueError("Unknown NISE settings; use the versioned NISE request.")
    cfg = {**DEFAULTS, **request}
    if cfg["search_policy_version"] == 1:
        cfg = {**DEFAULTS, "num_starts": 100, "max_cycles": 30, "patience": 5, "trajectories": 6, "beam": 1, **LEGACY_POLICY, **request}
    if cfg["search_policy_version"] < 3:
        cfg["nise_seqs"] = request.get("nise_seqs", 64)
        cfg["first_cycle_seqs"] = request.get("first_cycle_seqs", cfg["nise_seqs"])
    # Older custom requests shared their refinement/gate sampling count.
    cfg["phase0_gate_seqs"] = request.get("phase0_gate_seqs", cfg["phase0_seqs1"])
    if cfg["backbone_method"] not in ("protein-hunter", "rfdiffusion3"):
        raise ValueError("Choose Protein Hunter or RFdiffusion3 for initial backbone generation.")
    if cfg["exposure_mode"] not in ("sasa", "biotin-carboxamide-v1"):
        raise ValueError("Unknown ligand exposure policy.")
    if cfg["exposure_mode"] != "sasa" and not cfg["selective_affinity"]:
        raise ValueError("Biotin exit filtering requires geometry-before-affinity scoring.")
    for key, (low, high) in BOUNDS.items():
        value = cfg[key]
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f"{key} must be an integer between {low} and {high}.")
    for key in ("selective_affinity", "adaptive_proposals", "partial_noising"):
        if type(cfg[key]) is not bool:
            raise ValueError(f"{key} must be true or false.")
    if cfg["adaptive_proposals"] and (cfg["initial_proposals"] > min(cfg["nise_seqs"], cfg["first_cycle_seqs"]) or cfg["beam"] > cfg["initial_proposals"]):
        raise ValueError("Adaptive initial proposals must be between the beam width and the maximum proposals per parent.")
    if cfg["beam"] > cfg["first_cycle_seqs"]:
        raise ValueError("First-cycle proposals must cover the beam width.")
    if cfg["partial_noising"]:
        if cfg["adaptive_proposals"]:
            raise ValueError("Turn off adaptive sampling before enabling partial noising.")
        if cfg["noise_advance"] >= cfg["beam"] or cfg["noise_advance"] > cfg["noise_mpnn_seqs"]:
            raise ValueError("Reserve fewer noising places than the beam width, and sample at least that many repair sequences.")
        if cfg["nesso_screen"] and cfg["noise_advance"] > cfg["nesso_top_k"]:
            raise ValueError("The NESSO shortlist must cover the reserved noising places.")
    import re, math
    for key in ("hotspot_atoms", "exposed_atoms"):
        values = cfg[key]
        if not isinstance(values, list) or len(values) > 256 or any(not isinstance(v, str) or not re.fullmatch(r"[A-Z]{1,2}[1-9][0-9]{0,2}", v) or len(v) > 4 for v in values):
            raise ValueError("Choose ligand atoms from the resolved molecule; invalid " + key)
        if len(values) != len(set(values)):
            raise ValueError("Duplicate ligand atom selections are not allowed.")
        cfg[key] = list(values)
    if set(cfg["hotspot_atoms"]) & set(cfg["exposed_atoms"]):
        raise ValueError("An atom cannot be both a hotspot and an exposed atom.")
    for key, low, high in (("noise_radius", 3, 15), ("noise_percent", 1, 100), ("hotspot_distance", 3, 10), ("exposure_min_fraction", 0.1, 1),
                           ("early_score_gate", 0, 2), ("min_improvement", 0, 1), ("phase0_sc_ca", 0.1, 10), ("nise_sc_ca", 0.1, 10), ("nise_sc_lig", 0.1, 10)):
        if type(cfg[key]) not in (int, float) or not math.isfinite(cfg[key]) or not low <= cfg[key] <= high:
            raise ValueError(f"{key} must be between {low} and {high}.")
    if not isinstance(cfg["ligand_atom_signature"], str) or not isinstance(cfg["ligand_atoms_generated_for"], str):
        raise ValueError("Invalid saved ligand atom identity.")
    if cfg["hotspot_atoms"] or cfg["exposed_atoms"]:
        if not re.fullmatch(r"[0-9a-f]{64}", cfg["ligand_atom_signature"]) or cfg["ligand_atoms_generated_for"] != str(cfg["smiles"]).strip():
            raise ValueError("Reload the ligand atoms after changing the SMILES, then reselect the desired atoms.")
    if cfg["trajectories"] > cfg["num_starts"]:
        raise ValueError("Trajectories cannot exceed starting structures.")
    if cfg["beam"] > cfg["nise_seqs"]:
        raise ValueError("Sequences to advance cannot exceed sequences sampled per parent.")
    if type(cfg["phase0_nesso_screen"]) is not bool:
        raise ValueError("phase0_nesso_screen must be true or false.")
    if cfg["phase0_nesso_screen"] and cfg["phase0_nesso_refine_top_k"] > cfg["phase0_seqs1"]:
        raise ValueError("Initial NESSO refinement shortlist cannot exceed sequences sampled per lineage.")
    if cfg["phase0_nesso_screen"] and cfg["phase0_nesso_expand_top_k"] < cfg["trajectories"]:
        raise ValueError("Initial NESSO expansion shortlist must allow at least the requested number of trajectories.")
    if cfg["screening_engine"] not in ("nesso", "psichic"):
        raise ValueError("Unknown experimental screening engine.")
    if cfg["screening_engine"] == "psichic" and (cfg["nesso_screen"] or cfg["phase0_nesso_screen"]) and cfg["binder_max_len"] > 700:
        raise ValueError("Experimental PSICHIC supports sequences up to 700 residues.")
    if type(cfg["nesso_screen"]) is not bool:
        raise ValueError("nesso_screen must be true or false.")
    if cfg["nesso_screen"] and not cfg["beam"] <= cfg["nesso_top_k"] <= cfg["nise_seqs"]:
        raise ValueError("NESSO shortlist must be between sequences to advance and sequences sampled per parent.")
    if cfg["binder_min_len"] > cfg["binder_max_len"]:
        raise ValueError("Minimum binder length exceeds maximum length.")
    smiles = cfg["smiles"]
    if not isinstance(smiles, str) or not smiles.strip() or len(smiles) > 4096 or any(c.isspace() for c in smiles.strip()):
        raise ValueError("Enter one small-molecule SMILES without whitespace.")
    cfg["smiles"] = smiles.strip()
    if type(cfg["preorganisation"]) is not bool:
        raise ValueError("preorganisation must be true or false.")
    if cfg["scheduler"] not in {"cycle-wave", "resident"}:
        raise ValueError("Unknown NISE scheduler.")
    return cfg


def scoring_contract(request):
    if request.get("screening_engine", "nesso") == "nesso":
        return nesso_contract()
    spec = importlib.util.spec_from_file_location("studio_psichic_contract", Path(__file__).with_name("psichic_contract.py"))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def required_files(root, request=None):
    root = Path(root)
    files = [root / p for p in (
        "venvs/NanoHunter_boltz/bin/python", "venvs/NanoHunter_lasermpnn/bin/python",
        "models/boltz2/boltz2_conf.ckpt", "models/boltz2/boltz2_aff.ckpt",
        "src/LASErMPNN/model_weights/laser_weights_0p1A_nothing_heldout.pt",
        "scripts/lasermpnn_prepare_input.py")]
    if request and (request.get("nesso_screen") or request.get("phase0_nesso_screen")):
        files += scoring_contract(request).installation_files(root)
    if request and request.get("backbone_method") == "rfdiffusion3":
        files += [root / p for p in (
            "rfd3/.venv/bin/python", "rfd3/weights/rfd3_core.safetensors",
            "rfd3/checkpoints/rfd3_latest.ckpt",
            "rfd3/rfd3_weight_set.py",
            "rfd3/milestone0_oracle.py", "rfd3/scripts/prepare_ligand_target.py",
            "rfd3/scripts/design_from_yaml.py", "rfd3/scripts/run_backbone_bins.py",
            "rfd3/scripts/generate_backbones.py", "rfd3/scripts/rfd3_resume.py")]
    return files


def preflight(root, request):
    cfg = normalize(request)
    missing = [str(p) for p in required_files(root, cfg) if not p.is_file()]
    if not (Path(root) / "models/boltz2/mols").is_dir():
        missing.append("Boltz molecular dictionary (models/boltz2/mols)")
    if missing:
        raise ValueError("Install Boltz, its affinity checkpoint, LASErMPNN, and any selected optional engines in Engines. Missing: " + ", ".join(missing))
    if cfg["exposure_mode"] == "biotin-carboxamide-v1":
        import subprocess, json
        result = subprocess.run([str(Path(root) / "venvs/NanoHunter_boltz/bin/python"),
                                 str(Path(__file__).with_name("biotin_exit.py"))],
                                input=json.dumps(cfg), text=True, capture_output=True, timeout=90)
        if result.returncode:
            raise ValueError("Biotin exit preflight failed: " + result.stderr[-2000:])
    if cfg["nesso_screen"] or cfg["phase0_nesso_screen"]:
        scoring_contract(cfg).validate_installation(root)
    return cfg


def prediction_budget(request):
    cfg = normalize(request)
    rfd3 = cfg["backbone_method"] == "rfdiffusion3"
    refinement = cfg["phase0_nesso_refine_top_k"] if cfg["phase0_nesso_screen"] else cfg["phase0_seqs1"]
    expansion = (min(cfg["num_starts"], cfg["phase0_nesso_expand_top_k"]) if cfg["phase0_nesso_screen"]
                 else cfg["num_starts"] * cfg["phase0_gate_seqs"] * cfg["phase0_seqs2"])
    initial = cfg["num_starts"] * ((0 if rfd3 else 1) + cfg["phase0_refine_cycles"] * refinement + cfg["phase0_gate_seqs"]) + expansion
    spec = importlib.util.spec_from_file_location("studio_nise_policy", Path(__file__).with_name("search_policy.py"))
    policy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(policy)
    rounds = len(policy.proposal_levels(cfg["nise_seqs"], cfg["adaptive_proposals"], cfg["initial_proposals"]))
    shortlist = cfg["nesso_top_k"] * rounds
    first_rounds = len(policy.proposal_levels(cfg["first_cycle_seqs"], cfg["adaptive_proposals"], cfg["initial_proposals"]))
    first = cfg["trajectories"] * (min(cfg["nesso_top_k"] * first_rounds, cfg["first_cycle_seqs"]) if cfg["nesso_screen"] else cfg["first_cycle_seqs"])
    normal_parents = cfg["beam"] - (cfg["noise_advance"] if cfg["partial_noising"] else 0)
    later = cfg["trajectories"] * (min(shortlist, normal_parents * cfg["nise_seqs"]) if cfg["nesso_screen"] else normal_parents * cfg["nise_seqs"])
    noise = cfg["trajectories"] * (cfg["noise_predictions"] + (min(cfg["noise_mpnn_seqs"], cfg["nesso_top_k"]) if cfg["nesso_screen"] else cfg["noise_mpnn_seqs"])) if cfg["partial_noising"] else 0
    later += noise
    return dict(noising_boltz_per_later_cycle_max=noise, initial_boltz_max=initial, initial_rfd3_backbones=cfg["num_starts"] if rfd3 else 0,
                first_cycle_boltz_max=first, later_cycle_boltz_max=later,
                optimization_boltz_max=first + (cfg["max_cycles"] - 1) * later,
                interpretation="Calculated upper bounds, not runtime estimates; fewer survivors and early stopping reduce work.")
