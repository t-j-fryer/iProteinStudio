"""Declare tiny benign launch fixtures and their engine/workflow coverage."""
import hashlib
import json
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
manifest_path = HERE / 'manifest.json'
m = json.loads(manifest_path.read_text())
managed = Path.home() / '.iproteinstudio'
fixtures = managed / 'projects' / m['project'] / 'acceptance-inputs'
fixtures.mkdir(parents=True, exist_ok=True)
seq, msa = m['fixture']['sequence'], m['fixture']['msa']
backbone = ROOT / 'Validation/output/apple_runtime_release_v4/protenix_msa_20260920T020113Z/baseline/attempt_001/unit_00/prediction/sumo/seed_42/predictions/sumo_sample_0.cif'
shutil.copy2(backbone, fixtures / 'sumo.cif')
# Use the runner's normal block-YAML format. Chain A is the designed chain.
def template(name, binder, ligand=None):
    path = fixtures / name
    content = f'version: 1\nsequences:\n  - protein:\n      id: A\n      sequence: {binder}\n      msa: empty\n'
    content += f'  - ligand:\n      id: B\n      smiles: {ligand}\n' if ligand else f'  - protein:\n      id: B\n      sequence: {seq}\n      msa: {msa}\n'
    path.write_text(content)
    return str(path)

protein = template('protein.yaml', 'A'*65)
scaffold_text = (ROOT / 'Sources/iProteinStudio/Resources/pipeline/examples/nanobody_scaffolds/7xl0_vobarilizumab.yaml').read_text()
scaffold = next(x.strip().split(': ',1)[1] for x in scaffold_text.splitlines() if x.strip().startswith('sequence:'))
nanobody = template('nanobody.yaml', scaffold)
biotin = 'O=C(O)CCCCC1SCC2NC(=O)NC12'
ligand = template('ligand.yaml', 'A'*65, biotin)
cases = [c for c in m['cases'] if c['id'].startswith('predict-')]
def hunter(name, engine, designer='solublempnn', model=None, nano=False, lig=False):
    args = ['--workflow','nanobody' if nano else 'protein','--predictor',engine,'--sequence-designer',designer,'--num-runs','1','--num-opt-cycles','1','--iptm-threshold','0.8','--predictor-samples','1','--post-predictor','none','--post-mode','none']
    if model: args += ['--model',model]
    if not nano: args += ['--random-binder','--binder-min-len','65','--binder-max-len','65','--binder-random-seed','42']
    if not lig: args += ['--require-target-msa']
    cases.append({'id':name,'workflow':'iterative_design','tool':'iterative_design_plan','arguments':{'project':m['project'],'run_name':name,'template_path':nanobody if nano else ligand if lig else protein,'arguments':args},'expected':'successful calibration, cycle00 and cycle01 structures and sequence-design output; hit status is not an acceptance requirement'})

for engine,model in [('boltz',None),('intellifold','v2-flash'),('intellifold','v2'),('protenix-v2',None),('protenix-mini',None),('protenix-constraint-v0.5',None),('openfold-3-mlx',None)]:
    hunter('hunter-'+engine+('-'+model if model else ''),engine,'proteinmpnn' if engine=='protenix-mini' else 'solublempnn',model)
hunter('nanobody-antifold','boltz','antifold',nano=True)
hunter('nanobody-abmpnn','boltz','abmpnn',nano=True)
hunter('hunter-ligandmpnn','boltz','ligandmpnn',lig=True)
for name, request in [
    ('rfd3-protein-flash',dict(target_kind='protein',target_structure=str(fixtures/'sumo.cif'),target_sequence=seq,target_chain='A',target_chains=['A'],binding_site_mode='surface_scan',sequence_model='solublempnn',extra_predictors=['boltz','intellifold','protenix-v2','openfold-3-mlx'],intellifold_model='v2-flash')),
    ('rfd3-protein-full-mini',dict(target_kind='protein',target_structure=str(fixtures/'sumo.cif'),target_sequence=seq,target_chain='A',target_chains=['A'],binding_site_mode='surface_scan',sequence_model='proteinmpnn',extra_predictors=['intellifold','protenix-mini'],intellifold_model='v2')),
    ('rfd3-ligand',dict(target_kind='small_molecule',smiles=biotin,sequence_model='ligandmpnn',extra_predictors=['boltz']))]:
    request.update(lengths=[65],num_backbones=1,sequences_per_backbone=1,top_n=1,batch_size=1,queues_per_bin=1,boltz_calibrate_n=1)
    cases.append({'id':name,'workflow':'rfd3_protein_binder','tool':'rfd3_denovo_plan','arguments':{'project':m['project'],'run_name':name,'request':request},'expected':'one backbone and sequence derivative; complete requested independent verification, including binder-alone for protein; affinity for ligand'})

for name, generator, screen in [('nise-boltz','protein-hunter',None),('nise-nesso','rfdiffusion3','nesso'),('nise-psichic','protein-hunter','psichic')]:
    request = dict(smiles=biotin,num_starts=1,trajectories=1,max_cycles=1,binder_min_len=65,binder_max_len=65,top_x=1,phase0_refine_cycles=1,phase0_seqs1=1,phase0_gate_seqs=1,phase0_seqs2=1,first_cycle_seqs=1,nise_seqs=1,beam=1,backbone_method=generator,rfd3_num_bins=1,early_score_gate=0.0)
    if screen: request.update(scoring_mode='screening',screening_engine=screen,nesso_screen=True,phase0_nesso_screen=True,nesso_top_k=1,phase0_nesso_expand_top_k=1,nesso_early_score_gate=0.0,psichic_early_score_gate=0.0)
    cases.append({'id':name,'workflow':'nise','tool':'nise_plan','arguments':{'project':m['project'],'request':request},'expected':'initialization, LASErMPNN redesign, selected scoring engine and one optimization cycle; zero diagnostic score gates exercise plumbing, never promoted as scientific defaults'})
hunter('nanobody-antifold-template','boltz','antifold',nano=True)
cases[-1]['arguments'].update(target_template_path=str(fixtures/'sumo.cif'),target_template_mode='guide')
cases[-1]['expected'] += '; target-only template guidance exercises the student-like request path'
m.update(cases=cases,matrix_pending=False,status='running',acceptance_scope='Launch/integration acceptance on this Mac, not a scientific-performance or fresh-Mac qualification',fixture_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in fixtures.iterdir()},unsupported=['Protenix Constraint is a guided designer, not an independent Predict/RFD3 verifier','No unsupported engine/workflow combinations requested'],diagnostic_overrides=['One output sample/backbone/trajectory; one redesign cycle','NISE score gates zero only in disposable smoke cases so every scoring branch executes; default diffusion/recycle/precision and guidance retained'])
manifest_path.write_text(json.dumps(m,indent=2)+'\n')
print(json.dumps({'cases':len(cases),'fixtures':str(fixtures)}))
