"""Native input authoring and separate-process feature audit.

Do not import rfproteina and rfd4_proteina_prep in the same interpreter: both
register AtomWorks annotations. This separation is part of the qualified port.
"""
import json
import os
from pathlib import Path
import re
import sys
from .contract import atomic, normalize, sha


def runtime(root):
    from engine_registry import pinned_installation
    return pinned_installation(root, 'rfd4', Path(root) / 'components/rfd4/current')


def write_condition_spec_cif(*args, **kwargs):
    """Native writer with molecule metadata refreshed after contig assembly.

    The pinned upstream inserter can leave stale molecule_iid values when a
    generated chain is inserted before multiple preserved chains. Re-derive
    metadata from the assembled bond graph using AtomWorks' own functions,
    before upstream conditioning and strict validation. Authoring is a separate
    single-threaded process; the original entry point is restored on failure.
    """
    from rfproteina.inference_utils import condition_spec as native
    from atomworks.io.transforms.atom_array import add_id_and_entity_annotations, add_iid_annotations
    original = native.apply_contig
    def assembled(*args, **kwargs):
        atoms, numbers = original(*args, **kwargs)
        if len(set(atoms.chain_id)) > 2:
            atoms = add_id_and_entity_annotations(atoms, overwrite=True)
            atoms = add_iid_annotations(atoms, overwrite=True)
        return atoms, numbers
    native.apply_contig = assembled
    try:
        return native.write_condition_spec_cif(*args, **kwargs)
    finally:
        native.apply_contig = original


def condition_spec(cfg, source, atoms, context=None):
    chains = sorted(set(map(str, atoms.chain_id)))
    conditions = {}
    def add(name, value, selection, group=None):
        row = dict(select=selection)
        if group is not None: row['group'] = group
        conditions.setdefault(name, {}).setdefault(value, []).append(row)
    from .targets import selected_chains, residue_segments, hotspot_map
    contig = cfg['contig']
    targets = selected_chains(chains, cfg['source_target_chain']) if cfg['task'] in ('protein', 'ligand') else []
    ligand_chains=[l['chain'] for l in (context or {}).get('ligands',[])]
    if cfg['task'] in ('protein', 'ligand') and not contig:
        if cfg['binder_chain'] != 'A' or cfg['target_chain'] != 'B':
            raise ValueError('Automatic binder authoring produces binder A and targets B onward. Use an annotated CIF for other output chain IDs.')
        if cfg['task'] == 'ligand' and len(targets) != 1:
            raise ValueError('Select one ligand chain.')
        segments = [residue_segments(c, atoms.res_id[atoms.chain_id == c]) for c in [*targets,*ligand_chains]]
        contig = f"{cfg['length']}-{cfg['length']},/0," + ',/0,'.join(segments)
        for target in targets:
            if cfg['task'] == 'protein':
                # One rigid coordinate group preserves the entire assembly.
                add('C_CRDGRP', 1, f"sel('{target}/*/*/[N,CA,C,O]') and not has_nan_coord()")
            else:
                add('C_CRD', True, f"sel('{target}') and not has_nan_coord()")
            add('C_SEQ', True, f"sel('{target}')")
        for chain in ligand_chains:
            add('C_CRDGRP', 1, f"sel('{chain}') and not has_nan_coord()")
            add('C_SEQ', True, f"sel('{chain}')")
    if cfg['hotspots'] or cfg.get('hotspot_residues'):
        for target, residues in hotspot_map(cfg, targets or chains).items():
            if not residues: continue
            present = set(int(v) for v in atoms.res_id[atoms.chain_id == target])
            if not set(residues) <= present: raise ValueError('A requested hotspot is absent from the target chain.')
            selection = f"sel('{target}/*/{residues}') and not has_nan_coord()"
            if cfg['task'] == 'protein': selection += " and not sel('*/*/*/[N,CA,C,O]')"
            add('C_HOT', True, selection)
    if cfg.get('ligand_atom_conditions'):
        available=set(map(str,atoms.atom_name))
        for name,values in cfg['ligand_atom_conditions'].items():
            if name not in available: raise ValueError('Selected ligand atom is absent: '+name)
            selection=f"sel('B/*/*/{name}')"
            if 'buried' in values: add('C_RAS',1,selection)
            if 'exposed' in values: add('C_RAS',3,selection)
            if 'hotspot' in values: add('C_HOT',True,selection)
            hb=int('hbondDonor' in values)+2*int('hbondAcceptor' in values)
            if hb: add('C_HB',hb,selection)
    if cfg.get('motif'):
        from .motif import compile_spec
        contig, conditions = compile_spec(cfg['motif'], atoms)
    for row in cfg['conditions']:
        add(row['condition'], row['value'], row['selection'], row.get('group'))
    spec = dict(input=str(source), conditions=conditions)
    if contig: spec['contig'] = contig
    return spec


def author(root, cfg, destination):
    cfg = normalize(cfg)
    if cfg.get('motif') and cfg['motif'].get('source_sha256'):
        if sha(cfg['source']) != cfg['motif']['source_sha256']:
            raise ValueError('The motif source changed since inspection. Inspect and select the motif again.')
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    rt = runtime(root)
    os.environ.update(DEBUG='false', PROJECT_ROOT=str(rt / 'sources/RFD4-Proteina'))
    output = destination / 'annotated.cif'
    if cfg['task'] == 'monomer':
        import rfd4_proteina_prep
        # Bundled example is pinned with the runtime, not fetched at job time.
        example = rt / 'sources/RFD4-prep/examples/inputs/unconditional.cif'
        if not example.is_file(): raise ValueError('RFD4 runtime is missing its unconditional input example.')
        text = example.read_text()
        if '250-250' not in text: raise ValueError('Unexpected upstream unconditional template.')
        text = text.replace('250-250', f"{cfg['length']}-{cfg['length']}")
        # The native sample records these annotations as scalar CIF items.
        for name in ('expsegmin', 'expsegmax'):
            pattern = rf'(annotation_{name}_1_residue\s+)250\b'
            text, count = re.subn(pattern, lambda m: m[1] + str(cfg['length']), text)
            if count != 1: raise ValueError('Unexpected expandable-segment annotation: ' + name)
        output.write_text(text)
        atomic(destination / 'condition_spec.json', dict(source='pinned unconditional template', length=cfg['length']))
    elif cfg['task'] == 'nanobody' and cfg['scaffold_id']:
        from .inputs import nanobody_source
        nanobody_source(root, cfg, destination)
    elif cfg['annotated_input'] or cfg['task'] == 'annotated':
        source = Path(cfg['source'])
        if source.suffix.lower() != '.cif': raise ValueError('Choose an uncompressed annotated CIF.')
        if cfg['conditions'] or cfg['hotspots'] or cfg.get('hotspot_residues') or cfg['contig']:
            raise ValueError('An annotated CIF already defines its conditions. Edit a source structure to author new conditions.')
        output.write_bytes(source.read_bytes())
        atomic(destination / 'condition_spec.json', dict(source_sha256=sha(source), input_as_annotated_cif=True))
    else:
        if cfg['task'] == 'ligand' and not cfg['source']:
            from .inputs import ligand_source
            cfg = dict(cfg, source=str(ligand_source(root, cfg['ligand_smiles'], destination, cfg.get('ligand_conformer'))), source_target_chain='B')
            if cfg.get('ligand_atom_conditions'):
                names=json.loads((destination/'molecule.json').read_text())['selection_atom_map']
                if set(cfg['ligand_atom_conditions'])-set(names): raise ValueError('Selected ligand atom is absent from the inspected SMILES.')
                cfg=dict(cfg,ligand_atom_conditions={names[name]:values for name,values in cfg['ligand_atom_conditions'].items()})
        from atomworks.io.parser import parse
        from rfproteina.utils.parse_presets import RCSB_WITH_METALS
        array = parse(cfg['source'], config=RCSB_WITH_METALS.replace(build_assembly=None, altloc='first'))['asym_unit'][0]
        context=None
        if cfg.get('motif'):
            from .motif_context import prepare as prepare_motif_context
            array, cfg, context = prepare_motif_context(array,cfg,destination)
        if cfg['task'] == 'protein':
            import biotite.structure as bs
            from biotite.sequence import ProteinSequence
            from .targets import selected_chains
            from .mixed_target import prepare_target, write_components
            mixed=prepare_target(array,cfg,destination)
            if mixed:
                array,context,hot=mixed
                cfg=dict(cfg,source_target_chain=','.join(context['protein_chains']),hotspots=[],hotspot_residues=hot)
            else:
                array = array[bs.filter_amino_acids(array)]
            chains = selected_chains(array.chain_id[bs.filter_amino_acids(array)], cfg['source_target_chain'])
            identities = []
            for i, target in enumerate(chains):
                protein = array[array.chain_id == target]
                _, names = bs.get_residues(protein)
                identities.append(dict(source_chain=target, native_chain=target, output_chain=chr(66+i),
                    sequence=''.join(ProteinSequence.convert_letter_3to1(name) for name in names)))
            if not context: atomic(destination / 'target_identity.json', dict(chains=identities))
        # Preserve the original entity, bond and custom chemical-component
        # tables. A coordinate-only CIF round trip loses their connectivity.
        source = Path(cfg['source']).resolve()
        if cfg.get('motif') or (cfg['task'] == 'protein' and context) or source.suffix.lower() == '.pdb':
            from atomworks.io.utils.io_utils import to_cif_file
            source = destination / 'protein_source.cif'
            to_cif_file(array, source)
            if context:
                from .mixed_target import write_components
                write_components(source,context)
        spec = condition_spec(cfg, source, array,context)
        if cfg.get('motif'):
            from .motif_context import extend_spec
            spec = extend_spec(spec,cfg,array)
        atomic(destination / 'condition_spec.json', spec)
        write_condition_spec_cif('studio', spec, output, spec_dir=destination, validate=True)
        if cfg.get('motif'):
            from .motif_context import freeze_reference
            freeze_reference(output,cfg,destination)
    return output


def audit_features(path, cfg, destination):
    import torch
    from rfd4_proteina_prep import prepare_cif
    features, atoms = prepare_cif(path, seed=cfg['seed'], device='cpu')
    mask = features['padding_mask']
    if mask.dtype != torch.bool or mask.ndim != 2 or mask.shape[0] != 1 or not mask.all():
        raise ValueError('RFD4 preparation returned unexpected padding or sample count.')
    count = int(mask.shape[1])
    if cfg['task'] == 'monomer' and count != cfg['length']:
        raise ValueError('Prepared monomer length differs from the request.')
    if cfg['task'] in ('partial', 'inverse'):
        valid = features['atom37_mask'].bool()
        if ((~torch.isfinite(features['coords_nm']).all(-1)) & valid).any():
            raise ValueError('Partial/inverse input has missing coordinates for present atoms.')
    if cfg['task'] == 'ligand' and cfg['ligand_smiles']:
        import biotite.structure as bs
        from biotite.interface.rdkit import to_mol
        from rdkit import Chem
        # <M> is the pinned format's expandable generated-protein sentinel.
        ligand = atoms[(atoms.res_name != '<M>') & ~bs.filter_amino_acids(atoms)
                       & ~bs.filter_nucleotides(atoms) & ~bs.filter_solvent(atoms)]
        if not len(ligand) or ligand.bonds is None: raise ValueError('Native ligand search requires an explicit bonded chemical component.')
        molecule = to_mol(ligand, explicit_hydrogen=False)
        Chem.SanitizeMol(molecule)
        Chem.AssignStereochemistryFrom3D(molecule)
        expected = Chem.MolFromSmiles(cfg['ligand_smiles'])
        if expected is None or len(Chem.GetMolFrags(molecule)) != 1 or Chem.MolToSmiles(Chem.RemoveHs(molecule)) != Chem.MolToSmiles(Chem.RemoveHs(expected)):
            raise ValueError('The source ligand graph, charge or stereochemistry differs from the requested scoring SMILES.')
        if cfg.get('ligand_geometry') is not None:
            from .mixed_target import molecule_record
            record=molecule_record(ligand,'authored-ligand','B',str(ligand.res_name[0]))
            manifest=dict(smiles_used=record['smiles'],atoms=[dict(index=a['index'],name=a['name'],el=a['element']) for a in record['atoms']])
            from ligand_geometry_policy import atom_settings
            atom_settings(cfg['ligand_geometry'],cfg['ligand_smiles'],manifest)
            molecule_path=Path(path).parent/'molecule.json'
            saved=json.loads(molecule_path.read_text()) if molecule_path.exists() else {}
            atomic(molecule_path,dict(saved,geometry_manifest=manifest))
    condition_audit=[]
    if cfg.get('ligand_atom_conditions'):
        from rfd4_proteina_prep._cif.conditions import C_RAS, C_HB, C_HOT
        mapping=json.loads((Path(path).parent/'molecule.json').read_text())['selection_atom_map']
        for name,values in cfg['ligand_atom_conditions'].items():
            native=mapping[name];mask=(atoms.atom_name==native)&(atoms.chain_id=='B')
            if int(mask.sum())!=1: raise ValueError('Conditioned ligand atom identity was lost: '+name)
            expected=[]
            if 'buried' in values: expected.append((C_RAS,1))
            if 'exposed' in values: expected.append((C_RAS,3))
            if 'hotspot' in values: expected.append((C_HOT,True))
            hb=int('hbondDonor' in values)+2*int('hbondAcceptor' in values)
            if hb: expected.append((C_HB,hb))
            for condition,value in expected:
                if not (condition.annotation(atoms,default='generate')[mask]==value).all():
                    raise ValueError('Native preparation dropped a ligand atom condition: '+name)
            condition_audit.append(dict(selection_atom=name,native_atom=native,conditions=values))
    context_path=Path(path).parent/'target_ligands.json'
    context_audit=[]
    if context_path.is_file():
        from .mixed_target import audit_conditioned
        context_audit=audit_conditioned(atoms,json.loads(context_path.read_text()))
    atomic(destination, dict(passed=True, ligand_conditions=condition_audit, ligand_context=context_audit, tokens=count, input_sha256=sha(path),
                            features={k: dict(shape=list(v.shape), dtype=str(v.dtype))
                                      for k, v in features.items() if isinstance(v, torch.Tensor)}))


def main():
    action, root, config, output = sys.argv[1:]
    cfg = normalize(json.loads(Path(config).read_text()))
    if action == 'author': author_lengths(Path(root), cfg, Path(output))
    elif action == 'audit': audit_lengths(cfg, Path(output))
    else: raise ValueError('Unknown RFD4 input operation.')




def author_lengths(root, cfg, destination):
    from .contract import allocated_lengths
    cfg=normalize(cfg); destination=Path(destination)
    lengths=list(dict.fromkeys(allocated_lengths(cfg)))
    if cfg.get('ligand_conformers'):
        from .contract import allocated_conformers
        paths={};pairs=list(dict.fromkeys((row['label'],length) for row,length in zip(allocated_conformers(cfg),allocated_lengths(cfg))))
        for index,(label,length) in enumerate(pairs):
            row=next(r for r in cfg['ligand_conformers'] if r['label']==label)
            target=destination if index==0 else destination/'ligand_inputs'/label/str(length)
            author(root,dict(cfg,length=length,length_plan=None,ligand_conformers=None,ligand_conformer=row['path']),target)
            paths.setdefault(label,{})[str(length)]=str(target/'annotated.cif')
        atomic(destination/'ligand_inputs.json',paths)
        return
    if cfg.get('scaffold_weights'):
        from .contract import allocated_scaffolds
        paths={}
        for index, scaffold in enumerate(dict.fromkeys(allocated_scaffolds(cfg))):
            target=destination if index==0 else destination/'scaffold_inputs'/scaffold
            child=normalize(dict(cfg,scaffold_weights=None,scaffold_id=scaffold,cdr_ranges=''))
            author(root,child,target)
            paths[scaffold]=str(target/'annotated.cif')
        atomic(destination/'scaffold_inputs.json',paths)
        return
    if not cfg.get('length_plan'):return author(root,cfg,destination)
    for index,length in enumerate(lengths):
        target=destination if index==0 else destination/'length_inputs'/str(length)
        author(root,dict(cfg,length=length,length_plan=None),target)
    atomic(destination/'length_inputs.json',{str(length):str((destination if i==0 else destination/'length_inputs'/str(length))/'annotated.cif') for i,length in enumerate(lengths)})


def audit_lengths(cfg,destination):
    destination=Path(destination)
    if cfg.get('ligand_conformers'):
        for label,paths in json.loads((destination/'ligand_inputs.json').read_text()).items():
            for length,path in paths.items(): audit_features(path,dict(cfg,length=int(length)),Path(path).parent/'feature_audit.json')
        return
    if cfg.get('scaffold_weights'):
        for scaffold,path in json.loads((destination/'scaffold_inputs.json').read_text()).items():
            child=normalize(dict(cfg,scaffold_weights=None,scaffold_id=scaffold,cdr_ranges=''))
            audit_features(path,child,Path(path).parent/'feature_audit.json')
        return
    index=destination/'length_inputs.json'
    paths=json.loads(index.read_text()) if cfg.get('length_plan') else {str(cfg['length']):str(destination/'annotated.cif')}
    for length,path in paths.items():audit_features(path,dict(cfg,length=int(length)),Path(path).parent/'feature_audit.json')


if __name__ == '__main__': main()
