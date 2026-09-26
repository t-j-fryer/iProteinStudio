"""Portable installer contracts: no compiler route and honest platform minimums."""
import importlib.util,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];SCRIPTS=ROOT/'Sources/iProteinStudio/Resources/pipeline/scripts';sys.path.insert(0,str(SCRIPTS))
import runtime_package,setup_portable
class Tests(unittest.TestCase):
 def test_constraint_portable_receipt_matches_launch_and_detection_contract(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp).resolve();base=root/'components/protenix_constraint/current';base.mkdir(parents=True)
   (base/'runtime.json').write_text(json.dumps({'engine':'protenix_constraint'}))
   source=root/'src/ProtenixConstraint';model=root/'models/protenix_constraint';venv=root/'venvs/constraint'
   for name in ('checkpoint/protenix_base_constraint_v0.5.0.pt','common/components.cif','common/components.cif.rdkit_mol.pkl'):
    path=model/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('fixture')
   embed=source/'protenix/model/modules/embedders.py';embed.parent.mkdir(parents=True);embed.write_text('verified package fixture')
   patches=root/'patches';patches.mkdir()
   for name in ('protenix_constraint_mps.patch','protenix_constraint_zero_substructure.patch'):(patches/name).write_text(name)
   (venv/'bin').mkdir(parents=True);(venv/'bin/python').symlink_to(sys.executable)
   (venv/'bin/protenix').write_text('#!/bin/sh\nexit 0\n');(venv/'bin/protenix').chmod(0o755)
   with patch.object(setup_portable,'from_catalog',return_value=base),patch.object(setup_portable,'download'):
    setup_portable.install(root,'protenix_constraint')
   receipt=model/'install_receipt.json';data=json.loads(receipt.read_text())
   self.assertEqual(data['zero_substructure'],'checkpoint-equivalent-single-token-broadcast')
   shell=(SCRIPTS.parent/'setup_pipeline.sh').read_text();function=shell.split('constraint_runtime_current() {',1)[1].split('\n}\n',1)[0]
   env={**os.environ,'PROTENIX_CONSTRAINT_VENV':str(venv),'PROTENIX_CONSTRAINT_REPO':str(source),'PROTENIX_CONSTRAINT_MODEL_DIR':str(model),'PROTENIX_CONSTRAINT_PATCH':str(patches/'protenix_constraint_mps.patch'),'PROTENIX_CONSTRAINT_ZERO_SUBSTRUCTURE_PATCH':str(patches/'protenix_constraint_zero_substructure.patch')}
   command=['/bin/bash','-c','constraint_runtime_current() {'+function+'\n}\nconstraint_runtime_current']
   self.assertEqual(subprocess.run(command,env=env).returncode,0)
   del data['zero_substructure'];receipt.write_text(json.dumps(data))
   self.assertNotEqual(subprocess.run(command,env=env).returncode,0)
 def test_platform_rejection_happens_before_download(self):
  catalog=dict(packages={'fixture':dict(minimum_macos='26.2',url='https://github.com/example/runtime',archive_sha256='0'*64)})
  with patch.object(Path,'read_text',return_value=json.dumps(catalog)),patch.object(runtime_package.platform,'machine',return_value='arm64'),patch.object(runtime_package.platform,'mac_ver',return_value=('26.0',(),'')),patch.object(runtime_package.subprocess,'run') as runner:
   with self.assertRaisesRegex(ValueError,'26.2 or newer'):runtime_package.from_catalog(Path('/unused'),'fixture')
   runner.assert_not_called()
 def test_dependency_selection_and_partial_failure(self):
  with tempfile.TemporaryDirectory() as tmp:
   calls=[]
   def install(root,key,local):
    calls.append(key)
    if key=='boltz':raise ValueError('fixture failure')
   with patch.object(sys,'argv',['setup_portable','--root',tmp,'--components','boltz_affinity,mpnn']),patch.object(setup_portable,'install',side_effect=install):
    self.assertEqual(setup_portable.main(),2)
   self.assertEqual(calls,['boltz','mpnn'])
 def test_asset_catalog_and_source_build_opt_in(self):
  for key,items in setup_portable.ASSETS.items():
   for item in items:
    self.assertEqual(len(item['sha256']),64);self.assertTrue(item['url'].startswith('https://'));self.assertNotIn('..',Path(item['path']).parts)
  source=(SCRIPTS.parent/'setup_pipeline.sh').read_text()
  self.assertLess(source.index('scripts/setup_portable.py'),source.index('if ! configure_apple_build_tools'))
  self.assertIn('IPROTEINSTUDIO_BUILD_FROM_SOURCE:-0',source)
if __name__=='__main__':unittest.main()
