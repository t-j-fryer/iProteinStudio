"""Root or source residue frames with explicit mapping, never tip-atom locks."""
import json
from pathlib import Path
from .contract import atomic, digest, ENGINES
from .geometry import LETTERS


def prepare(reference, sequence, engine, output):
    import gemmi
    if engine not in ENGINES:
        raise ValueError('This engine has no qualified Studio protein-template adapter.')
    reference, output = Path(reference), Path(output)
    ref = json.loads(reference.read_text())
    query_length = ref['query_length'] if ref.get('kind') == 'sparse-residue-guide' else len(ref['backbone_atoms'])
    if len(sequence) != query_length or set(sequence) - set(LETTERS.values()):
        raise ValueError('Template query must be a complete sequence with the declared length.')
    positions = sorted(int(k.split(':')[1]) for k in ref['identities'])
    for key, component in ref['identities'].items():
        if sequence[int(key.split(':')[1]) - 1] != LETTERS[component]:
            raise ValueError('Query mutates a locked catalytic residue.')
    spec = dict(reference_sha256=digest(reference), sequence=sequence, engine=engine, adapter_version=2)
    receipt = output / 'template.json'
    if receipt.exists():
        old = json.loads(receipt.read_text())
        if old['input'] != spec:
            raise ValueError('Template request changed; use a new candidate directory.')
        for name, checksum in old['files'].items():
            if digest(output / name) != checksum:
                raise ValueError('Template artifact changed: ' + name)
        return old
    output.mkdir(parents=True, exist_ok=True)
    st = gemmi.Structure(); st.name = 'motif'
    model = gemmi.Model('1'); chain = gemmi.Chain('A')
    for i, pos in enumerate(positions):
        key = f'A:{pos}:'
        res = gemmi.Residue(); res.name = ref['identities'][key]
        res.seqid = gemmi.SeqId(pos, ' '); res.entity_type = gemmi.EntityType.Polymer
        res.subchain = 'A'; res.label_seq = pos if engine == 'boltz' else i + 1
        if not {'N', 'CA', 'C', 'O'} <= set(ref['atoms'][key]['atoms']):
            raise ValueError('Mapped motif requires complete backbone frames for guidance.')
        for name, item in ref['atoms'][key]['atoms'].items():
            atom = gemmi.Atom(); atom.name = name; atom.element = gemmi.Element(item['element'])
            atom.pos = gemmi.Position(*item['xyz']); atom.occ = 1.0; atom.b_iso = 0
            res.add_atom(atom)
        chain.add_residue(res)
    model.add_chain(chain); st.add_model(model)
    entity = gemmi.Entity('1'); entity.entity_type = gemmi.EntityType.Polymer
    entity.polymer_type = gemmi.PolymerType.PeptideL; entity.subchains = ['A']
    inverse = {v: k for k, v in LETTERS.items()}
    entity.full_sequence = [inverse[a] for a in sequence] if engine == 'boltz' else [inverse[sequence[p - 1]] for p in positions]
    st.entities.append(entity)
    doc = st.make_mmcif_document(); block = doc.sole_block()
    if engine == 'boltz':
        block.set_pair('_iproteinstudio_motif.schema', '1')
    loop = block.init_loop('_entity_poly_seq.', ['entity_id', 'num', 'mon_id', 'hetero'])
    for i, component in enumerate(entity.full_sequence, 1):
        loop.add_row(['1', str(i), component, 'n'])
    # Required by AlphaFold-derived template parsers.
    comps = block.init_loop('_chem_comp.', ['id', 'type'])
    for component in sorted(set(entity.full_sequence)):
        comps.add_row([component, "'L-peptide linking'"])
    cif = output / 'motif.cif'; doc.write_file(str(cif))
    if engine == 'boltz':
        fragment = dict(templates=[dict(cif=str(cif.resolve()), chain_id=['A'], template_id=['A'])])
    elif engine == 'protenix-v2':
        fragment = dict(target_template=dict(path=str(cif.resolve()), sha256=digest(cif),
            mode='guide', scope='motif-beta', query_chains=['A'],
            motif_query_indices=[p - 1 for p in positions], query_sequence=sequence))
    else:
        # Explicit A3M columns preserve the insertion map even when all other
        # residues mutate. No sequence search or arbitrary short-fragment match.
        template_id = 'u' + digest(cif)[:3]
        mmcif = output / 'mmcif'; mmcif.mkdir(exist_ok=True)
        (mmcif / (template_id + '.cif')).write_bytes(cif.read_bytes())
        hit = ''.join(a if i + 1 in positions else '-' for i, a in enumerate(sequence))
        a3m = output / 'motif.a3m'
        a3m.write_text(f'>{template_id}_A/1-{len(positions)} mol:protein length:{len(positions)}\n{hit}\n')
        msa = output / 'query.a3m'; msa.write_text('>query\n' + sequence + '\n')
        dates = output / 'release_dates.json'
        atomic(dates, {template_id: dict(release_date='2000-01-01')})
        manifest = output / 'intellifold_manifest.json'
        normalized = mmcif / (template_id + '.cif')
        atomic(manifest, dict(schema=1, kind='iproteinstudio-intellifold-user-template',
            source=str(reference.resolve()), source_sha256=digest(reference), template_id=template_id,
            allowed_template_ids=[template_id], mmcif_dir=str(mmcif.resolve()),
            normalized_mmcif=str(normalized.resolve()), normalized_mmcif_sha256=digest(normalized),
            release_dates=str(dates.resolve()), release_dates_sha256=digest(dates),
            binder_template='selected', a3m_by_query_chain={'A': str(a3m.resolve())},
            msa_by_query_chain={'A': str(msa.resolve())},
            mappings=[dict(query_chain='A', template_chain='A', a3m=str(a3m.resolve()),
                           a3m_sha256=digest(a3m), query_indices=[p - 1 for p in positions],
                           template_indices=list(range(len(positions))))]))
        fragment = dict(protein_template=str(a3m.resolve()), protein_msa=str(msa.resolve()),
                        resident_manifest=str(manifest.resolve()))
    result = dict(input=spec, query_positions_1based=positions, mode='guide', atomic_lock=False,
                  coordinate_source=ref.get('source_mode', 'rfd3-root'),
                  required_adapter='motif_beta.boltz_templates' if engine == 'boltz' else None,
                  fragment=fragment, files={str(p.relative_to(output)): digest(p)
                                           for p in output.rglob('*') if p.is_file() and p != receipt},
                  qualification='Input adapter only; inspect native features before enabling cycling.')
    atomic(receipt, result)
    return result
