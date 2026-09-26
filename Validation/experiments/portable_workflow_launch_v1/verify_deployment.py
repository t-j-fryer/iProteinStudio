"""Check installed app resources, staged MCP, and the normal runtime installer."""
import hashlib, json, os, plistlib, subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
managed=Path.home()/'.iproteinstudio'
out=ROOT/'Validation/output/portable_workflow_launch_v1'
app=ROOT/'build/iProteinStudio.app'
bundle=app/'Contents/Resources/iProteinStudioResources'
info=plistlib.loads((app/'Contents/Info.plist').read_bytes())
assert info['CFBundleShortVersionString']=='0.2.8' and info['CFBundleVersion']=='54'
files=['nanohunter_run.sh','setup_pipeline.sh','PIPELINE_VERSION',
       'scripts/openfold_query_json.py','scripts/runtime_releases.json','scripts/setup_portable.py',
       'mcp/MCP_VERSION','mcp/iprotein_mcp/__init__.py',
       'mcp/iprotein_mcp/plans.py','mcp/iprotein_mcp/broker.py','mcp/schemas/rfd3-v1.json']
digests={}
for name in files:
    data=(bundle/'pipeline'/name).read_bytes()
    assert data==(managed/name).read_bytes(), name
    digests[name]=hashlib.sha256(data).hexdigest()
assert (bundle/'rfd3/prepare_campaign.py').read_bytes()==(managed/'rfd3_scripts/prepare_campaign.py').read_bytes()
for name in ('OVERLAY_VERSION','milestone0_oracle.py','scripts/generate_backbones.py'):
    assert (bundle/'rfd3_overlay'/name).read_bytes()==(managed/'rfd3_overlay'/name).read_bytes(), name
env={**os.environ,'NANOHUNTER_ROOT':str(managed),'PYTHONDONTWRITEBYTECODE':'1'}
doctor=json.loads(subprocess.check_output([str(managed/'components/control/current/python/bin/python3'),'-B',str(managed/'mcp/studioctl.py'),'doctor'],env=env,text=True))
assert doctor['ok'] and doctor['bridge_version']=='29'
job=json.loads((out/'engine-install-job.json').read_text())
state=json.loads((managed/'agent/jobs'/job['id']/'state.json').read_text())
assert state['status']=='completed', state.get('message')
runtime_digest=hashlib.sha256((managed/'components/rfd3/current/runtime.json').read_bytes()).hexdigest()
assert runtime_digest=='c9fc19327d6b15b5a14b83b3d99c914e1dc52d2b2d1eb9e87b6cf0be49d27a3a'
constraint=json.loads((managed/'models/protenix_constraint/install_receipt.json').read_text())
assert constraint['zero_substructure']=='checkpoint-equivalent-single-token-broadcast'
receipt={'version':'0.2.8','build':54,'managed_mcp':doctor,'packaged_and_staged_sha256':digests,'engine_install_job':job['id'],'runtime_manifest_sha256':runtime_digest,'constraint_receipt_contract':constraint['zero_substructure']}
(out/'DEPLOYMENT_VERIFIED.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt,indent=2))
