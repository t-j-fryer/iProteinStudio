"""Search budget and exact Boltz upper-bound selection; no model dependencies."""
import math
from collections import deque


def proposal_levels(maximum, adaptive, initial):
    if not adaptive:
        return [maximum]
    levels = [min(initial, maximum)]
    while levels[-1] < maximum:
        levels.append(min(maximum, levels[-1] * 2))
    return levels


def affinity_selection(nodes, score_batch, group, per_group=1, total_groups=None,
                       minimum=0.0, batch_size=8, previous=()):
    """Score enough eligible candidates to preserve each relevant top-k.

    P(bind) is in [0,1]. Ties are evaluated, never pruned. For diverse seeds,
    only the best member of each lineage contributes to the global boundary.
    Previously scored top-up candidates participate in the same boundary.
    Returns scored nodes and explicit reasons for unscored nodes.
    """
    pending = deque(sorted(nodes, key=lambda n: (-n.ligand_plddt, n.name)))
    for node in pending:
        if not math.isfinite(node.ligand_plddt) or not 0 <= node.ligand_plddt <= 100:
            raise ValueError(f"Invalid ligand pLDDT for {node.name}")
    scored, skipped = [], {}
    eligible = list(previous)

    def boundary(node):
        same = sorted((n.score for n in eligible if group(n) == group(node)), reverse=True)
        limit = max(minimum, same[per_group - 1] if len(same) >= per_group else minimum)
        if total_groups is not None:
            best = {}
            for n in eligible:
                best[group(n)] = max(best.get(group(n), -math.inf), n.score)
            values = sorted(best.values(), reverse=True)
            if len(values) >= total_groups:
                limit = max(limit, values[total_groups - 1])
        return limit

    while pending:
        batch = []
        while pending and len(batch) < batch_size:
            node = pending.popleft()
            if node.ligand_plddt / 100 + 1 < boundary(node):
                skipped[node.name] = "score_upper_bound_below_selection_boundary"
            else:
                batch.append(node)
        if not batch:
            continue
        score_batch(batch)
        for node in batch:
            if node.score is None or not math.isfinite(node.score) or not 0 <= node.score <= 2:
                raise ValueError(f"Invalid combined Boltz score for {node.name}")
            scored.append(node)
            if node.score >= minimum:
                eligible.append(node)
    return scored, skipped
