#!/usr/bin/env python3
"""Install IntelliFold's fail-closed local user-template featurizer policy."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


ENVIRONMENT_KEY = "IPROTEINSTUDIO_INTELLIFOLD_TEMPLATE_MANIFEST"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def install(manifest_path: str | Path | None = None) -> dict | None:
    raw_path = str(manifest_path or os.environ.get(ENVIRONMENT_KEY, "")).strip()
    if not raw_path:
        return None
    path = Path(raw_path).expanduser().resolve()
    if not path.is_file():
        raise RuntimeError(f"IntelliFold user-template manifest is missing: {path}")
    payload = json.loads(path.read_text())
    if payload.get("schema") != 1 or payload.get("kind") != "iproteinstudio-intellifold-user-template":
        raise RuntimeError(f"Invalid IntelliFold user-template manifest: {path}")
    mmcif_dir = Path(str(payload.get("mmcif_dir", ""))).resolve()
    normalized = Path(str(payload.get("normalized_mmcif", ""))).resolve()
    release_dates = Path(str(payload.get("release_dates", ""))).resolve()
    allowed = {str(value).lower() for value in payload.get("allowed_template_ids") or []}
    if not allowed or not mmcif_dir.is_dir() or not normalized.is_file() or not release_dates.is_file():
        raise RuntimeError(f"Incomplete IntelliFold user-template bundle: {path}")
    if _sha256(normalized) != payload.get("normalized_mmcif_sha256"):
        raise RuntimeError("IntelliFold normalized target template changed after preparation")
    if _sha256(release_dates) != payload.get("release_dates_sha256"):
        raise RuntimeError("IntelliFold target-template release metadata changed after preparation")
    for template_id in allowed:
        candidate = mmcif_dir / f"{template_id}.cif"
        if not candidate.is_file():
            raise RuntimeError(f"IntelliFold target-template mmCIF is missing: {candidate}")
    for mapping in payload.get("mappings") or []:
        a3m = Path(str(mapping.get("a3m", ""))).resolve()
        if not a3m.is_file() or _sha256(a3m) != mapping.get("a3m_sha256"):
            raise RuntimeError(f"IntelliFold target-template alignment changed: {a3m}")

    import shutil
    import intellifold.data.inference.utils as inference_utils
    import intellifold.data.module.inference as inference
    from intellifold.data.template.template_parser import PrefilterResult, get_pdb_id_and_chain
    from intellifold.data.template.template_utils import TemplateHitFeaturizer

    cache = Path(os.environ["INTELLIFOLD_CACHE"])

    def construct_user_template_featurizer():
        featurizer = TemplateHitFeaturizer(
            mmcif_dir=str(mmcif_dir),
            template_cache_dir="",
            max_hits=4,
            kalign_binary_path=shutil.which("kalign"),
            # Local user structures have no PDB release date. Upstream assigns
            # that case 9999-12-31, so use the same ceiling after restricting
            # the featurizer to the manifest's content-addressed IDs.
            max_template_date="9999-12-31",
            release_dates_path=str(release_dates),
            obsolete_pdbs_path=str(cache / "common/obsolete_to_successor.json"),
            _shuffle_top_k_prefiltered=None,
            _max_template_candidates_num=20,
        )
        original = featurizer._hit_filter.prefilter

        def prefilter(query_seq, hit, max_date):
            pdb_id, _chain_id = get_pdb_id_and_chain(hit)
            if pdb_id.lower() in allowed:
                return PrefilterResult(True)
            return original(query_seq, hit, max_date)

        featurizer._hit_filter.prefilter = prefilter
        return featurizer

    inference.construct_template_featurizer = construct_user_template_featurizer

    # IntelliFold v2 writes ``template_id=-1`` for an explicitly untemplated
    # protein, but its inference entity builder still turns that sentinel into
    # ``templates/-1_hmmsearch.a3m``.  Remove only that synthetic path.  This
    # keeps binder coordinates wholly unconditioned while leaving every target
    # entity's checksummed user-template path intact.
    original_bioassembly = inference.create_bioassembly_data

    def create_target_only_bioassembly(record, template_dir):
        result = original_bioassembly(record, template_dir)
        for chain in record.chains:
            if chain.mol_type != 0 or chain.template_id != -1:
                continue
            entity_id = int(chain.entity_id)
            if entity_id < 0 or entity_id >= len(result):
                raise RuntimeError("IntelliFold returned an invalid untemplated protein entity")
            protein = result[entity_id].get("proteinChain")
            if protein is None:
                raise RuntimeError("IntelliFold lost an untemplated protein entity")
            protein.pop("templatesPath", None)
        return result

    inference.create_bioassembly_data = create_target_only_bioassembly

    # Upstream's generic --use_template path otherwise offers to download its
    # large optional PDB archive. Explicit Studio user templates are
    # self-contained and must never trigger that database path.
    original_download = inference_utils.download

    def download_without_template_database(cache_dir, model, use_template=False):
        return original_download(cache_dir, model, use_template=False)

    inference_utils.download = download_without_template_database
    return payload
