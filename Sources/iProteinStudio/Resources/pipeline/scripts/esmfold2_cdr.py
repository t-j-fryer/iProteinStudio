"""Recorded CDR-only initialization contract for ESMFold2 Full.

Uses the existing nanobody boundary resolver; this is not an alternative
antibody-numbering method or a whole-chain hallucination switch.
"""
from nanobody_cdrs import parse_explicit, parse_which_cdrs, resolve_cdrs

AA = set('ACDEFGHIKLMNPQRSTVWY')
KEY = 'studio_cdr_initialization'


def make_contract(scaffold, ranges='auto', selected='CDR1 CDR2 CDR3', chain='A', catalog=None):
    kwargs = {} if catalog is None else {'catalog_path': catalog}
    resolved = resolve_cdrs(scaffold, explicit=None if ranges == 'auto' else parse_explicit(ranges), **kwargs)
    names = parse_which_cdrs(selected)
    contract = dict(schema=1, chain=chain, scaffold=scaffold,
                    ranges={name: list(resolved['ranges'][name]) for name in names},
                    boundary_method=resolved['method'])
    positions(contract)
    return contract


def positions(contract):
    if not isinstance(contract, dict) or contract.get('schema') != 1:
        raise ValueError('Invalid ESMFold2 CDR initialization contract.')
    scaffold = contract.get('scaffold', '')
    ranges = contract.get('ranges')
    if (not isinstance(scaffold, str) or len(scaffold) < 60 or set(scaffold) - AA
            or not isinstance(contract.get('chain'), str) or not contract['chain']
            or not isinstance(ranges, dict) or not ranges
            or set(ranges) - {'CDR1', 'CDR2', 'CDR3'}):
        raise ValueError('CDR initialization requires a complete nanobody scaffold and named CDR ranges.')
    selected, previous = set(), 0
    for name in sorted(ranges):
        span = ranges[name]
        if (not isinstance(span, (list, tuple)) or len(span) != 2
                or any(type(n) is not int for n in span)
                or not previous < span[0] <= span[1] < len(scaffold)):
            raise ValueError('CDR ranges must be ordered, non-overlapping and inside the scaffold.')
        selected.update(range(span[0], span[1] + 1))
        previous = span[1]
    return selected


def validate(contract, model, chains):
    if model != 'full':
        raise ValueError('CDR X-token initialization is available only with ESMFold2 Full.')
    selected = positions(contract)
    matches = [c for c in chains if c['kind'] == 'protein' and c['id'] == contract['chain']]
    if len(matches) != 1:
        raise ValueError('CDR initialization chain is missing or ambiguous.')
    sequence = matches[0]['sequence']
    if len(sequence) != len(contract['scaffold']):
        raise ValueError('CDR initialization must preserve scaffold length.')
    if any(a != b for i, (a, b) in enumerate(zip(sequence, contract['scaffold']), 1) if i not in selected):
        raise ValueError('CDR initialization changed the preserved framework.')
    if any(c['kind'] == 'protein' and c['id'] != contract['chain'] and 'X' in c['sequence'] for c in chains):
        raise ValueError('X tokens are allowed only in the declared nanobody CDRs.')
    return selected
