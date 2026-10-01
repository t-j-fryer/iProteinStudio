"""Audit complete accepted outputs; do not edit raw campaign files."""
import csv, json, math, os, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'Validation/output/hunter_stages_v1'
DEV=OUT/'runtime'
os.environ['NANOHUNTER_ROOT']=str(DEV)
sys.path.insert(0,str(ROOT/'Sources/iProteinStudio/Resources/pipeline/mcp'))
sys.path.insert(0,str(ROOT/'Sources/iProteinStudio/Resources/pipeline/scripts'))
from iprotein_mcp.catalog import results_overview
from hunter_stages import verify_handoff
from validate_prediction_geometry import inspect_geometry,read_residues,cif_atom_rows
import yaml
names=['rfd3_fast_retry1','boltz_fast','boltz_full','boltz_full_resume','rfd3_ligand_boltz_retry1']
reports=[]
for name in names:
    receipt=OUT/(name+'.job.json')
    if not receipt.exists():continue
    job=json.loads(receipt.read_text())
    state=json.loads((Path.home()/'.iproteinstudio/agent/jobs'/job['id']/'state.json').read_text())
    if state['status']!='completed':
        reports.append(dict(name=name,status=state['status']));continue
    root=Path(state['output_root'])
    overview=results_overview('hunter-stages-acceptance/'+name,limit=100)
    (OUT/(name+'.overview.json')).write_text(json.dumps(overview,indent=2))
    handoff=verify_handoff(root)
    structures=[]
    for directory in sorted(root.glob('run_*/cycle_*')):
        cycle=int(directory.name.split('_')[-1]);model=next((directory/'pred_min').glob('model_0.*'))
        if model.suffix not in {'.cif','.pdb'}:raise ValueError('Unexpected structure')
        geometry=inspect_geometry(model);assert not geometry['errors'],geometry
        data=yaml.safe_load(next(directory.glob('run_*_cycle_*.yaml')).read_text())
        seq=next(e['protein']['sequence'] for e in data['sequences'] if e.get('protein',{}).get('id')=='A')
        if cycle:assert set(seq)<=set('ACDEFGHIKLMNPQRSTVWY'),seq
        residues=read_residues(model)
        assert sum('CA' in atoms for k,atoms in residues.items() if k[1]=='A')==len(seq)
        confidence=directory/'pred_min/confidence.json'
        scores=json.loads(confidence.read_text()) if confidence.exists() else {}
        if cycle:
            assert confidence.is_file()
            assert math.isfinite(scores['iptm'])
        engine=(directory/'pred_min/predictor.txt').read_text().strip()
        assert engine==(handoff['initial_engine'] if cycle==0 else handoff['refinement_engine'])
        ligand_manifest=root/'_initialization/rfd3/ligand_manifest.json'
        if ligand_manifest.exists():
            expected_atoms={a['name']:a['el'] for a in json.loads(ligand_manifest.read_text())['atoms']}
            if model.suffix=='.pdb':
                actual_atoms={line[12:16].strip():line[76:78].strip() for line in model.read_text().splitlines() if line.startswith('HETATM') and line[21]=='B'}
            else:
                columns,rows=cif_atom_rows(model);positions={v.removeprefix('_atom_site.'):i for i,v in enumerate(columns)}
                actual_atoms={r[positions['label_atom_id']]:r[positions['type_symbol']] for r in rows if r[positions['label_asym_id']]=='B'}
            assert actual_atoms==expected_atoms,(actual_atoms,expected_atoms)
            for constraint in data.get('constraints',[]):
                for chain,atom in constraint.get('pocket',{}).get('contacts',[]):
                    assert chain=='B' and atom in actual_atoms
        structures.append(dict(run=directory.parent.name,cycle=cycle,engine=engine,iptm=scores.get('iptm'),msa_policy=scores.get('msa_policy')))
    sessions=[]
    for ready in sorted(root.glob('_cycle_wave/resident_sessions/*/ready.json')):
        record=json.loads(ready.read_text());assert record['model_load_count']==1 and record['fallback']==0
        sessions.append(dict(pid=record['pid'],model_load_count=record['model_load_count'],responses=len(list((ready.parent/'responses').glob('request_*.json')))))
    if not name.endswith('_resume'):assert len(sessions)==1
    expected=int(next(iter(csv.DictReader((root/'run_001/metrics_per_cycle.csv').open())))['cycle'])
    assert expected==0
    reports.append(dict(name=name,status='passed',job=job['id'],structures=structures,sessions=sessions))
(OUT/'audit.json').write_text(json.dumps(reports,indent=2)+'\n')
print(json.dumps([{k:v for k,v in r.items() if k not in {'structures','sessions'}} for r in reports],indent=2))
if any(r['status']!='passed' for r in reports):raise SystemExit(1)
