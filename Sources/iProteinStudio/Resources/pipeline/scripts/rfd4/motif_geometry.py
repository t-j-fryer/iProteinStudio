"""CPU geometry operations in the pinned native runtime, not predictor environments."""
import json
import os
from pathlib import Path
import subprocess
from .contract import atomic, fixed, seal, sha, verify


def operation(root, folder, source, mode, **options):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    request=folder/'request.json';result=folder/'result.json';done=folder/'completed.json'
    fixed(request,dict(source=str(source),source_sha256=sha(source),mode=mode,**options))
    if done.exists():
        report=verify(done)
    else:
        venv=Path(root)/'venvs/NanoHunter_rfd4'
        env=dict(os.environ,VIRTUAL_ENV=str(venv),PATH=str(venv/'bin')+os.pathsep+os.environ.get('PATH',''),PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1')
        subprocess.run([str(venv/'bin/python'),'-B',str(Path(__file__).resolve().parents[1]/'rfd4_cli.py'),
                        'motif-geometry','--root',str(root),'--config',str(request),'--output',str(result)],env=env,check=True)
        report=json.loads(result.read_text())
        if report['source_sha256']!=sha(source):raise ValueError('Motif geometry source changed during assessment.')
        seal(done,report,[request,result,source])
    return report['value'],[request,result,done]


def execute(request, output):
    from .motif_metrics import insertion_map,score
    source=request['source']
    if sha(source)!=request['source_sha256']:raise ValueError('Motif geometry input changed.')
    if request['mode']=='map':value=insertion_map(source,request['reference'])
    elif request['mode']=='score':value=score(source,request['mapped'],request['context'],fix_sequence=request['fix_sequence'],holo=request['holo'])
    else:raise ValueError('Unknown motif geometry operation.')
    atomic(output,dict(value=value,source_sha256=sha(source)))
