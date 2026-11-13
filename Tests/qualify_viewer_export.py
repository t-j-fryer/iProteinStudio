"""Optional isolated graphics check of the actual portable MCP style export."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[1]
PIPELINE=ROOT/'Sources/iProteinStudio/Resources/pipeline'
sys.path.insert(0,str(PIPELINE/'mcp'))
from iprotein_mcp import common,exports,review

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--chimerax',required=True);parser.add_argument('--out',required=True);args=parser.parse_args()
    output=Path(args.out).resolve();output.mkdir(parents=True,exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='studio-portable-viewer-') as tmp:
        root=Path(tmp);run=root/'projects/fixture/rfd4_runs/test';run.mkdir(parents=True)
        source=run/'test.pdb';source.write_bytes((ROOT/'Sources/iProteinStudio/Resources/examples/t4_lysozyme/target.pdb').read_bytes())
        (run/'rfd4_config.json').write_text('{}')
        record=dict(candidate_id='a'*64,run_id='fixture/rfd4_runs/test',group_id='synthetic',variant_id='fixture',artifacts=[dict(path='test.pdb',path_sha256=common.file_digest(source))])
        with patch.dict(os.environ,{'NANOHUNTER_ROOT':str(root),'IPROTEINSTUDIO_AGENT_ROOT':str(root/'agent')}),patch.object(exports,'_index',return_value=[record]):
            result=review.viewer_script_export(record['run_id'],record['candidate_id'],common.canonical_digest([record]))
            with zipfile.ZipFile(result['local_path']) as archive:archive.extractall(output)
        script=output/'manuscript_style.py';body=script.read_text();audit=output/'audit.json';image=output/'render.png'
        script.write_text(body+f'''\nassert len(models) == 1
assert models[0].num_atoms > 100
assert models[0].residues.ribbon_displays.any()
Path({str(audit)!r}).write_text(json.dumps(dict(passed=True,source_sha256=cfg['sha256'],model_count=len(models),portable_template_sha256={hashlib.sha256(body.encode()).hexdigest()!r})))
run(session, 'save ' + StringArg.unparse({str(image)!r}) + ' width 800 height 600 supersample 1')
''')
        with (output/'chimerax.log').open('w') as log:
            subprocess.run([args.chimerax,'--debug','--notools','--nostatus','--exit',str(script)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=60,env={**os.environ,'CHIMERAX_START':str(root/'empty-startup')})
        if not audit.exists() or not json.loads(audit.read_text())['passed'] or not image.exists():raise RuntimeError('Portable style export failed graphics acceptance.')
        if common.file_digest(output/'structure.pdb')!=record['artifacts'][0]['path_sha256']:raise RuntimeError('Coordinates changed.')
        manifest=dict(schema=1,passed=True,scope='Shipped T4 lysozyme; isolated ChimeraX process; no user workspace or inference',export_sha256=result['export_sha256'],source_sha256=record['artifacts'][0]['path_sha256'],template_sha256=common.file_digest(PIPELINE/'mcp/templates/chimerax_manuscript_v1.py.txt'),render_sha256=common.file_digest(image))
        (output/'qualification.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('PASS portable sibling-file style export in isolated ChimeraX')
if __name__=='__main__':main()
