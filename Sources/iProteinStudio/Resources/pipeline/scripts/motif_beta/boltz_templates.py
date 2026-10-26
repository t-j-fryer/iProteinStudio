"""Honor explicit positions in Studio's sparse motif mmCIFs.

Boltz's native polymer parser sequence-aligns observed residues and can move a
residue inside a repeated sequence. For our marked files only, use label_seq_id
as the correspondence. All atom parsing/masking stays in upstream code. Ordinary
templates use the unmodified upstream parser. No coordinates are fabricated.
"""
from types import FunctionType, SimpleNamespace


def parse_mmcif(path, *args, **kwargs):
    import gemmi
    from boltz.data.parse import mmcif as native
    block = gemmi.cif.read(str(path)).sole_block()
    marker = block.find_value('_iproteinstudio_motif.schema')
    if not marker:
        return native.parse_mmcif(path, *args, **kwargs)
    if marker != '1':
        raise ValueError('Unsupported sparse motif coordinate mapping schema.')

    class PositionalGemmi:
        def __getattr__(self, name): return getattr(gemmi, name)

        @staticmethod
        def align_sequence_to_polymer(sequence, polymer, polymer_type, scoring):
            if polymer_type != gemmi.PolymerType.PeptideL:
                raise ValueError('Sparse motif templates support protein residues only.')
            positions = [r.label_seq for r in polymer]
            if (not positions or any(p is None or not 1 <= p <= len(sequence) for p in positions)
                    or positions != sorted(set(positions))):
                raise ValueError('Sparse motif label_seq_id must be distinct, ordered query positions.')
            for residue, pos in zip(polymer, positions):
                if residue.name != sequence[pos - 1] or residue.seqid.num != pos:
                    raise ValueError('Sparse motif residue identity/number differs from its explicit mapping.')
                if not {'N', 'CA', 'C', 'O'} <= {a.name for a in residue}:
                    raise ValueError('Sparse motif requires observed backbone frames.')
            selected = set(positions)
            return SimpleNamespace(match_string=''.join('|' if i + 1 in selected else ' ' for i in range(len(sequence))))

    # Copy function bindings, not implementation: native parser functions execute
    # unchanged against a local alignment adapter, without changing global gemmi.
    polymer = native.parse_polymer
    mapped_polymer = FunctionType(polymer.__code__, {**polymer.__globals__, 'gemmi': PositionalGemmi()},
                                 polymer.__name__, polymer.__defaults__, polymer.__closure__)
    mapped_polymer.__kwdefaults__ = polymer.__kwdefaults__
    parser = native.parse_mmcif
    mapped_parser = FunctionType(parser.__code__, {**parser.__globals__, 'parse_polymer': mapped_polymer},
                                parser.__name__, parser.__defaults__, parser.__closure__)
    mapped_parser.__kwdefaults__ = parser.__kwdefaults__
    result = mapped_parser(path, *args, **kwargs)
    structure = gemmi.make_structure_from_block(block)
    if len(structure) != 1 or len(structure[0]) != 1 or structure[0][0].name != 'A':
        raise ValueError('Sparse motif template must contain one protein chain A.')
    expected = [r.label_seq for r in structure[0][0]]
    observed = [i + 1 for i, r in enumerate(result.data.residues) if r['is_present']]
    if observed != expected:
        raise ValueError('Native Boltz parser did not preserve the explicit sparse motif positions.')
    return result


def install():
    """Install only in the beta resident process, with one preprocessing worker."""
    from boltz.data.parse import schema
    if schema.parse_mmcif is parse_mmcif:
        return
    from boltz.data.parse import mmcif
    if schema.parse_mmcif is not mmcif.parse_mmcif:
        raise ValueError('Another Boltz template parser override is active.')
    schema.parse_mmcif = parse_mmcif
