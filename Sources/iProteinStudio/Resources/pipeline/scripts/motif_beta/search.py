"""One geometry objective for greedy and beam; no confidence-score mixing."""
import math
from .contract import POLICIES, PROFILE


def rank(rows, width, *, previous=()):
    if type(width) is not int or width < 1:
        raise ValueError('Width must be a positive integer.')
    rows = list(previous) + list(rows)
    if not rows:
        return []
    refs = {r['metrics']['reference_sha256'] for r in rows}
    if len(refs) != 1:
        raise ValueError('Candidates from different root references cannot compete.')
    identifiers = [r['id'] for r in rows]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError('Duplicate candidate IDs.')
    for r in rows:
        m = r['metrics']
        if m['profile'] != PROFILE or m['guided']:
            raise ValueError('Selection requires untemplated checks using the same scoring profile.')
        if any(not math.isfinite(m[k]) for k in ('objective', 'tie_break')):
            raise ValueError('Nonfinite ranking metric.')
    eligible = sorted((r for r in rows if r['metrics']['eligible']),
                      key=lambda r: (r['metrics']['objective'], r['metrics']['tie_break'], r['id']))
    result, seen = [], set()
    for row in eligible:
        sequence = row['metrics']['sequence']
        if sequence in seen:
            continue
        seen.add(sequence); result.append(row)
        if len(result) == width:
            break
    return result


def advance(policy, rows, width=4, previous=()):
    if policy not in POLICIES:
        raise ValueError('Unknown search policy.')
    if policy == 'fixed':
        return []  # Every cycle samples the immutable root.
    if policy == 'iterative':
        # One offspring per predeclared trajectory; no across-trajectory selection.
        if len({r['trajectory'] for r in rows}) != len(rows):
            raise ValueError('Independent iteration requires one child per trajectory.')
        return [r for r in rows if r['metrics']['eligible']]
    return rank(rows, 1 if policy == 'greedy' else width, previous=previous)


def allocation(parents, proposals):
    """Equal total evaluated-proposal budget, including beam rounds."""
    if not parents or type(proposals) is not int or proposals < 1:
        return []
    return [(parent, proposals // len(parents) + (i < proposals % len(parents)))
            for i, parent in enumerate(parents) if proposals // len(parents) + (i < proposals % len(parents))]
