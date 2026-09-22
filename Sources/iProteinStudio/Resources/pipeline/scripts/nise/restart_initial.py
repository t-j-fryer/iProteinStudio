"""Fork audited cycle00 operations into a new campaign; never import selections."""
from pathlib import Path
import json
import shutil
from runtime import Journal, Backend, atomic, digest


def import_initial(source, output):
    from ligand_atoms import resolve, audit_atoms
    import nise_lib
    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output or (output/'phase0').exists():
        raise ValueError('Initial restart requires a fresh, separate output directory.')
    old = json.loads((source/'nise_config.json').read_text())['request']
    new = json.loads((output/'nise_config.json').read_text())['request']
    for key in ('smiles','num_starts','binder_min_len','binder_max_len','seed','hotspot_atoms','hotspot_distance','backbone_method'):
        if old.get(key) != new.get(key):
            raise ValueError('Initial restart changes generation inputs: '+key)
    if new['backbone_method'] != 'protein-hunter' or not new['selective_affinity']:
        raise ValueError('Initial checkpoint import currently supports selective-affinity Protein Hunter starts only.')
    manifest = resolve(new['smiles'])
    if json.loads((source/'ligand_atom_map.json').read_text()) != manifest:
        raise ValueError('Restart chemical state/atom mapping differs from the source.')
    staged = output/'initial_import_staging'
    if staged.exists():raise ValueError('An incomplete import must be inspected before retry.')
    staged.mkdir()
    units = []
    try:
        for index in range(new['num_starts']):
            name = f'L{index:03d}'
            unit = source/'phase0/cycle00'/name
            receipt = unit/'completed.json'
            saved = json.loads(receipt.read_text())
            if saved['input'].get('phase') != 'structure':
                raise ValueError('Initial restart requires completed structure-only receipts.')
            Journal(source).load(receipt,saved['input'])
            pred = saved['result']['prediction']
            pdb = Path(pred['pdb']).resolve()
            if unit not in pdb.parents:
                raise ValueError('Initial prediction escapes its operation directory.')
            Backend.audit_structure(pdb,saved['input']['sequence'],True)
            audit_atoms(pdb,manifest)
            parsed = nise_lib.parse_prediction(unit/'out',name)
            if not 0 <= parsed.ligand_plddt <= 100:
                raise ValueError('Missing or invalid initial ligand confidence.')
            if len(list((unit/'out/boltz_results_yaml/predictions'/name).glob('*_model_*.pdb'))) != 1:
                raise ValueError('Initial restart expects exactly one prediction per input.')
            for relative in saved['files']:
                if unit not in (source/relative).resolve().parents:
                    raise ValueError('Initial receipt references files outside its operation.')
            if any(p.is_symlink() for p in unit.rglob('*')):
                raise ValueError('Initial restart does not import symlinks.')
            target = staged/name
            shutil.copytree(unit,target,symlinks=False)
            # Only relocate the output path. Inputs, structure bytes, confidence
            # and original timing remain unchanged; provenance is explicit.
            saved['result']['prediction']['pdb'] = str(output/pdb.relative_to(source))
            atomic(target/'completed.json',saved)
            units.append(dict(name=name,source_receipt_sha256=digest(receipt),
                              imported_receipt_sha256=digest(target/'completed.json')))
        final = output/'phase0/cycle00';final.parent.mkdir()
        staged.rename(final)
        atomic(output/'ligand_atom_map.json',manifest)
        files={str(p.relative_to(output)):digest(p) for p in final.rglob('*') if p.is_file()}
        atomic(output/'initial_restart.json',dict(schema=1,source=str(source),
            source_config_sha256=digest(source/'nise_config.json'),count=len(units),units=units,files=files,
            boundary='cycle00 structures before geometry; no old pass/fail, MPNN, affinity or advancement imported'))
    except BaseException:
        # Keep the incomplete staging data for diagnosis; never silently trust it.
        raise


def validate_import(output):
    output = Path(output).resolve()
    descriptor = output/'initial_restart.json'
    data = json.loads(descriptor.read_text())
    config = json.loads((output/'nise_config.json').read_text())
    if data.get('schema') != 1 or data.get('count') != config['request']['num_starts']:
        raise ValueError('Invalid initial restart descriptor.')
    paths = [descriptor]
    for relative, sha in data['files'].items():
        path=(output/relative).resolve()
        if (output/'phase0/cycle00') not in path.parents or not path.is_file() or digest(path)!=sha:
            raise ValueError('Imported initial artifact changed: '+relative)
        paths.append(path)
    for unit in data['units']:
        path=output/'phase0/cycle00'/unit['name']/'completed.json'
        if digest(path)!=unit['imported_receipt_sha256']:
            raise ValueError('Imported initial receipt changed.')
        saved=json.loads(path.read_text());Journal(output).load(path,saved['input'])
    return paths

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('source');parser.add_argument('output');args=parser.parse_args()
    import_initial(args.source,args.output)
    validate_import(args.output)
