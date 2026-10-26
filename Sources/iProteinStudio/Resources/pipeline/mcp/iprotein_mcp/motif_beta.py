"""Public typed entry points for the existing bounded desktop motif workbench."""
import importlib.util
import json

from .common import StudioError, project_root, runtime_root, validate_slug
from .desktop import desktop_plan
from .memory import memory_request


def contract():
    path = runtime_root() / 'scripts/motif_beta/contract.py'
    if not path.is_file():
        raise StudioError('The installed motif beta adapter is missing. Update Studio before planning.')
    spec = importlib.util.spec_from_file_location('studio_public_motif_beta', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def catalog():
    module = contract()
    return dict(profile=module.PROFILE, scope='Pinned AME-41 benchmark motifs; not arbitrary motif import',
                qualification='CPU input/feature checks; full guided/untemplated model cycle qualification remains pending.',
                cases=[dict(case_id=c['case_id'], pdb_id=c['pdb_id'],
                            source_sha256=c['source_sha256'],
                            motif_residues=len(c['protein_motif']),
                            ligands=[dict(component=r['component'], chain=r['chain'], residue=r['residue']) for r in c['ligands']])
                       for c in module.catalog()['cases']])


@memory_request
def plan(request):
    project = validate_slug(request.get('project', ''))
    name = validate_slug(request.get('run_name', ''), 'run name')
    try:
        settings = contract().normalize(request.get('request', {}))
    except (ValueError, KeyError, OSError) as exc:
        raise StudioError(str(exc)) from exc
    output = project_root(project) / 'motif_beta' / name
    try:
        output.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise StudioError('Motif output already exists. Resume its saved job or choose a new run name.') from exc
    (output / 'motif_beta_request.json').write_text(json.dumps(settings, indent=2) + '\n')
    return desktop_plan(dict(project=project, workflow='motif_beta', output=str(output)))
