"""Explicit protein target roles shared by authoring, MSA lookup and scoring."""
import re


def selected_chains(available, selection):
    available = list(dict.fromkeys(map(str, available)))
    chains = re.split(r'[,:\s]+', selection.strip()) if selection.strip() else available
    if not chains or len(chains) != len(set(chains)) or any(c not in available for c in chains):
        raise ValueError('Choose distinct protein target chains present in the structure.')
    if len(chains) > 25:
        raise ValueError('Automatic target authoring supports up to 25 chains (B–Z).')
    return chains


def residue_segments(chain, residues):
    residues = list(dict.fromkeys(map(int, residues)))
    if not residues or any(n < 1 for n in residues) or residues != sorted(residues):
        raise ValueError('Target chains need increasing, positive residue numbering.')
    segments = []
    first = previous = residues[0]
    for number in residues[1:] + [None]:
        if number is not None and number == previous + 1:
            previous = number
            continue
        segments.append(f'{chain}{first}-{previous}' if first != previous else f'{chain}{first}')
        first = previous = number
    return ','.join(segments)


def hotspot_map(cfg, chains):
    result = {c: [] for c in chains}
    if cfg['hotspots']:
        if len(chains) != 1:
            raise ValueError('Use chain-qualified hotspots for a multichain target, for example B32 C55.')
        result[chains[0]] = list(cfg['hotspots'])
    for token in cfg.get('hotspot_residues') or []:
        match = re.fullmatch(r'([A-Za-z0-9]+):([1-9][0-9]*)|([A-Za-z])([1-9][0-9]*)', token)
        if not match:
            raise ValueError('Use chain-qualified hotspots such as B32 or B:32.')
        chain, number = (match[1], match[2]) if match[1] else (match[3], match[4])
        if chain not in result:
            raise ValueError('A hotspot names a chain outside the selected target.')
        number = int(number)
        if number in result[chain]: raise ValueError('Duplicate hotspot residue.')
        result[chain].append(number)
    return result


def target_sequences(config):
    if config.get('target_sequences'):
        return dict(config['target_sequences'])
    if config.get('target_sequence'):
        return {config['settings']['target_chain']: config['target_sequence']}
    return {}
