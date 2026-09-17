"""Prepare and validate a terminal-oxygen-only draft; no model inference or jobs."""
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(root / 'Sources/iProteinStudio/Resources/pipeline/scripts/nise'))
from contract import normalize, prediction_budget
from ligand_atoms import resolve, validate_selection
from rdkit import Chem

out = Path(__file__).resolve().parent
prior = json.loads((out.parent / '0140-biotin-beam-correction/draft_original_ligand_request.json').read_text())
request = dict(prior['request'], exposed_atoms=['O18', 'O19'])
request = normalize(request)
manifest = resolve(request['smiles'])
validate_selection(request, manifest)
mol = Chem.MolFromSmiles(manifest['smiles_used'])
carbon, carbonyl_o, hydroxyl_o = mol.GetSubstructMatch(Chem.MolFromSmarts('[CX3](=O)[OX2H1]'))
names = {a['index']: a['name'] for a in manifest['atoms']}
assert {names[carbonyl_o], names[hydroxyl_o]} == set(request['exposed_atoms'])
assert names[carbon] == 'C22'
assert {k for k in request if request[k] != prior['request'][k]} == {'exposed_atoms'}
budget = prediction_budget(request)
assert budget['initial_boltz_max'] + budget['optimization_boltz_max'] == 55208
(out / 'draft_request.json').write_text(json.dumps(dict(project=prior['project'], request=request), indent=2) + '\n')
(out / 'validation.json').write_text(json.dumps(dict(
    status='Validated draft; no execution plan or job created',
    exposed_atoms=request['exposed_atoms'], removed_exposure_atoms=['C22', 'C25'],
    changed_fields=['exposed_atoms'], atom_signature=manifest['signature'],
    exposure_min_fraction=request['exposure_min_fraction'], prediction_budget=budget), indent=2) + '\n')
print('PASS: terminal oxygens verified; only exposed_atoms changed; total prediction ceiling 55,208')
