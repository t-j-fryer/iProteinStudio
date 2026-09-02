#!/usr/bin/env python3
"""Install IntelliFold's Apple-MPS-safe advanced-indexing operations.

The pinned v2 and v2-flash configurations use a multidimensional advanced
index into the token-pair tensor.  On some Apple GPU/OS combinations that is
lowered to MPS GatherND and aborts with an assertion whose index width is the
atom count.  The advanced atom compaction helpers use two more formulations
with the same problem: boolean gather/scatter assignment and a scatter-then-
gather repeat.  Order-preserving ``index_select`` mappings are mathematically
identical and avoid all three unsupported GatherND paths.
"""

from __future__ import annotations

import fcntl
from pathlib import Path


PAIR_OLD = '''            row_indices = indices_row.unsqueeze(-1)
            col_indices = indices_col.unsqueeze(-2)
            row_indices, col_indices = torch.broadcast_tensors(row_indices, col_indices)
            p = add(p,p_trunk[einops.rearrange(torch.arange(p_trunk.shape[0]), "n -> n 1 1 1"), row_indices, col_indices], inplace=inplace_safe)
'''

PAIR_NEW = '''            row_indices = indices_row.unsqueeze(-1)
            col_indices = indices_col.unsqueeze(-2)
            row_indices, col_indices = torch.broadcast_tensors(row_indices, col_indices)
            # Apple MPS can abort in GatherND for the equivalent multidimensional
            # advanced index above. Flatten the token-pair axes and select each
            # batch independently; this preserves values and gradients exactly.
            pair_indices = row_indices * seq_len + col_indices
            pair_shape = pair_indices.shape[1:]
            channels = p_trunk.shape[-1]
            flat_trunk = p_trunk.reshape(p_trunk.shape[0], seq_len * seq_len, channels)
            selected_pairs = torch.stack([
                torch.index_select(flat_trunk[batch_index], 0, pair_indices[batch_index].reshape(-1))
                .reshape(*pair_shape, channels)
                for batch_index in range(p_trunk.shape[0])
            ], dim=0)
            p = add(p, selected_pairs, inplace=inplace_safe)
'''


AGGREGATE_NEW = '''def aggregate_fn_advanced(original_seqs, attention_mask):
    """Compact valid atoms without MPS boolean advanced indexing."""
    batch_size, num_tokens, max_num_atoms_per_token = attention_mask.shape[:3]
    if max_num_atoms_per_token != 24:
        raise ValueError("Only 24 atoms per token is supported")

    flat_mask = attention_mask.bool().reshape(batch_size, -1)
    # Atom masks are small, immutable inference metadata.  Build their integer
    # mappings on CPU so no Apple backend can lower boolean assignment to
    # MPSNDArrayGatherND.  Tensor values and all model computation stay on MPS.
    cpu_mask = flat_mask.detach().to(device="cpu")
    valid_indices = [
        torch.nonzero(cpu_mask[row], as_tuple=False).flatten()
        for row in range(batch_size)
    ]
    num_atoms_cpu = [int(indices.numel()) for indices in valid_indices]
    if any(count == 0 for count in num_atoms_cpu):
        raise ValueError("Some sequences have zero atoms. Please remove them before aggregation.")
    max_atoms = max(num_atoms_cpu)

    output_attention_mask = torch.stack([
        torch.arange(max_atoms, device=attention_mask.device) < count
        for count in num_atoms_cpu
    ], dim=0)

    aggregated_seqs = []
    for tensor in original_seqs:
        flattened = tensor.reshape(batch_size, num_tokens * max_num_atoms_per_token, *tensor.shape[3:])
        compacted_rows = []
        for row, cpu_indices in enumerate(valid_indices):
            selected = torch.index_select(flattened[row], 0, cpu_indices.to(device=tensor.device))
            padding = torch.zeros(
                [max_atoms - selected.shape[0], *selected.shape[1:]],
                dtype=tensor.dtype,
                device=tensor.device,
            )
            compacted_rows.append(torch.cat((selected, padding), dim=0))
        aggregated_seqs.append(torch.stack(compacted_rows, dim=0))

    def reverse_fn(compacted_seqs):
        """Restore the 24-slot representation without MPS scatter assignment."""
        restored_seqs = []
        for compacted in compacted_seqs:
            new_batch_size = compacted.shape[0]
            if new_batch_size % batch_size != 0:
                raise ValueError("Expanded batch size is not a multiple of the input batch size")
            repeats = new_batch_size // batch_size
            restored_rows = []
            for row in range(new_batch_size):
                source_row = row // repeats
                count = num_atoms_cpu[source_row]
                compact = compacted[row, :count]
                zero = torch.zeros([1, *compact.shape[1:]], dtype=compacted.dtype, device=compacted.device)
                values = torch.cat((compact, zero), dim=0)
                mapping = torch.full(
                    (num_tokens * max_num_atoms_per_token,),
                    count,
                    dtype=torch.long,
                    device="cpu",
                )
                mapping[valid_indices[source_row]] = torch.arange(count, dtype=torch.long)
                dense = torch.index_select(values, 0, mapping.to(device=compacted.device))
                restored_rows.append(
                    dense.reshape(num_tokens, max_num_atoms_per_token, *compacted.shape[2:])
                )
            restored_seqs.append(torch.stack(restored_rows, dim=0))
        return restored_seqs

    return aggregated_seqs, reverse_fn
'''


REPEAT_NEW = '''def repeat_consecutive_with_lens_advanced(feats, lens):
    """Repeat token features by atom counts without MPS scatter/gather."""
    batch, seq, *dims = feats.shape
    cpu_lens = lens.detach().to(device="cpu", dtype=torch.long)
    totals = [int(cpu_lens[row].sum().item()) for row in range(batch)]
    max_len = max(totals)
    rows = []
    for row in range(batch):
        mapping = torch.repeat_interleave(
            torch.arange(seq, dtype=torch.long),
            cpu_lens[row],
        )
        repeated = torch.index_select(feats[row], 0, mapping.to(device=feats.device))
        padding = torch.zeros(
            [max_len - repeated.shape[0], *repeated.shape[1:]],
            dtype=feats.dtype,
            device=feats.device,
        )
        rows.append(torch.cat((repeated, padding), dim=0))
    return torch.stack(rows, dim=0)
'''


def replace_definition(
    text: str,
    *,
    name: str,
    next_name: str,
    replacement: str,
    required_anchors: tuple[str, ...],
) -> tuple[str, bool]:
    marker = replacement.splitlines()[1]
    if marker in text:
        return text, False
    start_anchor = f"def {name}("
    end_anchor = f"\ndef {next_name}("
    if text.count(start_anchor) != 1:
        raise RuntimeError(f"IntelliFold source has an unexpected {name} definition count")
    start = text.index(start_anchor)
    try:
        end = text.index(end_anchor, start)
    except ValueError as exc:
        raise RuntimeError(f"IntelliFold source is missing the boundary after {name}") from exc
    original = text[start:end]
    if any(anchor not in original for anchor in required_anchors):
        raise RuntimeError(f"IntelliFold source does not match the pinned {name} anchors")
    return text[:start] + replacement.rstrip() + "\n" + text[end:], True


def patch_source(root: Path) -> str:
    source_root = root / "src" / "IntelliFold" / "intellifold" / "openfold"
    diffusion = source_root / "model" / "diffusion.py"
    conversion = source_root / "utils" / "atom_token_conversion.py"
    for source in (diffusion, conversion):
        if not source.is_file():
            raise RuntimeError(f"IntelliFold source is missing: {source}")
    lock_path = root / ".iproteinstudio-intellifold-mps.lock"
    with lock_path.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        diffusion_text = diffusion.read_text()
        if PAIR_NEW in diffusion_text and PAIR_OLD not in diffusion_text:
            pair_changed = False
        elif diffusion_text.count(PAIR_OLD) == 1:
            diffusion_text = diffusion_text.replace(PAIR_OLD, PAIR_NEW, 1)
            pair_changed = True
        else:
            raise RuntimeError(
                f"IntelliFold source does not match the pinned pair-lookup anchor: {diffusion}"
            )

        conversion_text = conversion.read_text()
        conversion_text, aggregate_changed = replace_definition(
            conversion_text,
            name="aggregate_fn_advanced",
            next_name="slice_at_dim",
            replacement=AGGREGATE_NEW,
            required_anchors=(
                "aggregated_seqs[i][output_attention_mask] = original_seqs[i][attention_mask]",
                "original_seq[attention_mask] = aggregated_seq[output_attention_mask]",
            ),
        )
        conversion_text, repeat_changed = replace_definition(
            conversion_text,
            name="repeat_consecutive_with_lens_advanced",
            next_name="pad_and_window",
            replacement=REPEAT_NEW,
            required_anchors=(
                "output_indices = output_indices.scatter",
                "output = torch.gather(feats",
            ),
        )

        changed = pair_changed or aggregate_changed or repeat_changed
        if pair_changed:
            temporary = diffusion.with_suffix(diffusion.suffix + ".part")
            temporary.write_text(diffusion_text)
            temporary.replace(diffusion)
        if aggregate_changed or repeat_changed:
            temporary = conversion.with_suffix(conversion.suffix + ".part")
            temporary.write_text(conversion_text)
            temporary.replace(conversion)
        return "applied" if changed else "already applied"


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    arguments = parser.parse_args()
    print(f"IntelliFold MPS advanced indexing: {patch_source(arguments.root.resolve())}")
