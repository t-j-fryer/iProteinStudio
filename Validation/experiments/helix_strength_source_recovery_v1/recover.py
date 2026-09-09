#!/usr/bin/env python3
"""Continue the unchanged helix study with a receipt-verified source reference."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import sys
import time

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'Validation/experiments/helix_strength_all_engines_v2'))
import campaign as c
RECOVERY=c.OUTPUT/'recovery_source_v1'
REFERENCE=RECOVERY/'source'


def configure():
    receipt=c.read(c.OUTPUT/'stage_receipt.json')
    record=RECOVERY/'receipt.json'
    if not record.exists():
        RECOVERY.mkdir(parents=True,exist_ok=True)
        drift={}
        for name,expected in receipt['files'].items():
            live=c.RUNTIME/name
            c.require(c.sha(live)==expected['after_sha256'],f'Runtime differs from the declared study: {name}')
            current=c.sha(c.SOURCE/name)
            if current!=expected['after_sha256']:
                drift[name]={'working_tree_sha256':current,'declared_sha256':expected['after_sha256']}
            target=REFERENCE/name;target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists():c.require(c.sha(target)==expected['after_sha256'],'Unexpected existing reference')
            else:shutil.copy2(live,target)
        c.atomic(record,{'created_at':c.now(),'original_manifest_sha256':c.sha(c.OUTPUT/'manifest.json'),
                         'recovery_code_sha256':c.sha(__file__),'working_tree_drift':drift,
                         'source_reference':str(REFERENCE),'files':{n:v['after_sha256'] for n,v in receipt['files'].items()},
                         'policy':'Source reference is the exact original runtime bytes. Runtime, engine, checkpoint, plan and original experiment checks stay enabled. No live files or completed predictions are edited.'})
    saved=c.read(record)
    c.require(saved['recovery_code_sha256']==c.sha(__file__),'Recovery controller changed')
    c.require(saved['original_manifest_sha256']==c.sha(c.OUTPUT/'manifest.json'),'Study manifest changed')
    for name,checksum in saved['files'].items():c.require(c.sha(REFERENCE/name)==checksum,'Source reference changed')
    c.SOURCE=REFERENCE
    c.prepare()
    import audit
    return audit


def run():
    audit=configure()
    with (c.OUTPUT/'controller.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        c.verify_stage(full_hashes=True)
        for phase in ('pilot','remaining'):
            for arm in c.CONFIG['arms']:
                if (c.OUTPUT/'audits'/phase/(arm+'.json')).exists() or (phase=='pilot' and arm in c.CONFIG.get('reused_pilots',{})):
                    result=audit.audit(phase,arm)
                    c.require(result['operational_passed'],f'Existing audit gate failed: {phase}/{arm}')
                    c.emit({'phase':phase,'arm':arm,'status':'audit_reverified','completed':len(result['trajectories'])})
                    continue
                plan=c.ensure_plan(phase,arm)
                state=c.ctl('start',plan['id'],plan['sha256'])
                c.atomic(c.OUTPUT/'jobs'/phase/(arm+'.json'),{'id':state['id'],'plan_id':plan['id']})
                c.emit({'phase':phase,'arm':arm,**c.compact(state)})
                while state['status'] not in c.TERMINAL:
                    time.sleep(15)
                    state=c.ctl('job-status',state['id'])
                    c.atomic(c.OUTPUT/'status'/phase/(arm+'.json'),state)
                c.atomic(c.OUTPUT/'status'/phase/(arm+'.json'),state)
                c.emit({'phase':phase,'arm':arm,**c.compact(state)})
                result=audit.audit(phase,arm)
                c.require(result['operational_passed'],f'Output audit gate failed: {phase}/{arm}')
                c.emit({'phase':phase,'arm':arm,'operational_passed':True})
        c.verify_stage(full_hashes=True)
        audit.report()
        sys.path.insert(0,str(ROOT/'Validation/experiments/helix_strength_analysis_v1'))
        import finish
        result=finish.finish()
        c.atomic(c.OUTPUT/'analysis_status.json',result)
        c.emit(result)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['verify','audit-pending','run']);args=p.parse_args()
    try:
        if args.action=='run':run()
        else:
            audit=configure()
            if args.action=='verify':
                c.verify_stage(full_hashes=True);c.emit({'verified':True,'receipt':str(RECOVERY/'receipt.json')})
            else:
                result=audit.audit('pilot','openfold3_h0p5')
                c.require(result['operational_passed'],'Pending OpenFold output failed its audit')
                c.emit({'operational_passed':True,'arm':'openfold3_h0p5','trajectories':len(result['trajectories'])})
    except Exception as error:
        result={'complete':False,'status':'blocked','error':str(error),'time':c.now()}
        c.atomic(c.OUTPUT/'analysis_status.json',result);c.emit(result);raise
