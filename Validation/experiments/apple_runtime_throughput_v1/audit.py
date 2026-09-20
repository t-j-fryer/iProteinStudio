#!/usr/bin/env python3
"""Final read-only runtime/output audit; write one derived evidence receipt."""
import argparse
import json
from pathlib import Path
from bench_worker import sha, atomic
from coordinator import verify_completed, verify_seal


def main():
    ap=argparse.ArgumentParser();ap.add_argument('output',type=Path);a=ap.parse_args();out=a.output.resolve()
    jobs=[];blocks=[];partial=[]
    for run in sorted(out.glob('*_20*Z')):
        if not (run/'submitted.json').exists():continue
        jid=json.loads((run/'submitted.json').read_text())['id']
        cfg=json.loads((run/'frozen/run.json').read_text());root=Path(cfg['root'])
        state=json.loads((root/'agent/jobs'/jid/'state.json').read_text())
        if state['status'] not in ('completed','failed','cancelled'):raise RuntimeError('Benchmark still active: '+jid)
        jobs.append(dict(id=jid,status=state['status'],error=state.get('error'),path=str(run)))
        plan=json.loads((run/'plan.json').read_text())
        for source in plan['provenance']:
            if sha(source['path'])!=source['sha256']:raise RuntimeError('Plan source changed: '+source['path'])
        for block in cfg['blocks']:
            for attempt in sorted((run/block['id']).glob('attempt_*')):
                if not attempt.is_dir():continue
                if (attempt/'completed.json').exists():
                    verify_completed(attempt,attempt.parent/(attempt.name+'.request.json'))
                    result=json.loads((attempt/'result.json').read_text())
                    blocks.append(dict(path=str(attempt),units=len(result['rows']),receipt_sha256=sha(attempt/'completed.json')))
                else:
                    partial.append(dict(path=str(attempt),measured_units=len(list(attempt.glob('unit_*/measurement.json'))),files={str(p.relative_to(attempt)):sha(p) for p in attempt.rglob('*') if p.is_file()}))
    seals=[]
    for name in ('boltz-torch213','boltz-torch214'):
        path=out/(name+'.seal.json');verify_seal(path);seals.append(dict(path=str(path),sha256=sha(path)))
    first=sorted(out.glob('smoke_20*Z'))[0]
    root=Path(json.loads((first/'frozen/run.json').read_text())['root'])
    helpers={p.name:sha(p)==sha(root/'scripts'/p.name) for p in (first/'frozen/scripts').glob('*.py')}
    if not all(helpers.values()):raise RuntimeError('Installed helper changed since baseline snapshot')
    metadata=list((root/'venvs/NanoHunter_boltz/lib/python3.11/site-packages').glob('torch-*.dist-info/METADATA'))
    versions=[line.split(': ',1)[1] for p in metadata for line in p.read_text().splitlines() if line.startswith('Version: ')]
    if versions!=['2.13.0']:raise RuntimeError('Installed Torch version changed')
    thread_run=next(out.glob('threads_20*Z'))
    interruption=json.loads((thread_run/'interruption.json').read_text())
    preserved=sha(thread_run/'reference/attempt_001/completed.json')==interruption['reference_receipt_sha256']
    jid=json.loads((thread_run/'submitted.json').read_text())['id']
    reused='BENCH_REUSED|reference' in (root/'agent/jobs'/jid/'pipeline.log').read_text()
    if not preserved or not reused:raise RuntimeError('Completed reference was not preserved/reused')
    result=dict(jobs=jobs,completed_blocks=blocks,total_completed_outputs=sum(b['units'] for b in blocks),
                partial_attempts=partial,runtime_seals=seals,installed_helpers_unchanged=helpers,installed_torch_versions=versions,
                interruption=dict(completed_reference_preserved=preserved,completed_reference_reused=reused),
                caveat='Completed output means byte-integrity and cardinality audit, not numerical eligibility. The BF16 comparison failed its declared coordinate margins.')
    atomic(out/'FINAL_AUDIT.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('partial_attempts','completed_blocks','jobs','runtime_seals')},indent=2))


if __name__=='__main__':main()
