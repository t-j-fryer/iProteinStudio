#!/usr/bin/env python3
"""Build the OpenFold-3 query JSON for an iProteinStudio template YAML.

This is the single implementation used by both standalone prediction and the
iterative runner.  In particular, it preserves the distinction between an
explicit `msa: empty` request and an omitted MSA policy.

Prints "true" if any chain still needs the MSA server, "false" otherwise —
the same contract the runner's function had.

Usage:
    openfold_query_json.py TEMPLATE_YAML BINDER_SEQ QUERY_NAME OUT_JSON \
                           [TARGET_MSA_PATH] [BINDER_MSA_PATH] [BASE_SEED]
"""

import sys

if len(sys.argv) < 5:
    raise SystemExit(
        "usage: openfold_query_json.py TEMPLATE_YAML BINDER_SEQ QUERY_NAME OUT_JSON "
        "[TARGET_MSA_PATH] [BINDER_MSA_PATH]"
    )
# Pad optional trailing arguments for the legacy runner call contract.
while len(sys.argv) < 7:
    sys.argv.append("")

import json, sys
from pathlib import Path

template, binder_seq, query_name, out_json, target_msa_path, binder_msa_path = sys.argv[1:7]
base_seed = int(sys.argv[7]) if len(sys.argv) > 7 and sys.argv[7] else 42

def strip_quotes(v: str) -> str:
    v = v.strip()
    if (v.startswith("'") and v.endswith("'")) or (v.startswith('"') and v.endswith('"')):
        return v[1:-1]
    return v

def usable(v: str) -> bool:
    low = v.strip().lower()
    return bool(v.strip()) and low not in {"empty", "none", "null"}

def parse_yaml_sequences(path: str):
    items = []
    cur = None
    list_key = None
    for raw in open(path):
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("- ") and s.endswith(":"):
            key = s[2:-1].strip()
            if key in {"protein", "rna", "dna", "ligand"}:
                if cur:
                    items.append(cur)
                cur = {"kind": key}
                list_key = None
                continue
        if cur is None:
            continue
        if list_key and s.startswith("- "):
            cur.setdefault(list_key, []).append(strip_quotes(s[2:].strip()))
            continue
        if ":" not in s:
            continue
        k, v = s.split(":", 1)
        k = k.strip()
        v = v.strip()
        if not v and k in {"ccd_codes", "chain_ids"}:
            cur[k] = []
            list_key = k
            continue
        list_key = None
        if v.startswith("[") and v.endswith("]"):
            vals = [strip_quotes(x.strip()) for x in v[1:-1].split(",") if x.strip()]
            cur[k] = vals
        else:
            cur[k] = strip_quotes(v)
    if cur:
        items.append(cur)
    return items

def chain_id_of(item):
    cid = item.get("id")
    if cid:
        return str(cid)
    cids = item.get("chain_ids")
    if isinstance(cids, list) and cids:
        return str(cids[0])
    if isinstance(cids, str) and cids:
        return cids
    return ""

entries = parse_yaml_sequences(template)
out_chains = []
need_server = False
has_real_msa = False

for e in entries:
    kind = str(e.get("kind", "")).lower()
    cid = chain_id_of(e)
    if not kind or not cid:
        continue

    if kind in {"protein", "rna", "dna"}:
        seq = str(e.get("sequence", "")).strip()
        msa = str(e.get("msa", "")).strip()
        # Studio writes an explicit `msa: empty` when the scientist chose
        # single-sequence inference.  That is materially different from an
        # omitted MSA setting, which asks OpenFold to search the server.  Keep
        # that distinction while retaining the positional paths for legacy
        # NanoHunter callers whose older templates did not embed paths.
        msa_was_explicit = "msa" in e
        if cid == "A" and kind == "protein":
            seq = binder_seq
            if binder_msa_path:
                msa = binder_msa_path
        elif (kind in {"protein", "rna"} and (not usable(msa))
              and target_msa_path and not msa_was_explicit):
            msa = target_msa_path
        if not seq:
            continue
        row = {
            "molecule_type": kind,
            "chain_ids": [cid],
            "sequence": seq,
        }
        if kind in {"protein", "rna"}:
            if usable(msa):
                row["main_msa_file_paths"] = [msa]
                has_real_msa = True
            elif not msa_was_explicit:
                need_server = True
        out_chains.append(row)
        continue

    if kind == "ligand":
        row = {
            "molecule_type": "ligand",
            "chain_ids": [cid],
        }
        smiles = str(e.get("smiles", "")).strip()
        ccd_codes = e.get("ccd_codes")
        if smiles:
            row["smiles"] = smiles
        elif isinstance(ccd_codes, list) and ccd_codes:
            row["ccd_codes"] = [str(x) for x in ccd_codes if str(x).strip()]
        elif isinstance(ccd_codes, str) and ccd_codes.strip():
            row["ccd_codes"] = [ccd_codes.strip()]
        else:
            continue
        out_chains.append(row)

payload = {
    "seeds": [base_seed],
    "queries": {
        query_name: {
            "chains": out_chains,
            # OpenFold supports MSA-free inference directly.  Enable its MSA
            # feature pipeline only when at least one real alignment is present
            # or a genuinely unspecified chain still needs the server.  Mixed
            # folds are supported: chains with no MSA path are intentionally
            # skipped by OpenFold's inference MSA parser.
            "use_msas": has_real_msa or need_server,
            "use_main_msas": has_real_msa or need_server,
            "use_paired_msas": False,
        }
    },
}

Path(out_json).parent.mkdir(parents=True, exist_ok=True)
with open(out_json, "w") as f:
    json.dump(payload, f, indent=2)

print("true" if need_server else "false")
