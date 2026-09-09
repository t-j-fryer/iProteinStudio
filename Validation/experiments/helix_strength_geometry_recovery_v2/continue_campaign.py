#!/usr/bin/env python3
"""Retain verified geometry rejections and continue independent monomer conditions."""
import argparse
import fcntl
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'Validation/experiments/helix_strength_source_recovery_v1'))
import recover as source_recovery
c=source_recovery.c
RECOVERY=c.OUTPUT/'recovery_geometry_v2'


# Explicitly reviewed deployment changes: NISE entry points/display only. These
# files are not invoked by the frozen unconditioned-monomer plans. Every other
# original file/hash remains required; no future drift is accepted implicitly.
NISE_ONLY = {'mcp/README.md', 'mcp/iprotein_mcp/catalog.py',
             'scripts/nise/campaign.py', 'scripts/nise/contract.py',
             'scripts/nise/nise_run.py', 'scripts/nise/runtime.py'}


def verify_stage(full_hashes=False):
    baseline=c.read(c.OUTPUT/'stage_receipt.json')
    amendment=c.read(RECOVERY/'non_monomer_deployment.json')
    c.require(amendment['manifest_sha256']==c.sha(c.OUTPUT/'manifest.json'),'Amendment belongs to a different study')
    accepted=amendment['accepted_files']
    c.require(set(accepted)==NISE_ONLY,'Unreviewed deployment scope')
    for name,record in baseline['files'].items():
        c.require(c.sha(c.SOURCE/name)==record['after_sha256'],f'Original source reference changed: {name}')
        expected=accepted[name]['sha256'] if name in accepted else record['after_sha256']
        c.require(c.sha(c.RUNTIME/name)==expected,f'Runtime provenance changed: {name}')
    for name,record in {**baseline['engine_files'],**baseline['engine_code']}.items():
        expected=accepted.get(name,record)
        path=c.RUNTIME/name;stat=path.stat()
        c.require(stat.st_size==expected['bytes'] and stat.st_mtime_ns==expected['mtime_ns'],f'Engine file changed: {name}')
        if full_hashes:c.require(c.sha(path)==expected['sha256'],f'Engine checksum changed: {name}')
    return baseline


c.verify_stage=verify_stage


def review(result,audit):
    if result['operational_passed']:
        return []
    phase,arm=result['phase'],result['arm']
    c.require(phase=='remaining','A failed pilot cannot authorize cohort expansion')
    c.require(all(t['outcome'] in ('completed','failed') for t in result['trajectories']), 'Unstarted trajectories require separate diagnosis')
    plan=c.read(c.OUTPUT/'plans'/phase/(arm+'.json'))
    state=c.read(c.OUTPUT/'status'/phase/(arm+'.json'))
    c.require(state['status']=='failed','Only a terminal failed cohort can be reviewed')
    root=Path(plan['normalized_request']['campaign'])
    validator=root/'.studio_runtime/pipeline/scripts/validate_prediction_geometry.py'
    expected=c.read(c.OUTPUT/'stage_receipt.json')['engine_code']['scripts/validate_prediction_geometry.py']['sha256']
    c.require(c.sha(validator)==expected,'Frozen geometry validator changed')
    spec=importlib.util.spec_from_file_location('frozen_geometry_review',validator)
    geometry=importlib.util.module_from_spec(spec);spec.loader.exec_module(geometry)
    records=[]
    import yaml
    for row in result['trajectories']:
        if row['outcome']=='completed':continue
        local=row['trajectory']-1
        run=root/f'run_{local:03d}'
        c.require((run/'run_exit_code.txt').read_text().strip()!='0','Failure receipt disagrees with run exit')
        accepted=[r['cycle'] for r in result['structures'] if r['trajectory']==row['trajectory']]
        cycle=max(accepted)+1 if accepted else 0
        c.require(accepted==list(range(cycle)),'Preceding accepted cycles are not contiguous')
        directory=run/f'cycle_{cycle:02d}'
        raw=audit.native_structures(directory,c.CONFIG['arms'][arm]['predictor'])
        c.require(len(raw)==1,'Rejected prediction cardinality is not one')
        issues=geometry.validate(raw[0])
        c.require(bool(issues) and all(' C-N=' in issue and '(>2.2)' in issue for issue in issues),
                  f'Failure is not an independently reproduced peptide-bond rejection: {issues}')
        logs=list(directory.rglob('predict.log'))
        content='\n'.join(p.read_text(errors='replace') for p in logs)
        c.require('Predictor returned invalid protein geometry' in content and all(issue in content for issue in issues),
                  'Prediction log does not attribute failure to the reproduced geometry defect')
        sequences=[]
        for p in directory.glob('*.yaml'):
            document=yaml.safe_load(p.read_text())
            if not isinstance(document,dict):continue
            for entity in document.get('sequences',[]):
                protein=entity.get('protein',{})
                if protein.get('id')=='A':sequences.append(protein['sequence'])
        c.require(bool(sequences) and len(set(sequences))==1 and len(sequences[0])==90,'Rejected input sequence is not unambiguous')
        assessment=audit.evaluate(raw[0],sequences[0])
        records.append({'trajectory':row['trajectory'],'cycle':cycle,'outcome':'retained_geometry_rejection',
                        'eligible':False,'structure':str(raw[0].relative_to(c.OUTPUT)),
                        'structure_sha256':c.sha(raw[0]),'input_sequence':sequences[0],
                        'geometry_diagnostics':issues,'finite_ca_confidence_checked':len(assessment['per_residue_confidence'])==90,
                        'logs':{str(p.relative_to(c.OUTPUT)):c.sha(p) for p in logs}})
    c.require(bool(records),'Failed cohort has no classified failures')
    value={'phase':phase,'arm':arm,'original_audit_sha256':c.sha(c.OUTPUT/'audits'/phase/(arm+'.json')),
           'validator_sha256':expected,'records':records,'progression':'continue other independent conditions; no retry or replacement',
           'original_operational_passed':False,'controller_sha256':c.sha(__file__)}
    path=RECOVERY/'reviews'/phase/(arm+'.json')
    if path.exists():c.require(c.read(path)==value,'Recorded failure review changed')
    else:c.atomic(path,value)
    return [r['trajectory'] for r in records]


def run():
    audit=source_recovery.configure()
    with (c.OUTPUT/'controller.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        c.verify_stage(full_hashes=True)
        for phase in ('pilot','remaining'):
            for arm in c.CONFIG['arms']:
                saved=c.OUTPUT/'audits'/phase/(arm+'.json')
                if saved.exists() or (phase=='pilot' and arm in c.CONFIG.get('reused_pilots',{})):
                    result=audit.audit(phase,arm)
                    failures=review(result,audit)
                    c.emit({'phase':phase,'arm':arm,'status':'audit_reverified',
                            'completed':sum(r['outcome']=='completed' for r in result['trajectories']),
                            'retained_failed_trajectories':failures})
                    continue
                plan=c.ensure_plan(phase,arm)
                state=c.ctl('start',plan['id'],plan['sha256'])
                c.atomic(c.OUTPUT/'jobs'/phase/(arm+'.json'),{'id':state['id'],'plan_id':plan['id']})
                c.emit({'phase':phase,'arm':arm,**c.compact(state)})
                while state['status'] not in c.TERMINAL:
                    time.sleep(15);state=c.ctl('job-status',state['id'])
                    c.atomic(c.OUTPUT/'status'/phase/(arm+'.json'),state)
                c.atomic(c.OUTPUT/'status'/phase/(arm+'.json'),state)
                c.emit({'phase':phase,'arm':arm,**c.compact(state)})
                result=audit.audit(phase,arm)
                failures=review(result,audit)
                c.emit({'phase':phase,'arm':arm,'operational_passed':result['operational_passed'],
                        'retained_failed_trajectories':failures,'progression':'continue independent conditions'})
        c.verify_stage(full_hashes=True);audit.report()
        sys.path.insert(0,str(ROOT/'Validation/experiments/helix_strength_analysis_v1'))
        import finish
        result=finish.finish();c.atomic(c.OUTPUT/'analysis_status.json',result);c.emit(result)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['review','run']);args=p.parse_args()
    try:
        if args.action=='run':run()
        else:
            audit=source_recovery.configure();result=audit.audit('remaining','boltz_h0')
            c.emit({'retained_failed_trajectories':review(result,audit),'operational_passed':result['operational_passed']})
    except Exception as error:
        result={'complete':False,'status':'blocked','error':str(error),'time':c.now()}
        c.atomic(c.OUTPUT/'analysis_status.json',result);c.emit(result);raise
