import hashlib,io,json,os,sys,tarfile,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Sources/iProteinStudio/Resources/pipeline/scripts'))
from runtime_package import verify,extract
class Tests(unittest.TestCase):
 def test_release_payload_policy_distinguishes_loaders_tables_and_weights(self):
  sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
  from runtime_payload_policy import model_payload,require_weight_free
  self.assertFalse(model_payload('python/lib/python3.12/site-packages/tool.pth'))
  self.assertFalse(model_payload('sources/LASErMPNN/files/new_ideal_coords.pt'))
  for name in ('python/lib/python3.12/site-packages/torchmetrics/functional/image/lpips_models/alex.pth',
               'models/weights.safetensors', 'model.pt', 'checkpoint.ckpt', 'pytorch_model.bin',
               'other/files/new_ideal_coords.pt'):
   self.assertTrue(model_payload(name),name)
   with self.assertRaisesRegex(ValueError,'downloaded separately'):
    require_weight_free({'files':{name:{}}})

 def test_archive_creates_parent_for_link_only_directory(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);archive=root/'good.tar';out=root/'out';out.mkdir()
   with tarfile.open(archive,'w') as tar:
    item=tarfile.TarInfo('source/skills/readme');item.size=2;tar.addfile(item,io.BytesIO(b'ok'))
    link=tarfile.TarInfo('source/.agents/skills');link.type=tarfile.SYMTYPE;link.linkname='../skills';tar.addfile(link)
   extract(archive,out)
   self.assertEqual((out/'source/.agents/skills/readme').read_bytes(),b'ok')
   self.assertEqual(os.readlink(out/'source/.agents/skills'),'../skills')
 def test_tamper_and_external_link(self):
  with tempfile.TemporaryDirectory() as tmp:
   base=Path(tmp);(base/'file').write_bytes(b'original')
   m=dict(schema_version=1,engine='fixture',contains_weights=False,files={'file':dict(size=8,sha256=hashlib.sha256(b'original').hexdigest())})
   (base/'runtime.json').write_text(json.dumps(m));verify(base,engine='fixture')
   (base/'file').write_bytes(b'tampered')
   with self.assertRaises(ValueError):verify(base,engine='fixture')
   (base/'file').unlink();(base/'file').symlink_to('/etc/hosts')
   with self.assertRaises(ValueError):verify(base,engine='fixture')
 def test_activation_retains_source_local_assets_and_rollback(self):
  from runtime_package import activate,digest
  from runtime_transaction import rollback
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp).resolve()/'installed';package=Path(tmp)/'package'
   (package/'python/bin').mkdir(parents=True);executable=package/'python/bin/python3'
   executable.write_text('#!/bin/sh\nexit 0\n');executable.chmod(0o755)
   (package/'sources/Tool').mkdir(parents=True);(package/'sources/Tool/code.py').write_text('qualified')
   source=root/'src/Tool';(source/'models').mkdir(parents=True)
   (source/'code.py').write_text('legacy');(source/'models/model.pt').write_bytes(b'weights')
   inventory={str(p.relative_to(package)):dict(size=p.stat().st_size,sha256=digest(p)) for p in package.rglob('*') if p.is_file()}
   m=dict(schema_version=1,engine='fixture',contains_weights=False,files=inventory,relocation_imports=[],asset_mounts={'sources/Tool/models':'src/Tool/models','python/models':'src/Tool/models'})
   (package/'runtime.json').write_text(json.dumps(m));sha=digest(package/'runtime.json')
   installed=activate(root,'fixture',package,sha,[str(source)+'=sources/Tool'])
   self.assertEqual((source/'code.py').read_text(),'qualified')
   self.assertEqual((source/'models/model.pt').read_bytes(),b'weights')
   verify(installed,sha,'fixture')
   self.assertEqual((source/'models').resolve(),(installed/'python/models').resolve())
   (source/'models/fresh.pt').write_bytes(b'new download')
   self.assertEqual((installed/'python/models/fresh.pt').read_bytes(),b'new download')
   rollback(root,'fixture')
   self.assertEqual((source/'code.py').read_text(),'legacy')
   self.assertEqual((source/'models/model.pt').read_bytes(),b'weights')
   verify(installed,sha,'fixture')
 def test_archive_traversal_and_link_parent(self):
  for name,link in [('../bad',None),('/bad',None),('escape','../../etc'),('dir','/etc')]:
   with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);archive=root/'bad.tar';out=root/'out';out.mkdir()
    with tarfile.open(archive,'w') as t:
     info=tarfile.TarInfo(name)
     if link:info.type=tarfile.SYMTYPE;info.linkname=link;t.addfile(info)
     else:info.size=1;t.addfile(info,io.BytesIO(b'x'))
    with self.assertRaises(ValueError):extract(archive,out)
if __name__=='__main__':unittest.main()
