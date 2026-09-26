"""Launch acceptance cases only through the shipped, immutable MCP broker."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'Validation/output/portable_workflow_launch_v1'
MANAGED = Path.home() / '.iproteinstudio'
os.environ['NANOHUNTER_ROOT'] = str(MANAGED)
bridge = ROOT / 'Sources/iProteinStudio/Resources/pipeline/mcp' if os.environ.get('STUDIO_ACCEPTANCE_SOURCE_BRIDGE') == '1' else MANAGED / 'mcp'
sys.path.insert(0, str(bridge))
from server import MCPServer
from iprotein_mcp.common import atomic_json, project_root

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['submit', 'status', 'overview'])
    parser.add_argument('cases', nargs='*')
    args = parser.parse_args()
    server = MCPServer('run')
    manifest = json.loads(Path(__file__).with_name('manifest.json').read_text())
    project_root(manifest['project'], create=True)
    for case in manifest['cases']:
        name = case['id']
        if args.cases and name not in args.cases:
            continue
        directory = OUT / name
        directory.mkdir(parents=True, exist_ok=True)
        plan_path = directory / 'plan.json'
        job_path = directory / 'job.json'
        if args.action == 'submit':
            atomic_json(directory / 'guide.json', server.tool_call('workflow_guide', {'workflow':case['workflow']}))
            if plan_path.exists():
                plan = json.loads(plan_path.read_text())
            else:
                if case['tool'] == 'rfd3_denovo_plan':
                    request = case['arguments']['request']
                    inspection = ({'kind':'protein','structure':request['target_structure'],'chains':request['target_chains']}
                                  if request['target_kind']=='protein' else {'kind':'ligand','smiles':request['smiles']})
                    atomic_json(directory / 'target-inspection.json', server.tool_call('target_inspect', inspection))
                plan = server.tool_call(case['tool'], case['arguments'])
                atomic_json(plan_path, plan)
            if job_path.exists():
                job = server.tool_call('job_status', {'job_id':json.loads(job_path.read_text())['id']})
            else:
                job = server.tool_call('job_start', {'plan_id':plan['id'], 'plan_sha256':plan['sha256']})
                atomic_json(job_path, job)
        elif not job_path.exists():
            print(json.dumps({'case':name,'status':'not_submitted'}), flush=True)
            continue
        elif args.action == 'overview':
            runs = server.tool_call('runs_list', {'project':manifest['project']})
            atomic_json(OUT / 'runs.json', runs)
            for run in runs['runs']:
                overview = server.tool_call('results_overview', {'run_id':run['id']})
                atomic_json(OUT / 'overviews' / (run['id'].replace('/','_')+'.json'), overview)
            print(json.dumps({'runs':len(runs['runs'])}), flush=True)
            break
        else:
            job = server.tool_call('job_status', {'job_id':json.loads(job_path.read_text())['id']})
        atomic_json(directory / 'latest-state.json', job)
        print(json.dumps({'case':name, **{k:job.get(k) for k in ('id','status','stage','message','error','output_root')}}), flush=True)

if __name__ == '__main__':
    main()
