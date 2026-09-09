"""Pinned, dependency-free NESSO installation and score contracts."""
import hashlib
import json
import math
import os
from pathlib import Path

ASSETS = Path(__file__).resolve().parent / "nesso_assets"
VERSION = "v1.0.0-mps-1"
SCALARS = ("affinity_pred_value", "affinity_pred_value1", "affinity_pred_value2",
           "affinity_logits_binary", "affinity_probability_binary", "entropy_pp",
           "entropy_pl", "entropy_ll", "entropy_crop_pp", "entropy_crop_pl", "entropy_crop_ll")


# A ranking contract, separate from the pinned model/installation protocol.
# Pocket-cropped protein-ligand distogram entropy is already normalized by log(n_bins).
RANKING_POLICY = dict(version="nesso-pbind-placement-v2", entropy_field="entropy_crop_pl",
                      entropy_min_exclusive=1e-6, entropy_max_inclusive=1.0,
                      formula="affinity_probability_binary + (1 - entropy_crop_pl)",
                      order="descending", tie_break="candidate name ascending")


def placement_score(values):
    """A missing/degenerate placement never receives a perfect confidence term.

    Invalid probability is a model-output error. Invalid placement entropy is a
    candidate rejection; it must be reported and excluded before shortlist caps.
    """
    probability = values.get("affinity_probability_binary")
    if type(probability) not in (int, float) or not math.isfinite(probability) or not 0 <= probability <= 1:
        raise ValueError("NESSO binding probability is missing, non-finite or outside [0, 1]")
    entropy = values.get(RANKING_POLICY["entropy_field"])
    reason = None
    if type(entropy) not in (int, float) or not math.isfinite(entropy):
        reason = "Missing or non-finite protein-ligand placement entropy (entropy_crop_pl)"
    elif not 0 <= entropy <= RANKING_POLICY["entropy_max_inclusive"]:
        reason = "Protein-ligand placement entropy is outside [0, 1]"
    elif entropy <= RANKING_POLICY["entropy_min_exclusive"]:
        reason = "Protein-ligand placement entropy is zero or near zero (<= 0.000001)"
    return dict(eligible=reason is None, rejection_reason=reason,
                score=None if reason else probability + (1.0 - entropy))


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def installation(root):
    return Path(root) / "components/nesso" / VERSION


def protocol():
    return json.loads((ASSETS / "protocol.json").read_text())


def expected_assets():
    p = protocol()
    return {"model/model.safetensors": p["assets"]["checkpoint_sha256"],
            "model/hparams.json": p["assets"]["hparams_sha256"],
            "ccd.pkl": p["assets"]["ccd_sha256"],
            "LICENSE": p["upstream"]["license_sha256"],
            **{"esm/" + k: v for k, v in p["assets"]["esm_files"].items()}}


def read_receipt(root):
    base = installation(root)
    path = base / "receipt.json"
    if not path.is_file():
        raise ValueError("Install NESSO-1 (experimental) from Engines before enabling screening.")
    saved = json.loads(path.read_text())
    if not isinstance(saved, dict):
        raise ValueError("Invalid NESSO installation receipt")
    if (saved.get("version") != VERSION or saved.get("protocol_sha256") != sha256(ASSETS / "protocol.json")
            or saved.get("lock_sha256") != sha256(ASSETS / "requirements.lock")
            or saved.get("patch_sha256") != sha256(ASSETS / "nesso_mps.patch")):
        raise ValueError("NESSO installation does not match the pinned Studio protocol. Reinstall it from Engines.")
    files = saved.get("files", {})
    if not isinstance(files, dict) or not files or any(Path(k).is_absolute() or '..' in Path(k).parts for k in files):
        raise ValueError("Invalid NESSO installation receipt paths")
    if any(not isinstance(info, dict) or type(info.get("size")) is not int or info["size"] < 0
           or not isinstance(info.get("sha256"), str) for info in files.values()):
        raise ValueError("Invalid NESSO installation file receipts")
    for name, checksum in expected_assets().items():
        if files.get(name, {}).get("sha256") != checksum:
            raise ValueError("NESSO receipt has missing or unexpected model assets: " + name)
    for name, checksum in protocol()["source_postimages"].items():
        matches = [info for key, info in files.items() if key.endswith('/site-packages/' + name)]
        if len(matches) != 1 or matches[0].get('sha256') != checksum:
            raise ValueError("NESSO native-MPS patch provenance is missing: " + name)
    return saved


def installation_files(root):
    base = installation(root)
    saved = read_receipt(root)
    return [base / "receipt.json", base / "venv/bin/python"] + [base / key for key in sorted(saved["files"])]


def validate_installation(root, full=True):
    base = installation(root)
    saved = read_receipt(root)
    if not (base / "venv/bin/python").is_file() or not os.access(base / "venv/bin/python", os.X_OK):
        raise ValueError("NESSO Python environment is missing; reinstall NESSO in Engines.")
    for key, info in saved["files"].items():
        path = base / key
        if not path.is_file() or path.stat().st_size != info["size"] or (full and sha256(path) != info["sha256"]):
            raise ValueError("NESSO installation file is missing or changed: " + key)
    return saved


def validate_scores(values):
    # Keep non-placement output failures fail-loud. A missing/non-finite
    # placement entropy is recorded as JSON null and rejected by selection.
    required = tuple(k for k in SCALARS if k != "entropy_crop_pl")
    if not isinstance(values, dict) or any(type(values.get(k)) not in (int, float) or not math.isfinite(values[k]) for k in required):
        raise ValueError("NESSO returned missing or non-finite scalar outputs")
    if not 0 <= values['affinity_probability_binary'] <= 1:
        raise ValueError("NESSO binding probability is outside [0, 1]")
    result = {key: values.get(key) for key in SCALARS}
    entropy = result["entropy_crop_pl"]
    if type(entropy) not in (int, float) or not math.isfinite(entropy):
        result["entropy_crop_pl"] = None
    return result


def shortlist(sequences, scores, count):
    """Rank separately within each trajectory, preserving candidate identity."""
    import re
    if set(scores) != set(sequences):
        raise ValueError("NESSO must score every sampled candidate before selection")
    groups = {}
    for name in sequences:
        match = re.fullmatch(r'c\d+_t(\d+)_n\d+_s\d+', name)
        if not match:
            raise ValueError("NESSO screening only accepts optimization candidate identities")
        validate_scores(scores[name])
        if placement_score(scores[name])["eligible"]:
            groups.setdefault(int(match[1]), []).append(name)
    selected = []
    for tid in sorted(groups):
        selected += sorted(groups[tid], key=lambda n: (-placement_score(scores[n])["score"], n))[:count]
    return selected


def shortlist_by_lineage(sequences, scores, owners, per_lineage, total=None):
    """Stage-neutral selection: score every candidate, cap ancestry, then pool.

    Owners are explicit original-lineage identities, never inferred from names
    of expansion derivatives. Ties are deterministic and raw scores stay separate
    from all Boltz structural/confidence measurements.
    """
    if set(scores) != set(sequences) or set(owners) != set(sequences):
        raise ValueError("NESSO requires a score and lineage for every sampled candidate")
    if type(per_lineage) is not int or per_lineage < 1 or (total is not None and (type(total) is not int or total < 1)):
        raise ValueError("Invalid NESSO shortlist size")
    groups = {}
    for name in sequences:
        validate_scores(scores[name])
        if not isinstance(owners[name], str) or not owners[name]:
            raise ValueError("Missing original lineage identity")
        if placement_score(scores[name])["eligible"]:
            groups.setdefault(owners[name], []).append(name)
    key = lambda name: (-placement_score(scores[name])["score"], name)
    chosen = [name for owner in sorted(groups) for name in sorted(groups[owner], key=key)[:per_lineage]]
    return sorted(chosen, key=key)[:total] if total is not None else chosen
