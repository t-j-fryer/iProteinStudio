# Exact masked-scaffold MSA implementation extracted from nanohunter_run.sh.
import csv
import re
import sys
from pathlib import Path

(
    base_a3m,
    out_a3m,
    binder_seq,
    scaffold_seq,
    mask_regions_raw,
    ranges_raw,
    catalog_tsv,
    max_seqs_raw,
    mask_char,
) = sys.argv[1:10]

base_a3m = Path(base_a3m)
out_a3m = Path(out_a3m)
binder_seq = re.sub(r"[^A-Za-z-]", "", binder_seq).upper()
scaffold_seq = re.sub(r"[^A-Za-z]", "", scaffold_seq).upper()
max_seqs = max(1, int(max_seqs_raw))
mask_char = mask_char.upper()
if mask_char not in {"-", "X"}:
    raise SystemExit("Internal error: scaffold MSA mask char must be '-' or 'X'.")
if not binder_seq or not scaffold_seq:
    raise SystemExit("Cannot write scaffold MSA without binder and scaffold sequences.")
if len(binder_seq) != len(scaffold_seq):
    raise SystemExit(
        f"Current binder length {len(binder_seq)} does not match scaffold length {len(scaffold_seq)}."
    )

DEFAULT_RANGES = {
    "CDR1": (27, 38),
    "CDR2": (56, 65),
    "CDR3": (105, 117),
}


def expand_regions(raw):
    tokens = [t.strip().upper() for t in re.split(r"[\s,;]+", raw or "") if t.strip()]
    if not tokens:
        return ["CDR3"]
    out = []
    for tok in tokens:
        tok = {"CDRH1": "CDR1", "CDRH2": "CDR2", "CDRH3": "CDR3"}.get(tok, tok)
        if tok in {"ALL", "ALLH", "CDRH"}:
            out.extend(["CDR1", "CDR2", "CDR3"])
        elif tok in {"CDR1", "CDR2", "CDR3"}:
            out.append(tok)
        else:
            raise SystemExit(f"Unsupported scaffold MSA mask CDR region: {tok}")
    return [r for r in ["CDR1", "CDR2", "CDR3"] if r in out]


def parse_range_value(value):
    m = re.match(r"^\s*(\d+)\s*(?:-|\.\.)\s*(\d+)\s*$", value or "")
    if not m:
        raise ValueError(value)
    start, end = int(m.group(1)), int(m.group(2))
    if start < 1 or end < start:
        raise ValueError(value)
    return start, end


def load_catalog_ranges():
    path = Path(catalog_tsv)
    if not path.exists():
        return {}
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            seq = re.sub(r"[^A-Za-z]", "", row.get("sequence", "")).upper()
            if seq != scaffold_seq:
                continue
            return {
                "CDR1": parse_range_value(row.get("cdr1_range_1based", "")),
                "CDR2": parse_range_value(row.get("cdr2_range_1based", "")),
                "CDR3": parse_range_value(row.get("cdr3_range_1based", "")),
            }
    return {}


def parse_override_ranges():
    raw = (ranges_raw or "").strip()
    if not raw or raw.lower() in {"auto", "none", "null"}:
        return {}
    out = {}
    for match in re.finditer(
        r"\b(CDR[123]|CDRH[123])\b\s*[:=]\s*(\d+)\s*(?:-|\.\.)\s*(\d+)",
        raw,
        flags=re.I,
    ):
        region = match.group(1).upper().replace("CDRH", "CDR")
        start, end = int(match.group(2)), int(match.group(3))
        if start < 1 or end < start:
            raise SystemExit(f"Invalid {region} scaffold MSA mask range: {start}-{end}")
        out[region] = (start, end)
    if not out:
        raise SystemExit(
            "--nanobody-seed-cdr-ranges must look like CDR1:26-33,CDR2:51-57,CDR3:97-110"
        )
    return out


regions = expand_regions(mask_regions_raw)
ranges = dict(DEFAULT_RANGES)
ranges.update(load_catalog_ranges())
ranges.update(parse_override_ranges())
mask_positions = set()
for region in regions:
    start, end = ranges[region]
    if end > len(scaffold_seq):
        raise SystemExit(
            f"{region} scaffold MSA mask range {start}-{end} exceeds scaffold length {len(scaffold_seq)}."
        )
    mask_positions.update(range(start - 1, end))


def read_a3m(path):
    records = []
    header = None
    parts = []
    for raw in path.read_text(errors="ignore").splitlines():
        if raw.startswith(">"):
            if header is not None:
                records.append((header, "".join(parts)))
            header = raw[1:].strip() or "sequence"
            parts = []
        else:
            parts.append(raw.strip())
    if header is not None:
        records.append((header, "".join(parts)))
    return records


def read_msa_records(path):
    if path.suffix.lower() == ".csv":
        records = []
        with path.open(newline="") as handle:
            reader = csv.DictReader(handle)
            if not {"sequence", "key"}.issubset(reader.fieldnames or []):
                raise SystemExit(
                    f"Invalid scaffold MSA CSV {path}: expected columns sequence,key."
                )
            for i, row in enumerate(reader):
                seq = (row.get("sequence") or "").strip()
                if not seq:
                    continue
                key = str(row.get("key") or f"row_{i}").strip() or f"row_{i}"
                records.append((key, seq))
        return records
    return read_a3m(path)


def aligned_columns(seq):
    # Drop A3M insertions and dots; keep aligned residues/gaps.
    return "".join(ch for ch in seq if not ch.islower() and ch != ".").upper()


def clean_aligned(seq):
    allowed = set("ACDEFGHIKLMNPQRSTVWYX-")
    return "".join(ch if ch in allowed else "X" for ch in seq.upper())


def mask_support(seq):
    chars = list(clean_aligned(seq))
    if len(chars) != len(scaffold_seq):
        return None
    for idx in mask_positions:
        chars[idx] = mask_char
    return "".join(chars)


def wrap(seq, width=160):
    return "\n".join(seq[i : i + width] for i in range(0, len(seq), width))


query = clean_aligned(binder_seq)
if len(query) != len(scaffold_seq):
    raise SystemExit("Current binder sequence has unexpected aligned length.")

support = []
seen = {query}
for header, seq in read_msa_records(base_a3m):
    aligned = aligned_columns(seq)
    masked = mask_support(aligned)
    if masked is None:
        continue
    if masked in seen:
        continue
    seen.add(masked)
    support.append((header, masked))
    if len(support) >= max(0, max_seqs - 1):
        break

if not support and max_seqs > 1:
    fallback = mask_support(scaffold_seq)
    if fallback and fallback not in seen:
        support.append(("masked_scaffold_support", fallback))

out_a3m.parent.mkdir(parents=True, exist_ok=True)
with out_a3m.open("w") as handle:
    handle.write(">query\n")
    handle.write(wrap(query) + "\n")
    for i, (header, seq) in enumerate(support, start=1):
        safe_header = re.sub(r"\s+", "_", header)[:120] or f"support_{i}"
        handle.write(f">masked_{i}_{safe_header}\n")
        handle.write(wrap(seq) + "\n")
