"""Restore CCD labels from the submitted Boltz entity map, retaining native bytes."""
from pathlib import Path
from .contract import atomic, digest
from .geometry import read


def restore(native, document, output):
    native, output = Path(native), Path(output)
    expected = {entry['ligand']['id']: entry['ligand']['ccd']
                for entry in document['sequences'] if 'ligand' in entry}
    residues = read(native)
    mapping = []
    for chain, component in expected.items():
        if not isinstance(chain, str) or len(chain) != 1 or not isinstance(component, str) or not 1 <= len(component) <= 3:
            raise ValueError('Motif beta requires one explicit CCD instance per PDB chain.')
        keys = [key for key in residues if key.split(':')[0] == chain]
        if keys != [chain + ':1:']:
            raise ValueError('Prediction ligand chain does not match the submitted entity: ' + chain)
        observed = residues[keys[0]]['component']
        if observed not in {'LIG', component}:
            raise ValueError('Unexpected native ligand label: ' + observed)
        mapping.append(dict(chain=chain, residue=1, native_component=observed, ccd=component))
    lines = native.read_text().splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.startswith(('ATOM  ', 'HETATM')) and line[21] in expected:
            lines[index] = line[:17] + f"{expected[line[21]]:>3}" + line[20:]
    output.write_text(''.join(lines))
    mapped = read(output)
    if set(mapped) != set(residues) or any(mapped[key]['atoms'] != residues[key]['atoms'] for key in residues):
        raise ValueError('Ligand-label restoration changed atoms or coordinates.')
    receipt = output.with_suffix('.identity.json')
    atomic(receipt, dict(schema=1, source='submitted Boltz CCD entities', native_sha256=digest(native),
                        mapped_sha256=digest(output), entities=mapping))
    return output, receipt
