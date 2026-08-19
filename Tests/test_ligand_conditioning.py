#!/usr/bin/env python3
"""Regression contracts for ligand identity, atom naming and RFD3 conditions."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RFD3 = ROOT / "Sources/iProteinStudio/Resources/rfd3"
BIOTIN = "C1[C@H]2[C@@H]([C@@H](S1)CCCCC(=O)O)NC(=O)N2"
CAFFEINE = "Cn1c(=O)c2c(ncn2C)n(C)c1=O"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


inspect_target = load("ligand_inspect_contract", RFD3 / "inspect_target.py")
intelligence = load("ligand_intelligence_contract", RFD3 / "ligand_intelligence.py")
prepare_campaign = load("ligand_prepare_contract", RFD3 / "prepare_campaign.py")


def conditions(site: dict) -> set[str]:
    return {entry["condition"] for entry in site["suggestions"]}


def test_biotin_atom_names_and_chemistry() -> None:
    result = inspect_target.inspect_ligand(BIOTIN, None, None)
    sites = {site["index"]: site for site in result["sites"]}
    assert len(sites) == 16
    assert sites[9]["name"] == "C22"       # carboxyl carbon
    assert sites[10]["name"] == "O18"      # carboxyl carbonyl oxygen
    assert sites[11]["name"] == "O19"      # neutral carboxylic-acid OH
    assert sites[14]["name"] == "O17"      # ureido carbonyl oxygen

    donors = {idx for idx, site in sites.items() if "hbondDonor" in conditions(site)}
    acceptors = {idx for idx, site in sites.items() if "hbondAcceptor" in conditions(site)}
    assert donors == {11, 12, 15}
    assert acceptors == {4, 10, 14}
    assert all("exposed" not in conditions(site) for site in sites.values())
    assert all("buried" not in conditions(sites[idx]) for idx in donors | acceptors)

    charged = inspect_target.inspect_ligand("C[N+](C)(C)C", None, None)
    charged_sites = {site["index"]: site for site in charged["sites"]}
    assert "buried" not in conditions(charged_sites[1])


def test_directed_linker_bond_is_unambiguous() -> None:
    from rdkit import Chem

    mol = Chem.MolFromSmiles("CCOC")
    core, presentation, rule = intelligence.split_core_and_presentation(mol, 1, 2)
    assert core == {0, 1}
    assert presentation == {2, 3}
    assert rule == "explicit core-to-linker bond"

    reverse_core, reverse_presentation, _ = intelligence.split_core_and_presentation(mol, 2, 1)
    assert reverse_core == {2, 3}
    assert reverse_presentation == {0, 1}

    for pair in ((1, None), (0, 3)):
        try:
            intelligence.split_core_and_presentation(mol, *pair)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid linker selection {pair} was accepted")


def exact_identity_match(query_smiles: str, other_smiles: list[str]) -> None:
    import requests
    from rdkit import Chem

    query = Chem.MolFromSmiles(query_smiles)
    exact = Chem.MolToInchiKey(query)
    keys = {f"OTHER{idx}": Chem.MolToInchiKey(Chem.MolFromSmiles(smiles))
            for idx, smiles in enumerate(other_smiles)}
    keys["EXACT"] = exact

    class Response:
        status_code = 200

        def __init__(self, key: str):
            self.key = key

        def json(self):
            return {"rcsb_chem_comp_descriptor": {"InChIKey": self.key}}

    original = requests.get
    requests.get = lambda url, timeout: Response(keys[url.rsplit("/", 1)[-1]])
    try:
        matched = intelligence.confirm_identical_ccds(list(keys), query, 1)
    finally:
        requests.get = original
    assert matched == ["EXACT"]


def test_ccd_identity_is_generic_and_requires_full_chemical_identity() -> None:
    # Stereochemistry, protonation and an unrelated aromatic heterocycle are
    # independent identity dimensions. None may be silently normalised to the
    # first graph-search result.
    exact_identity_match("C[C@H](O)C(=O)O", [
        "C[C@@H](O)C(=O)O",             # enantiomer
        "C[C@H](O)C(=O)[O-]",           # deprotonated query
    ])
    exact_identity_match("CC(=O)O", ["CC(=O)[O-]"])
    exact_identity_match(CAFFEINE, ["Cn1c(=O)c2[nH]cnc2n(C)c1=O"])


def test_chemical_search_reads_every_page() -> None:
    import requests

    class Response:
        status_code = 200

        def __init__(self, payload: dict):
            self.payload = payload

        def json(self):
            return self.payload

    starts: list[int] = []
    original = requests.post

    def post(url, json, timeout):
        start = json["request_options"]["paginate"]["start"]
        starts.append(start)
        if start == 0:
            return Response({
                "total_count": 102,
                "result_set": [{"identifier": f"CCD{i:03d}"} for i in range(100)],
            })
        return Response({
            "total_count": 102,
            "result_set": [{"identifier": "CCD099"}, {"identifier": "EXACT"}],
        })

    requests.post = post
    try:
        candidates = intelligence.rcsb_chemical_search(CAFFEINE, 1)
    finally:
        requests.post = original
    assert starts == [0, 100]
    assert len(candidates) == 101
    assert candidates[-1] == "EXACT"


def test_incomplete_candidate_verification_is_not_a_false_negative() -> None:
    import requests
    from rdkit import Chem

    exact_key = Chem.MolToInchiKey(Chem.MolFromSmiles(CAFFEINE))

    class Response:
        def __init__(self, status_code: int, key: str | None = None):
            self.status_code = status_code
            self.key = key

        def json(self):
            return {"rcsb_chem_comp_descriptor": {"InChIKey": self.key}}

    original = requests.get
    requests.get = lambda url, timeout: (
        Response(200, exact_key) if url.endswith("/EXACT") else Response(503)
    )
    try:
        try:
            intelligence.confirm_identical_ccds(
                ["EXACT", "UNKNOWN"], Chem.MolFromSmiles(CAFFEINE), 1)
        except RuntimeError as exc:
            assert "could not be verified" in str(exc)
        else:
            raise AssertionError("a partial candidate search was reported as complete")
    finally:
        requests.get = original


def test_every_exact_ccd_is_searched_and_entries_are_deduplicated() -> None:
    originals = {
        name: getattr(intelligence, name)
        for name in ("rcsb_chemical_search", "confirm_identical_ccds",
                     "rcsb_entries_for_ccd", "fetch_ligand_instance")
    }
    intelligence.rcsb_chemical_search = lambda smiles, timeout: ["ONE", "TWO"]
    intelligence.confirm_identical_ccds = lambda candidates, query, timeout: candidates
    intelligence.rcsb_entries_for_ccd = (
        lambda code, limit, timeout: ["1AAA", "2BBB"] if code == "ONE" else ["2BBB", "3CCC"]
    )
    intelligence.fetch_ligand_instance = lambda entry, code, timeout: object()
    try:
        result = intelligence.experimental_conformers(CAFFEINE, {
            "network_timeout": 1,
            "max_pdb_entries": 10,
        })
    finally:
        for name, value in originals.items():
            setattr(intelligence, name, value)

    assert result["ccd_codes"] == ["ONE", "TWO"]
    assert result["n_entries"] == 3
    assert [item["entry"] for item in result["instances"]] == ["1AAA", "2BBB", "3CCC"]


def test_foundry_hbond_direction_is_not_inverted() -> None:
    request = {
        "design_name": "biotin_contract",
        "target_kind": "small_molecule",
        "component_id": "BTN",
        "is_non_loopy": True,
        "infer_ori_strategy": "com",
        "conditions": {
            "N23": ["hbondDonor"],
            "O17": ["hbondAcceptor"],
            "C29": ["buried"],
        },
    }
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        ligand = root / "BTN.pdb"
        ligand.write_text("HETATM\n")
        path = prepare_campaign.write_design_yaml(request, root, ligand, "L1")
        text = path.read_text()
    assert 'select_hbond_donor:\n    "L1": "N23"' in text
    assert 'select_hbond_acceptor:\n    "L1": "O17"' in text
    assert 'select_buried:\n    "L1": "C29"' in text


def main() -> None:
    test_biotin_atom_names_and_chemistry()
    test_directed_linker_bond_is_unambiguous()
    test_ccd_identity_is_generic_and_requires_full_chemical_identity()
    test_chemical_search_reads_every_page()
    test_incomplete_candidate_verification_is_not_a_false_negative()
    test_every_exact_ccd_is_searched_and_entries_are_deduplicated()
    test_foundry_hbond_direction_is_not_inverted()
    print("PASS ligand conditioning contracts")


if __name__ == "__main__":
    main()
