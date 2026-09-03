#!/usr/bin/env python3
"""Convert a user PDB/mmCIF into IntelliFold's explicit-template contract.

IntelliFold accepts template-search A3M files, not structure paths.  This
adapter deterministically matches each target query chain to one structure
chain, writes a normalized mmCIF under a content-addressed identifier, and
emits one exact HMMsearch-style A3M per query chain.  Binder chain A is never
included.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import gemmi
import yaml


def die(message: str) -> None:
    raise SystemExit(f"IntelliFold target-template adapter: {message}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def clean_sequence(value: object) -> str:
    return "".join(char for char in str(value or "").upper() if char.isalpha())


def observed_chain_sequences(structure: gemmi.Structure) -> dict[str, str]:
    result: dict[str, str] = {}
    if not structure:
        return result
    for chain in structure[0]:
        sequence: list[str] = []
        seen: set[tuple[int, str]] = set()
        for residue in chain:
            key = (residue.seqid.num, residue.seqid.icode)
            info = gemmi.find_tabulated_residue(residue.name)
            if key in seen or not info.is_amino_acid():
                continue
            seen.add(key)
            letter = info.one_letter_code
            sequence.append(letter if len(letter) == 1 and letter.isalpha() else "X")
        if sequence and any(atom.name.strip() == "CA" for residue in chain for atom in residue):
            result[chain.name] = "".join(sequence).upper()
    return result


def align(query: str, template: str) -> tuple[str, int, int, float, float]:
    """Return deterministic A3M hit sequence plus match/coverage statistics."""
    rows, cols = len(query) + 1, len(template) + 1
    scores = [[0] * cols for _ in range(rows)]
    trace = [[0] * cols for _ in range(rows)]  # diagonal, query-only, template-only
    for i in range(1, rows):
        scores[i][0], trace[i][0] = -2 * i, 1
    for j in range(1, cols):
        scores[0][j], trace[0][j] = -2 * j, 2
    for i in range(1, rows):
        for j in range(1, cols):
            choices = (
                scores[i - 1][j - 1] + (2 if query[i - 1] == template[j - 1] else -1),
                scores[i - 1][j] - 2,
                scores[i][j - 1] - 2,
            )
            best = max(range(3), key=lambda index: (choices[index], -index))
            scores[i][j], trace[i][j] = choices[best], best

    aligned: list[str] = []
    matches = mapped = 0
    i, j = len(query), len(template)
    while i or j:
        direction = trace[i][j]
        if i and j and direction == 0:
            aligned.append(template[j - 1].upper())
            mapped += 1
            matches += query[i - 1] == template[j - 1]
            i -= 1
            j -= 1
        elif i and (j == 0 or direction == 1):
            aligned.append("-")
            i -= 1
        else:
            aligned.append(template[j - 1].lower())
            j -= 1
    aligned.reverse()
    identity = matches / max(1, mapped)
    coverage = mapped / max(1, len(query))
    return "".join(aligned), mapped, matches, identity, coverage


def query_chains(yaml_path: Path) -> dict[str, str]:
    try:
        document = yaml.safe_load(yaml_path.read_text()) or {}
    except Exception as exc:
        die(f"could not parse design YAML {yaml_path}: {exc}")
    result: dict[str, str] = {}
    for wrapped in document.get("sequences") or []:
        if not isinstance(wrapped, dict) or "protein" not in wrapped:
            continue
        protein = wrapped["protein"] or {}
        raw_ids = protein.get("id")
        ids = raw_ids if isinstance(raw_ids, list) else [raw_ids]
        sequence = clean_sequence(protein.get("sequence"))
        for raw_id in ids:
            chain_id = str(raw_id or "").strip()
            if chain_id and chain_id != "A":
                if not sequence:
                    die(f"target chain {chain_id} has no protein sequence")
                result[chain_id] = sequence
    if not result:
        die("design YAML has no target protein chain (binder A is intentionally excluded)")
    return result


def normalize(structure: gemmi.Structure, destination: Path) -> None:
    structure.setup_entities()
    for entity in structure.entities:
        if entity.entity_type != gemmi.EntityType.Polymer:
            continue
        if entity.polymer_type not in {gemmi.PolymerType.PeptideL, gemmi.PolymerType.PeptideD}:
            continue
        if entity.full_sequence:
            continue
        sequence: list[str] = []
        seen: set[tuple[str, int, str]] = set()
        subchains = set(entity.subchains)
        for chain in structure[0]:
            for residue in chain:
                key = (chain.name, residue.seqid.num, residue.seqid.icode)
                info = gemmi.find_tabulated_residue(residue.name)
                if residue.subchain not in subchains or key in seen or not info.is_amino_acid():
                    continue
                seen.add(key)
                sequence.append(residue.name)
        if not sequence:
            die(f"could not derive the sequence for template entity {entity.name}")
        entity.full_sequence = sequence
    structure.assign_label_seq_id(force=True)
    document = structure.make_mmcif_document()
    block = document.sole_block()

    # Gemmi's atom-only PDB conversion records entity_poly but omits the
    # entity_poly_seq loop used by IntelliFold's inherited AlphaFold parser.
    # Add that standards-compliant loop and peptide component types without
    # changing coordinates or residue numbering.
    entity_poly_seq = block.init_loop(
        "_entity_poly_seq.", ["entity_id", "num", "mon_id", "hetero"]
    )
    for entity in structure.entities:
        if entity.entity_type != gemmi.EntityType.Polymer:
            continue
        if entity.polymer_type not in {gemmi.PolymerType.PeptideL, gemmi.PolymerType.PeptideD}:
            continue
        for index, monomer in enumerate(entity.full_sequence, start=1):
            entity_poly_seq.add_row([entity.name, str(index), monomer, "n"])
    component_ids = block.find_values("_chem_comp.id")
    component_types = block.find_values("_chem_comp.type")
    for index, component_id in enumerate(component_ids):
        if gemmi.find_tabulated_residue(component_id).is_amino_acid():
            component_types[index] = "L-peptide linking"

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.part")
    document.write_file(str(temporary))
    os.replace(temporary, destination)


def prepare(source: Path, yaml_path: Path, output: Path) -> Path:
    source = source.expanduser().resolve()
    yaml_path = yaml_path.expanduser().resolve()
    output = output.expanduser().resolve()
    if not source.is_file() or source.suffix.lower() not in {".pdb", ".cif", ".mmcif"}:
        die(f"missing or unsupported structure: {source}")
    try:
        structure = gemmi.read_structure(str(source))
    except Exception as exc:
        die(f"could not read {source}: {exc}")
    if len(structure) == 0:
        die(f"template contains no structural model: {source}")
    template_chains = observed_chain_sequences(structure)
    if not template_chains:
        die("template contains no protein chain with C-alpha coordinates")

    source_digest = sha256(source)
    # IntelliFold's inherited PDB parser accepts exactly four identifier
    # characters. The full SHA-256 remains authoritative in the manifest;
    # this short ID is only a private filename inside one campaign bundle.
    template_id = "u" + source_digest[:3]
    mmcif_dir = output / "mmcif"
    cif_path = mmcif_dir / f"{template_id}.cif"
    normalize(structure, cif_path)

    available = set(template_chains)
    mappings: list[dict[str, object]] = []
    a3m_by_chain: dict[str, str] = {}
    msa_by_chain: dict[str, str] = {}
    bundle_by_sequence: dict[str, dict[str, object]] = {}
    pairs = output / "pairs"
    pairs.mkdir(parents=True, exist_ok=True)
    for pair_index, (chain_id, query) in enumerate(query_chains(yaml_path).items()):
        reused = bundle_by_sequence.get(query)
        if reused is not None:
            a3m_by_chain[chain_id] = str(reused["a3m"])
            msa_by_chain[chain_id] = str(reused["msa"])
            mappings.append({**reused["mapping"], "query_chain": chain_id,
                             "shared_entity_template": True})
            continue
        candidates = []
        for template_chain in sorted(available):
            template_sequence = template_chains[template_chain]
            hit, mapped, matches, identity, coverage = align(query, template_sequence)
            candidates.append((identity, coverage, mapped, template_chain, hit,
                               matches, template_sequence))
        if not candidates:
            die(f"no unused template chain remains for target chain {chain_id}")
        identity, coverage, mapped, template_chain, hit, matches, template_sequence = max(candidates)
        if identity < 0.70 or coverage < 0.70:
            die(f"unsafe match for target chain {chain_id}: best template chain "
                f"{template_chain} has identity={identity:.3f}, coverage={coverage:.3f}; "
                "provide the structure of the same target sequence")
        available.remove(template_chain)
        a3m_path = pairs / f"{pair_index:03d}_template.a3m"
        msa_path = pairs / f"{pair_index:03d}_msa.a3m"
        description = (f">{template_id}_{template_chain}/1-{len(template_sequence)} "
                       f"[iProteinStudio user template] mol:protein length:{len(template_sequence)}")
        a3m_path.write_text(f"{description}\n{hit}\n")
        msa_path.write_text(f">query\n{query}\n")
        a3m_by_chain[chain_id] = str(a3m_path.resolve())
        msa_by_chain[chain_id] = str(msa_path.resolve())
        mapping = {
            "query_chain": chain_id,
            "template_chain": template_chain,
            "query_length": len(query),
            "template_length": len(template_sequence),
            "aligned_residues": mapped,
            "identical_residues": matches,
            "identity": identity,
            "coverage": coverage,
            "a3m": str(a3m_path.resolve()),
            "a3m_sha256": sha256(a3m_path),
            "msa": str(msa_path.resolve()),
            "shared_entity_template": False,
        }
        mappings.append(mapping)
        bundle_by_sequence[query] = {
            "a3m": str(a3m_path.resolve()), "msa": str(msa_path.resolve()),
            "mapping": mapping,
        }

    release_dates = output / "release_dates.json"
    release_dates.write_text(json.dumps({template_id: {"release_date": "2000-01-01"}},
                                        indent=2, sort_keys=True) + "\n")
    manifest = output / "manifest.json"
    payload = {
        "schema": 1,
        "kind": "iproteinstudio-intellifold-user-template",
        "source": str(source),
        "source_sha256": source_digest,
        "template_id": template_id,
        "allowed_template_ids": [template_id],
        "mmcif_dir": str(mmcif_dir.resolve()),
        "normalized_mmcif": str(cif_path.resolve()),
        "normalized_mmcif_sha256": sha256(cif_path),
        "release_dates": str(release_dates.resolve()),
        "release_dates_sha256": sha256(release_dates),
        "a3m_by_query_chain": a3m_by_chain,
        "msa_by_query_chain": msa_by_chain,
        "binder_template": "none",
        "mappings": mappings,
    }
    manifest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--yaml", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(prepare(args.source, args.yaml, args.output))


if __name__ == "__main__":
    main()
