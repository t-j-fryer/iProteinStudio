"""Portable installer contracts: no compiler route and honest platform minimums."""
import importlib.util,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];SCRIPTS=ROOT/'Sources/iProteinStudio/Resources/pipeline/scripts';sys.path.insert(0,str(SCRIPTS))
import runtime_package,setup_portable
class Tests(unittest.TestCase):
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
