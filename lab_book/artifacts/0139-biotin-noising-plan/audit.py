"""Read-only chemistry and budget audit; no models, plans or jobs started."""
import argparse,hashlib,json,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'Sources/iProteinStudio/Resources/pipeline/scripts/nise'))
import contract
from ligand_atoms import resolve,validate_selection
from rdkit import Chem
from rdkit.Chem import rdMolDescriptors, rdFreeSASA
from rdkit.Chem.Draw import rdMolDraw2D

def isolated_selected_sasa(manifest, names):
    """One generated conformer, using the pipeline's heavy-atom SASA protocol."""
    molecule = Chem.RWMol()
    conformer = Chem.Conformer(len(manifest['atoms']))
    radii = []
    for i, atom in enumerate(manifest['atoms']):
        element = Chem.Atom(atom['el'])
        molecule.AddAtom(element)
        conformer.SetAtomPosition(i, (atom['x'], atom['y'], atom['z']))
        radii.append(Chem.GetPeriodicTable().GetRvdw(element.GetAtomicNum()))
    molecule.AddConformer(conformer)
    opts = rdFreeSASA.SASAOpts(rdFreeSASA.ShrakeRupley, rdFreeSASA.Protor, 1.4)
    rdFreeSASA.CalcSASA(molecule, radii, opts=opts)
    result = {a['name']: float(molecule.GetAtomWithIdx(i).GetProp('SASA'))
              for i, a in enumerate(manifest['atoms']) if a['name'] in names}
    assert all(value > 0.1 for value in result.values())
    return result

p=argparse.ArgumentParser();p.add_argument('--old-run',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
out=args.output;out.mkdir(parents=True,exist_ok=True)
old=json.loads((args.old_run/'nise_config.json').read_text())['request'];prior_map=json.loads((args.old_run/'ligand_atom_map.json').read_text())
manifest=resolve(old['smiles']);validate_selection(old,manifest)
assert manifest['signature']==prior_map['signature']
mol=Chem.MolFromSmiles(manifest['smiles_used'])
for atom,entry in zip(mol.GetAtoms(),manifest['atoms']):atom.SetProp('atomNote',entry['name'])
by_name={a['name']:a['index'] for a in manifest['atoms']}
acid=mol.GetSubstructMatch(Chem.MolFromSmarts('[CX3](=O)[OX2H1]'))
assert len(acid)==3
carbonyl,oxygen,hydroxyl=acid
ring=set(i for ring in mol.GetRingInfo().AtomRings() for i in ring)
urea=mol.GetSubstructMatch(Chem.MolFromSmarts('[N;R][C;R](=[O])[N;R]'))
head=ring|set(urea)
assert set(by_name[n] for n in old['hotspot_atoms'])==head
assert {carbonyl,oxygen,hydroxyl}.issubset(set(by_name[n] for n in old['exposed_atoms']))
alpha=next(a.GetIdx() for a in mol.GetAtomWithIdx(carbonyl).GetNeighbors() if a.GetSymbol()=='C')
assert set(by_name[n] for n in old['exposed_atoms'])=={carbonyl,oxygen,hydroxyl,alpha}
rows=[]
for a,e in zip(mol.GetAtoms(),manifest['atoms']):
 role='ureido carbonyl oxygen' if a.GetIdx()==urea[2] else ('bicyclic head' if a.GetIdx() in head else ('acid carbonyl carbon' if a.GetIdx()==carbonyl else ('acid carbonyl oxygen' if a.GetIdx()==oxygen else ('acid hydroxyl oxygen (replaced on amidation)' if a.GetIdx()==hydroxyl else ('tail methylene adjacent to carbonyl' if a.GetIdx()==alpha else 'valeric tail methylene')))))
 rows.append(dict(name=e['name'],index=e['index'],element=e['el'],role=role,selection='Bind' if e['name'] in old['hotspot_atoms'] else ('Expose' if e['name'] in old['exposed_atoms'] else 'None'),neighbors=[manifest['atoms'][n.GetIdx()]['name'] for n in a.GetNeighbors()]))
colors={by_name[n]:(.98,.66,.24) for n in old['hotspot_atoms']};colors.update({by_name[n]:(.40,.75,.98) for n in old['exposed_atoms']})
draw=rdMolDraw2D.MolDraw2DSVG(1100,650);draw.drawOptions().annotationFontScale=.8
draw.DrawMolecule(mol,legend='Previous free-biotin selections: orange = Bind; blue = Expose',highlightAtoms=list(colors),highlightAtomColors=colors);draw.FinishDrawing();(out/'previous_biotin_atoms.svg').write_text(draw.GetDrawingText())
# A chemically explicit, minimal amide cap for discussion, NOT a protein-bound model.
editable=Chem.RWMol(Chem.MolFromSmiles(manifest['smiles_used']));editable.ReplaceAtom(hydroxyl,Chem.Atom('N'));newcarbon=editable.AddAtom(Chem.Atom('C'));editable.AddBond(hydroxyl,newcarbon,Chem.BondType.SINGLE)
cap=editable.GetMol();Chem.SanitizeMol(cap);cap_smiles=Chem.MolToSmiles(cap,isomericSmiles=True)
cap_manifest=resolve(cap_smiles);capmol=Chem.MolFromSmiles(cap_manifest['smiles_used'])
cap_ring=set(i for ring in capmol.GetRingInfo().AtomRings() for i in ring)
cap_urea=capmol.GetSubstructMatch(Chem.MolFromSmarts('[N;R][C;R](=[O])[N;R]'));cap_head=cap_ring|set(cap_urea)
amide=capmol.GetSubstructMatch(Chem.MolFromSmarts('[C;!R](=[O])[N;!R][C]'));assert len(amide)==4
cap_alpha=next(a.GetIdx() for a in capmol.GetAtomWithIdx(amide[0]).GetNeighbors() if a.GetSymbol()=='C')
cap_exposed=set(amide)|{cap_alpha}
cap_hotspots=[e['name'] for e in cap_manifest['atoms'] if e['index'] in cap_head]
cap_exposure=[e['name'] for e in cap_manifest['atoms'] if e['index'] in cap_exposed]
for a,e in zip(capmol.GetAtoms(),cap_manifest['atoms']):a.SetProp('atomNote',e['name'])
colors={i:(.98,.66,.24) for i in cap_head};colors.update({i:(.40,.75,.98) for i in cap_exposed})
draw=rdMolDraw2D.MolDraw2DSVG(1100,650);draw.drawOptions().annotationFontScale=.8
draw.DrawMolecule(capmol,legend='Discussion only: N-methylbiotinamide cap; attached protein is NOT represented',highlightAtoms=list(colors),highlightAtomColors=colors);draw.FinishDrawing();(out/'amide_proxy_atoms.svg').write_text(draw.GetDrawingText())
settings=contract.normalize(dict(smiles=old['smiles'],num_starts=1000,backbone_method='protein-hunter',
    trajectories=8,beam=3,first_cycle_seqs=64,nise_seqs=32,max_cycles=30,patience=4,
    partial_noising=True,noise_radius=6.0,noise_percent=25.0,noise_predictions=32,noise_mpnn_seqs=32,noise_advance=1,
    selective_affinity=True,adaptive_proposals=False,early_score_gate=.8,min_improvement=.01,
    phase0_refine_cycles=2,phase0_seqs1=3,phase0_gate_seqs=3,phase0_seqs2=5,
    phase0_nesso_screen=False,nesso_screen=False,scheduler='resident',seed=0,
    binder_min_len=65,binder_max_len=150,preorganisation=False,
    hotspot_atoms=old['hotspot_atoms'],exposed_atoms=old['exposed_atoms'],hotspot_distance=6.0,exposure_min_fraction=.5,
    ligand_atom_signature=manifest['signature'],ligand_atoms_generated_for=old['smiles']))
validate_selection(settings,manifest)
budget=contract.prediction_budget(settings)
summary=dict(status='chemistry review pending; no job or immutable execution plan created',
    old_run=str(args.old_run),source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.old_run/'nise_config.json',args.old_run/'ligand_atom_map.json')},
    atom_map_matches_saved=True,previous_atom_roles=rows,
    old_formula=rdMolDescriptors.CalcMolFormula(mol),old_stereo=Chem.FindMolChiralCenters(mol,includeUnassigned=True),
    old_atom_manifest=manifest,
    amide_proxy=dict(status='illustrative minimal cap, not approved chemistry or full lysine/protein',smiles=cap_smiles,
        formula=rdMolDescriptors.CalcMolFormula(capmol),hotspot_atoms=cap_hotspots,exposed_atoms=cap_exposure,manifest=cap_manifest),
    proposed_settings_on_original_free_biotin=settings,prediction_budget=budget,
    total_boltz_upper_bound=budget['initial_boltz_max']+budget['optimization_boltz_max'],
    first_refinement_affinity_max=6000,seed_expansion_affinity_max=15000,
    affinity_head_max=21000+budget['optimization_boltz_max'],
    throughput_estimate=None,
    gating=dict(hotspot='each selected atom within 6 A of a binder heavy atom; not a hydrogen-bond constraint',
                exposed='each selected atom retains at least 50% of its isolated-ligand SASA; 1.4 A water probe',
                phase0_refinement='atom checks; no RMSD rejection; first-round score gate >=0.80',
                phase0_unrestrained_gate='Ca RMSD <2 A, atom checks, no affinity',
                optimization='Ca RMSD <2.5 A; ligand RMSD <2.5 A from optimisation cycle 3; atom checks every cycle'))
summary['old_isolated_exposed_sasa_A2'] = isolated_selected_sasa(manifest, old['exposed_atoms'])
summary['proxy_isolated_exposed_sasa_A2'] = isolated_selected_sasa(cap_manifest, cap_exposure)
(out/'audit.json').write_text(json.dumps(summary,indent=2)+'\n')
(out/'draft_original_ligand_request.json').write_text(json.dumps(dict(project='test2',request=settings),indent=2)+'\n')
print(json.dumps({k:summary[k] for k in ('atom_map_matches_saved','previous_atom_roles','prediction_budget','total_boltz_upper_bound','affinity_head_max')},indent=2))
print('AMIDE PROXY',cap_smiles,cap_hotspots,cap_exposure)
