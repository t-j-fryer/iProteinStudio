"""CPU-only structure and saved-output audit; does not load neural models."""
import csv
import hashlib
import json
from pathlib import Path
import re
import sys
import numpy as np
import yaml
from biotite.sequence import ProteinSequence
from biotite.structure.io import pdb, pdbx

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = ROOT / 'Validation/output/portable_workflow_launch_v1'
MANAGED = Path.home() / '.iproteinstudio'
m = json.loads((HERE / 'manifest.json').read_text())

def structure(path):
    if path.suffix == '.pdb': atoms = pdb.PDBFile.read(path).get_structure(model=1)
    else: atoms = pdbx.get_structure(pdbx.CIFFile.read(path), model=1)
    assert len(atoms) and np.isfinite(atoms.coord).all(), 'empty/nonfinite coordinates'
    chains = {}
    for chain in dict.fromkeys(atoms.chain_id):
        ca = atoms[(atoms.chain_id==chain) & (atoms.atom_name=='CA') & ~atoms.hetero]
        if not len(ca): continue
        letters=[]
        for name in ca.res_name:
            if name == 'UNK':
                letters.append('X'); continue
            try: letters.append(ProteinSequence.convert_letter_3to1(str(name)))
            except KeyError: letters.append('X')
        chains[str(chain)] = ''.join(letters)
    assert chains, 'no protein C-alpha atoms'
    return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'atoms':len(atoms),'sequences':chains}

rows=[]
for case in m['cases']:
    directory=OUT/case['id']; jobfile=directory/'job.json'
    if not jobfile.exists(): continue
    job=json.loads(jobfile.read_text()); state=json.loads((MANAGED/'agent/jobs'/job['id']/'state.json').read_text())
    if state['status']!='completed':
        rows.append({'case':case['id'],'job_status':state['status'],'passed':False,'pending':state['status'] in ('queued','running')}); continue
    root=Path(state['output_root']); errors=[]; records=[]
    paths=[p for p in root.rglob('*') if p.suffix in ('.cif','.pdb') and not any(part.startswith('.') for part in p.relative_to(root).parts)]
    if case['tool']=='prediction_plan':
        paths=[p for p in paths if '/predictions/' in str(p) or '/output/' in str(p)]
        if len(paths)!=1: errors.append(f'Expected one predicted structure, found {len(paths)}')
    elif case['tool']=='iterative_design_plan':
        paths=sorted((root/'cifs_all').glob('*.cif'))
        if len(paths)!=2: errors.append(f'Expected cycle00 and cycle01, found {len(paths)}')
        for cycle in ('cycle_00','cycle_01'):
            if not any(cycle in p.name for p in paths): errors.append(f'Missing {cycle}')
    elif case['tool']=='rfd3_denovo_plan':
        backbones=list((root/'rfd3/backbones').glob('*.pdb'))
        if len(backbones)!=1: errors.append(f'Expected one RFD3 backbone, found {len(backbones)}')
        if not (root/'mpnn/sequences.csv').exists(): errors.append('Missing RFD3 sequence-design table')
        request=case['arguments']['request']
        engines=set(request.get('extra_predictors',[]))
        if request['target_kind']=='small_molecule': engines.add('boltz')
        for context in ('holo','monomer' if request['target_kind']=='protein' else 'apo'):
            table=root/'predictions'/context/'prediction_metrics.csv'
            if not table.exists():
                errors.append(f'Missing {context} verification table'); continue
            metrics=list(csv.DictReader(table.open()))
            expected=engines if request['target_kind']=='protein' or context=='holo' else {'boltz'}
            if {row.get('predictor') for row in metrics}!=expected: errors.append(f'{context}: requested verifier coverage differs')
            for row in metrics:
                succeeded = row.get('exit_code') == '0' if 'exit_code' in row else str(row.get('ok','')).lower() in ('true','1')
                if not succeeded: errors.append(f'{context}: failed verification row')
                artifact=Path(row.get('structure') or row.get('pdb',''))
                if not artifact.is_file(): errors.append(f'Missing verification artifact: {artifact}')
                else:
                    try:
                        chains=structure(artifact)['sequences']
                        if 'sequence' in row: expected_sequence=row['sequence']
                        else:
                            inputs=yaml.safe_load(Path(row['input_yaml']).read_text())
                            expected_sequence=next(entity['protein']['sequence'] for entity in inputs['sequences'] if entity.get('protein',{}).get('id')=='A')
                        assert chains['A']==expected_sequence, 'verification binder sequence mismatch'
                        if context=='holo' and request['target_kind']=='protein': assert chains['B']==m['fixture']['sequence'], 'verification target sequence mismatch'
                    except Exception as e: errors.append(f'{context}: {e}')
                if context=='holo' and request['target_kind']=='small_molecule' and row.get('predictor')=='boltz':
                    try: assert np.isfinite(float(row['pbind']))
                    except Exception: errors.append('Missing/nonfinite Boltz affinity result')
    elif case['tool']=='nise_plan':
        if not (root/'trajectory.csv').exists(): errors.append('Missing NISE optimization trajectory table')
    for path in paths:
        try:
            record=structure(path); records.append(record)
            if case['tool']=='prediction_plan':
                assert list(record['sequences'].values())==[m['fixture']['sequence']], 'prediction sequence differs from requested SUMO'
            if case['tool']=='iterative_design_plan':
                sequences=record['sequences']
                expected_length=121 if case['id'].startswith('nanobody-') else 65
                assert len(sequences['A'])==expected_length, 'binder length differs'
                if case['id']!='hunter-ligandmpnn': assert sequences['B']==m['fixture']['sequence'], 'target sequence differs'
                cycle=re.search(r'cycle_\d+',path.name).group()
                inputs=list((root/'run_001'/cycle).glob('run_001_cycle_*.yaml'))
                if not inputs and (root/'run_001'/cycle/'boltz_input.yaml').is_file(): inputs=[root/'run_001'/cycle/'boltz_input.yaml']
                assert len(inputs)==1, 'missing/ambiguous cycle input'
                requested=yaml.safe_load(inputs[0].read_text())
                for entity in requested['sequences']:
                    if 'protein' not in entity: continue
                    chain=entity['protein']; actual=sequences[chain['id']]; expected=chain['sequence']
                    assert len(actual)==len(expected) and all(x==y or x=='X' for x,y in zip(expected,actual)), 'saved cycle structure does not match its requested sequence'
        except Exception as e: errors.append(str(path)+': '+str(e))
    if not records: errors.append('No audited structures')
    confidences=[p for p in root.rglob('*.json') if 'confidence' in p.name and not any(part.startswith('.') for part in p.relative_to(root).parts)]
    for path in confidences:
        try:
            payload=json.loads(path.read_text()); json.dumps(payload,allow_nan=False)
        except Exception as e: errors.append(str(path)+': nonfinite/invalid confidence JSON '+str(e))
    if not confidences and case['tool']!='rfd3_denovo_plan': errors.append('No saved confidence JSON')
    log=(MANAGED/'agent/jobs'/job['id']/'pipeline.log').read_text()
    fallback_lines=[line for line in log.splitlines() if re.search(r'fall.?back.*CPU|not.*supported.*MPS',line,re.I)]
    geometry=[]
    for path in root.rglob('geometry_report.json'):
        if any(part.startswith('.') for part in path.relative_to(root).parts): continue
        report=json.loads(path.read_text())
        geometry.append({'path':str(path.relative_to(root)), **{key:report.get(key) for key in ('policy','violation_count','error_count','coordinate_input_usable')}})
    rows.append({'case':case['id'],'job_id':job['id'],'job_status':state['status'],'passed':not errors,'errors':errors,'structures':records,'confidence_json_count':len(confidences),'geometry_reports':geometry,'fallback_lines':fallback_lines,'progress_messages':log.count('IPROTEINSTUDIO_PROGRESS|'),'output_root':str(root)})
(OUT/'output-audit.json').write_text(json.dumps(rows,indent=2)+'\n')
for row in rows: print(json.dumps({k:row[k] for k in ('case','job_status','passed','errors') if k in row}))
