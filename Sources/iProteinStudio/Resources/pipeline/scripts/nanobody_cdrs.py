#!/usr/bin/env python3
"""Nanobody (VHH) CDR region detection for NanoHunter.

Resolves 1-based CDR1/CDR2/CDR3 sequence ranges for a nanobody binder chain,
so any inverse-folding designer (AntiFold or the MPNN family incl. AbMPNN) can
be restricted to CDR-only design.

Resolution order (most trusted first):
  1. Explicit ranges supplied by the user  (e.g. "CDR1:26-33,CDR2:51-57,CDR3:97-110")
  2. Exact sequence match in examples/nanobody_scaffolds/catalog.tsv
  3. Alignment-transfer heuristic: globally align the query to the most similar
     catalogued VHH and transfer that scaffold's curated CDR boundaries through
     the alignment. VHH frameworks are highly conserved, so boundary transfer is
     accurate for framework-similar scaffolds. Reports the reference used and the
     sequence identity so callers can judge confidence.

Depends only on the Python standard library, so it runs under any interpreter
NanoHunter uses (no numpy / biopython / ANARCI required).

CLI examples:
  # From a raw sequence, print detected ranges
  python nanobody_cdrs.py --seq EVQLVESGGG...WGQGTLVTVSS

  # From a structure, emit the MPNN --redesigned_residues spec for CDR1+CDR3
  python nanobody_cdrs.py --pdb model_0.pdb --chain A --cdrs "CDR1 CDR3" --emit residues

  # Machine-readable output
  python nanobody_cdrs.py --seq EVQL... --emit json
"""

import argparse
import csv
import json
import os
import re
import sys

CDR_NAMES = ("CDR1", "CDR2", "CDR3")

THREE_TO_ONE = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C",
    "GLN": "Q", "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I",
    "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P",
    "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
    "MSE": "M", "SEC": "U", "PYL": "O",
}

DEFAULT_CATALOG = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "examples", "nanobody_scaffolds", "catalog.tsv",
)


# --------------------------------------------------------------------------- #
# Parsing helpers
# --------------------------------------------------------------------------- #
def clean_seq(seq):
    return re.sub(r"[^A-Za-z]", "", seq or "").upper()


def parse_range(value):
    m = re.match(r"^\s*(\d+)\s*(?:-|\.\.)\s*(\d+)\s*$", value or "")
    if not m:
        raise ValueError(f"Invalid range: {value!r}")
    start, end = int(m.group(1)), int(m.group(2))
    if start < 1 or end < start:
        raise ValueError(f"Invalid range: {value!r}")
    return (start, end)


def normalize_cdr_name(raw):
    low = re.sub(r"[^a-z0-9]", "", (raw or "").lower())
    mapping = {
        "cdr1": "CDR1", "cdrh1": "CDR1", "1": "CDR1",
        "cdr2": "CDR2", "cdrh2": "CDR2", "2": "CDR2",
        "cdr3": "CDR3", "cdrh3": "CDR3", "3": "CDR3",
    }
    if low not in mapping:
        raise ValueError(f"Unknown CDR name: {raw!r} (use CDR1, CDR2, CDR3)")
    return mapping[low]


def parse_which_cdrs(raw):
    """Parse a "CDR1 CDR2 CDR3"/"CDR1,CDR3" selection into an ordered list."""
    if raw is None:
        return list(CDR_NAMES)
    toks = [t for t in re.split(r"[\s,;]+", raw.strip()) if t]
    if not toks:
        return list(CDR_NAMES)
    seen = []
    for tok in toks:
        name = normalize_cdr_name(tok)
        if name not in seen:
            seen.append(name)
    return sorted(seen, key=lambda n: CDR_NAMES.index(n))


def parse_explicit(raw):
    """Parse "CDR1:26-33,CDR2:51-57,CDR3:97-110" into {name: (s, e)}."""
    if not raw:
        return {}
    out = {}
    for m in re.finditer(
        r"\b(CDR[123]|CDRH[123])\b\s*[:=]\s*(\d+)\s*(?:-|\.\.)\s*(\d+)", raw, flags=re.I
    ):
        name = normalize_cdr_name(m.group(1))
        out[name] = (int(m.group(2)), int(m.group(3)))
    if not out:
        raise ValueError(
            f"Could not parse any CDR ranges from {raw!r}. "
            "Use e.g. CDR1:26-33,CDR2:51-57,CDR3:97-110"
        )
    return out


def extract_sequence_from_structure(path, chain):
    """Extract the single-letter sequence of `chain` from a .pdb or .cif file.

    Uses CA atoms in model 1, preserving residue order. Returns (seq, resnums)
    where resnums are the author residue numbers (1-based positions correspond
    to seq indices).
    """
    is_cif = path.lower().endswith((".cif", ".mmcif"))
    seq = []
    resnums = []
    seen = set()
    if is_cif:
        seq, resnums = _extract_from_cif(path, chain)
    else:
        with open(path) as handle:
            for line in handle:
                if not line.startswith(("ATOM", "HETATM")):
                    continue
                atom_name = line[12:16].strip()
                if atom_name != "CA":
                    continue
                alt = line[16].strip()
                if alt not in ("", "A"):
                    continue
                ch = line[21].strip()
                if ch != chain:
                    continue
                resname = line[17:20].strip().upper()
                resnum = line[22:27].strip()  # includes insertion code
                key = (ch, resnum)
                if key in seen:
                    continue
                seen.add(key)
                seq.append(THREE_TO_ONE.get(resname, "X"))
                resnums.append(resnum)
    if not seq:
        raise SystemExit(
            f"No residues found for chain {chain!r} in {path}. "
            "Check --chain."
        )
    return "".join(seq), resnums


def _extract_from_cif(path, chain):
    """Minimal mmCIF _atom_site parser (loop_ column-order aware)."""
    seq = []
    resnums = []
    seen = set()
    cols = {}
    in_loop = False
    field_order = []
    with open(path) as handle:
        lines = handle.readlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("loop_"):
            # collect following _atom_site.* headers
            field_order = []
            j = i + 1
            while j < len(lines) and lines[j].lstrip().startswith("_atom_site."):
                field_order.append(lines[j].strip())
                j += 1
            if field_order:
                cols = {name: idx for idx, name in enumerate(field_order)}
                needed = [
                    "_atom_site.label_atom_id",
                    "_atom_site.label_comp_id",
                    "_atom_site.auth_asym_id",
                    "_atom_site.auth_seq_id",
                ]
                if not all(c in cols for c in needed):
                    # fall back to label_* if auth_* missing
                    alt = {
                        "_atom_site.auth_asym_id": "_atom_site.label_asym_id",
                        "_atom_site.auth_seq_id": "_atom_site.label_seq_id",
                    }
                    for want, sub in alt.items():
                        if want not in cols and sub in cols:
                            cols[want] = cols[sub]
                if not all(c in cols for c in needed):
                    i = j
                    in_loop = False
                    continue
                model_col = cols.get("_atom_site.pdbx_PDB_model_num")
                alt_col = cols.get("_atom_site.label_alt_id")
                k = j
                while k < len(lines):
                    row = lines[k]
                    if row.startswith(("_", "#", "loop_", "data_")) or not row.strip():
                        break
                    tok = row.split()
                    if len(tok) < len(field_order):
                        k += 1
                        continue
                    if tok[cols["_atom_site.label_atom_id"]] != "CA":
                        k += 1
                        continue
                    if model_col is not None and tok[model_col] not in ("1", "."):
                        k += 1
                        continue
                    if alt_col is not None and tok[alt_col] not in (".", "", "A"):
                        k += 1
                        continue
                    if tok[cols["_atom_site.auth_asym_id"]] != chain:
                        k += 1
                        continue
                    resname = tok[cols["_atom_site.label_comp_id"]].upper()
                    resnum = tok[cols["_atom_site.auth_seq_id"]]
                    key = (chain, resnum)
                    if key not in seen:
                        seen.add(key)
                        seq.append(THREE_TO_ONE.get(resname, "X"))
                        resnums.append(resnum)
                    k += 1
                i = k
                continue
        i += 1
    return seq, resnums


# --------------------------------------------------------------------------- #
# Catalog
# --------------------------------------------------------------------------- #
def load_catalog(path):
    entries = []
    if not path or not os.path.exists(path):
        return entries
    with open(path, newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            seq = clean_seq(row.get("sequence", ""))
            if not seq:
                continue
            ranges = {}
            ok = True
            for name, col in (
                ("CDR1", "cdr1_range_1based"),
                ("CDR2", "cdr2_range_1based"),
                ("CDR3", "cdr3_range_1based"),
            ):
                raw = (row.get(col) or "").strip()
                if not raw:
                    ok = False
                    break
                try:
                    ranges[name] = parse_range(raw)
                except ValueError:
                    ok = False
                    break
            if not ok:
                continue
            entries.append(
                {
                    "id": row.get("scaffold_id") or row.get("display_name") or "?",
                    "seq": seq,
                    "ranges": ranges,
                }
            )
    return entries


# --------------------------------------------------------------------------- #
# Global (Needleman-Wunsch) alignment, pure stdlib
# --------------------------------------------------------------------------- #
def _nw_align(a, b, match=2, mismatch=-1, gap=-2):
    n, m = len(a), len(b)
    # score/traceback matrices
    score = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        score[i][0] = i * gap
    for j in range(1, m + 1):
        score[0][j] = j * gap
    tb = [[0] * (m + 1) for _ in range(n + 1)]  # 0 diag, 1 up(gap in b), 2 left(gap in a)
    for i in range(1, n + 1):
        ai = a[i - 1]
        row = score[i]
        prev = score[i - 1]
        trow = tb[i]
        for j in range(1, m + 1):
            diag = prev[j - 1] + (match if ai == b[j - 1] else mismatch)
            up = prev[j] + gap
            left = row[j - 1] + gap
            best = diag
            move = 0
            if up > best:
                best, move = up, 1
            if left > best:
                best, move = left, 2
            row[j] = best
            trow[j] = move
    # traceback -> aligned index lists (query index or None per column)
    ai, bi = n, m
    aligned = []  # list of (a_index_or_None, b_index_or_None)
    while ai > 0 or bi > 0:
        if ai > 0 and bi > 0 and tb[ai][bi] == 0:
            aligned.append((ai - 1, bi - 1))
            ai -= 1
            bi -= 1
        elif ai > 0 and (bi == 0 or tb[ai][bi] == 1):
            aligned.append((ai - 1, None))
            ai -= 1
        else:
            aligned.append((None, bi - 1))
            bi -= 1
    aligned.reverse()
    return aligned


def _identity(aligned, a, b):
    same = 0
    aln = 0
    for ai, bi in aligned:
        if ai is not None and bi is not None:
            aln += 1
            if a[ai] == b[bi]:
                same += 1
    return same / aln if aln else 0.0


def transfer_ranges(query, ref_seq, ref_ranges):
    """Transfer reference CDR boundaries onto the query via global alignment.

    Returns (ranges_dict_1based, identity_float).
    """
    aligned = _nw_align(query, ref_seq)
    identity = _identity(aligned, query, ref_seq)
    # For each column, remember which query/ref residue index sits there.
    # Map: for a reference position rp (0-based), find query position.
    out = {}
    for name in CDR_NAMES:
        if name not in ref_ranges:
            continue
        rs, re_ = ref_ranges[name]  # 1-based inclusive on ref
        rs0, re0 = rs - 1, re_ - 1
        # query residues whose aligned ref index is within [rs0, re0]
        q_in = [ai for ai, bi in aligned if ai is not None and bi is not None and rs0 <= bi <= re0]
        if q_in:
            out[name] = (min(q_in) + 1, max(q_in) + 1)
        else:
            # boundary fell entirely into query gaps: use nearest anchors
            before = [ai for ai, bi in aligned if ai is not None and bi is not None and bi < rs0]
            after = [ai for ai, bi in aligned if ai is not None and bi is not None and bi > re0]
            lo = (max(before) + 1) if before else 1
            hi = (min(after) - 1) if after else len(query)
            if hi < lo:
                hi = lo
            out[name] = (lo + 1, hi + 1)
    return out, identity


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #
def resolve_cdrs(sequence, explicit=None, catalog_path=DEFAULT_CATALOG,
                 exclude_ids=None):
    """Resolve CDR1/2/3 for a VHH sequence.

    Returns dict: {"ranges": {CDR1:(s,e),...}, "method": str, "detail": str,
                   "length": int}
    """
    seq = clean_seq(sequence)
    if len(seq) < 60:
        raise SystemExit(
            f"Sequence too short ({len(seq)} aa) to be a VHH domain."
        )
    explicit = explicit or {}
    catalog = load_catalog(catalog_path)
    if exclude_ids:
        catalog = [e for e in catalog if e["id"] not in exclude_ids]

    # 1. exact catalog match provides a trusted baseline
    ranges = {}
    method = "heuristic-align"
    detail = ""
    for entry in catalog:
        if entry["seq"] == seq:
            ranges = dict(entry["ranges"])
            method = "catalog"
            detail = f"exact match to catalog scaffold '{entry['id']}'"
            break

    # 2/3. heuristic alignment transfer for anything not exactly catalogued
    if method != "catalog":
        if catalog:
            best = None
            for entry in catalog:
                tr, ident = transfer_ranges(seq, entry["seq"], entry["ranges"])
                if best is None or ident > best[1]:
                    best = (tr, ident, entry["id"])
            ranges, ident, ref_id = best
            method = "heuristic-align"
            detail = f"boundaries transferred from '{ref_id}' ({ident * 100:.0f}% identity)"
        else:
            ranges = _motif_fallback(seq)
            method = "heuristic-motif"
            detail = "conserved-motif fallback (no catalog available)"
        # Snap CDR3 to near-universal anchors when they sit close to the
        # transferred boundary (FR4 "WGxG" Trp; the "YxC" Cys ending FR3).
        ranges = _snap_cdr3(seq, ranges)

    # 3. explicit user ranges always win, per-CDR
    if explicit:
        for name, rng in explicit.items():
            ranges[name] = rng
        applied = ",".join(sorted(explicit))
        detail = (detail + "; " if detail else "") + f"explicit override for {applied}"
        if set(explicit) >= set(CDR_NAMES):
            method = "explicit"
        elif method != "explicit":
            method = method + "+explicit"

    # sanity: clamp to sequence and enforce ordering
    L = len(seq)
    for name in list(ranges):
        s, e = ranges[name]
        s = max(1, min(s, L))
        e = max(s, min(e, L))
        ranges[name] = (s, e)

    return {"ranges": ranges, "method": method, "detail": detail, "length": L}


def _snap_cdr3(seq, ranges, tol=6):
    """Tighten a transferred CDR3 to universal anchors when they are nearby.

    FR4 begins at a conserved "WGxG" Trp; FR3 ends at a conserved "YxC" Cys.
    If either anchor sits within `tol` residues of the transferred boundary,
    snap to it. Anchors that are absent (some engineered VHHs lack canonical
    FR4) or far away are ignored, so the robust alignment transfer still wins.
    """
    if "CDR3" not in ranges:
        return ranges
    s, e = ranges["CDR3"]
    fr4 = list(re.finditer(r"WG[A-Z]G", seq))
    if fr4:
        # closest FR4 Trp to the current end
        w = min((m.start() for m in fr4), key=lambda x: abs((x) - e))
        if abs(w - e) <= tol:
            e = w  # 1-based end = residue before Trp (Trp is at index w -> pos w+1)
    ycs = [m for m in re.finditer(r"Y[A-Z]C", seq) if m.start() + 3 < e]
    if ycs:
        cys0 = ycs[-1].start() + 2  # 0-based Cys index
        cand = cys0 + 2             # 1-based first CDR3 residue after Cys
        if abs(cand - s) <= tol:
            s = cand
    if e < s:
        e = s
    ranges["CDR3"] = (s, e)
    return ranges


def _motif_fallback(seq):
    """Rough conserved-motif CDR boundaries when no catalog is available."""
    ranges = {}
    # First conserved Cys (FR1) — CDR1 starts ~4 residues later
    cys1 = seq.find("C")
    # FR2 Trp in the W-x-R-Q / W-x-x-Q motif
    fr2 = re.search(r"W[A-Z]RQ|W[A-Z]{2}Q", seq)
    if cys1 != -1 and fr2:
        ranges["CDR1"] = (cys1 + 5, max(cys1 + 5, fr2.start() - 2))
    # CDR2: ~15 residues into FR2, spanning ~8-10 residues (IMGT 56-65-ish)
    if fr2:
        c2s = fr2.end() + 14
        ranges["CDR2"] = (c2s + 1, c2s + 8)
    # Second conserved Cys near "YxC" motif -> CDR3 start; FR4 "WGxG" -> CDR3 end
    cys2 = None
    m2 = re.search(r"Y[A-Z]C", seq)
    if m2:
        cys2 = m2.start() + 2
    fr4 = re.search(r"WG[A-Z]G", seq)
    if cys2 is not None and fr4:
        ranges["CDR3"] = (cys2 + 2, fr4.start())
    return ranges


def cdr_residue_spec(ranges, chain, which=None, resnums=None):
    """Build the LigandMPNN --redesigned_residues spec for selected CDRs.

    If `resnums` (author residue labels from a structure) is given, positions
    are mapped through it; otherwise 1-based positions are used directly (valid
    for NanoHunter's sequentially numbered binder chain).
    """
    which = which or list(CDR_NAMES)
    toks = []
    for name in which:
        if name not in ranges:
            continue
        s, e = ranges[name]
        for pos in range(s, e + 1):
            if resnums is not None:
                if 1 <= pos <= len(resnums):
                    toks.append(f"{chain}{resnums[pos - 1]}")
            else:
                toks.append(f"{chain}{pos}")
    return " ".join(toks)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Detect nanobody (VHH) CDR1/CDR2/CDR3 regions."
    )
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--seq", help="VHH amino-acid sequence")
    src.add_argument("--pdb", help="structure file (.pdb/.cif) to read the sequence from")
    ap.add_argument("--chain", default="A", help="binder chain id for --pdb (default: A)")
    ap.add_argument("--cdrs", default="CDR1 CDR2 CDR3",
                    help='which CDRs to report/emit, e.g. "CDR3" or "CDR1 CDR3"')
    ap.add_argument("--explicit", default=None,
                    help='explicit ranges override, e.g. "CDR1:26-33,CDR3:97-110"')
    ap.add_argument("--catalog", default=DEFAULT_CATALOG, help="scaffold catalog TSV")
    ap.add_argument("--emit", choices=["human", "json", "residues", "ranges"],
                    default="human",
                    help="output form: human table, json, MPNN residue spec, or "
                         "compact CDR:start-end ranges")
    args = ap.parse_args(argv)

    if args.pdb:
        sequence, resnums = extract_sequence_from_structure(args.pdb, args.chain)
    else:
        sequence, resnums = clean_seq(args.seq), None

    explicit = parse_explicit(args.explicit) if args.explicit else {}
    which = parse_which_cdrs(args.cdrs)
    res = resolve_cdrs(sequence, explicit=explicit, catalog_path=args.catalog)
    ranges = res["ranges"]

    if args.emit == "residues":
        print(cdr_residue_spec(ranges, args.chain, which, resnums))
    elif args.emit == "ranges":
        print(",".join(f"{n}:{ranges[n][0]}-{ranges[n][1]}"
                        for n in which if n in ranges))
    elif args.emit == "json":
        print(json.dumps({
            "method": res["method"],
            "detail": res["detail"],
            "length": res["length"],
            "chain": args.chain,
            "ranges": {n: list(ranges[n]) for n in CDR_NAMES if n in ranges},
            "selected": which,
            "residues": cdr_residue_spec(ranges, args.chain, which, resnums),
        }, indent=2))
    else:
        print(f"VHH length : {res['length']} aa")
        print(f"Method     : {res['method']}")
        if res["detail"]:
            print(f"Detail     : {res['detail']}")
        for name in CDR_NAMES:
            if name in ranges:
                s, e = ranges[name]
                sel = "*" if name in which else " "
                sub = sequence[s - 1:e] if not resnums else "".join(
                    THREE_TO_ONE.get("", "") for _ in ()) or sequence[s - 1:e]
                print(f"  {sel} {name}: {s}-{e}  ({e - s + 1} aa)  {sequence[s-1:e]}")
        print(f"Selected   : {' '.join(which)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
