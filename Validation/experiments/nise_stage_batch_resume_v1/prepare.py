"""Prepare a bounded smoke or immutable same-output campaign continuation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import uuid

REPO=Path(__file__).resolve().parents[3]
PIPELINE=REPO/'Sources/iProteinStudio/Resources/pipeline'
sys.path[:0]=[str(PIPELINE/'mcp'),str(PIPELINE/'scripts/nise')]
from server import MCPServer
from iprotein_mcp.desktop import desktop_plan
from runtime import Journal,atomic,digest


def main():
    p=argparse.ArgumentParser();p.add_argument('--source-job',required=True);p.add_argument('--mode',choices=['smoke','continue'],required=True)
    p.add_argument('--records',type=Path,required=True);args=p.parse_args()
    state=MCPServer('run').tool_call('job_status',{'job_id':args.source_job})
    if state['status'] not in ('cancelled','failed'):raise ValueError('Source must be stopped')
    original=Path(state['output_root']);config=json.loads((original/'nise_config.json').read_text())
    checkpoints={}
    for receipt in sorted((original/'phase0/cycle00').rglob('completed.json')):
        data=json.loads(receipt.read_text());Journal(original).load(receipt,data['input'])
        checkpoints[str(receipt.relative_to(original))]=digest(receipt)
    if not checkpoints:raise ValueError('No original initial checkpoints')
    if args.mode=='smoke':
        out=original.parent.parent/'validation_runs'/('nise-batch-smoke-'+uuid.uuid4().hex[:12]);out.mkdir(parents=True)
        snapshot=out/'.studio_runtime/pipeline'
        selected=list(checkpoints)[:2];files={};ids=[]
        for relative in selected:
            receipt=original/relative;name=receipt.parent.name;ids.append(name)
            target=out/'batch_test_inputs'/name/'completed.json';target.parent.mkdir(parents=True)
            shutil.copy2(receipt,target);files[str(target.relative_to(out))]=digest(target)
        request=dict(config['request'],num_starts=len(ids),trajectories=len(ids))
        atomic(out/'nise_config.json',dict(output=str(out),request=request,batch_test=dict(schema=1,ids=ids,files=files)))
        atomic(out/'studio_run_label.json',{'name':'NISE stage batching — interruption and affinity smoke'})
        workflow='nise_batch_test'
    else:
        out=original;snapshot=out/'.studio_runtime/stage-directory-v1/pipeline'
        if snapshot.exists() or (out/'nise_continuation.json').exists():raise ValueError('Continuation already prepared; use its saved plan')
        for name in ('nise_run.py','nise_lib.py','search_policy.py','atom_geometry.py','ligand_atoms.py','contract.py'):
            if digest(out/'.studio_runtime/pipeline/scripts/nise'/name)!=digest(PIPELINE/'scripts/nise'/name):
                raise ValueError('Scientific code changed; cannot silently continue: '+name)
        workflow='nise_continuation'
    shutil.copytree(PIPELINE/'scripts',snapshot/'scripts',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    if args.mode=='continue':
        atomic(out/'nise_continuation.json',dict(schema=1,submission='stage-directory',source_job=args.source_job,
            base_plan_id=state['plan_id'],base_config_sha256=digest(out/'nise_config.json'),
            pipeline_snapshot=str(snapshot.relative_to(out)),checkpoints=checkpoints,
            note='Original science/config/checkpoints preserved; one pending input directory per stage; no early killing.'))
    plan=desktop_plan(dict(project=state['project'],workflow=workflow,output=str(out)))
    args.records.mkdir(parents=True,exist_ok=True);atomic(args.records/'plan.json',plan)
    atomic(args.records/'source_status.json',state)
    print(json.dumps(dict(plan_id=plan['id'],sha256=plan['sha256'],output=str(out),completed_original=len(checkpoints))))


if __name__=='__main__':main()
