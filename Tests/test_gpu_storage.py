import json,os,sys,tempfile,time,unittest
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Sources/iProteinStudio/Resources/pipeline/mcp'))
from iprotein_mcp.gpu_storage import probe,check,failure_message

class GPUStorageTests(unittest.TestCase):
 def test_preserves_existing_contents(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'other-app').mkdir();(p/'other-app/data').write_bytes(b'keep')
   before=sorted(str(x.relative_to(p)) for x in p.rglob('*'))
   self.assertEqual(probe(p)['status'],'ok')
   self.assertEqual(before,sorted(str(x.relative_to(p)) for x in p.rglob('*')))
   self.assertEqual((p/'other-app/data').read_bytes(),b'keep')
 def test_missing_directory_is_not_created(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'absent';self.assertEqual(probe(p)['status'],'not_created');self.assertFalse(p.exists())
 def test_symlink_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'real').mkdir();(p/'link').symlink_to(p/'real')
   with self.assertRaises(RuntimeError):probe(p/'link')
 def test_stalled_child_is_bounded_and_actionable(self):
  start=time.monotonic();r=check(.1,command=[sys.executable,'-c','import time; time.sleep(60)'])
  self.assertEqual(r['status'],'timeout');self.assertLess(time.monotonic()-start,3)
  self.assertIn('resume',failure_message(r));self.assertIn('preserved',failure_message(r))
 def test_success_and_failure_child(self):
  ok=check(command=[sys.executable,'-c','print(\'{"status":"ok"}\')'])
  self.assertIsNone(failure_message(ok))
  r=check(command=[sys.executable,'-c','raise OSError("disk inaccessible")'])
  self.assertEqual(r['status'],'error');self.assertIn('disk inaccessible',r['detail'])
 def test_broker_records_failure_before_dispatch(self):
  from iprotein_mcp import broker
  from iprotein_mcp.common import StudioError
  with tempfile.TemporaryDirectory() as d, patch.dict(os.environ,{'IPROTEINSTUDIO_AGENT_ROOT':d}):
   with patch('iprotein_mcp.gpu_storage.check',return_value={'status':'timeout','probe_pid':123}):
    with self.assertRaisesRegex(StudioError,'Restart your Mac'):
     broker._gpu_storage_preflight('job-storage-test')
   recorded=json.loads((Path(d)/'jobs/job-storage-test/gpu_storage.json').read_text())
   self.assertEqual(recorded['status'],'timeout')
 def test_worker_blocks_dispatch_then_can_retry(self):
  from iprotein_mcp import broker,common
  with tempfile.TemporaryDirectory() as d, patch.dict(os.environ,{'IPROTEINSTUDIO_AGENT_ROOT':d}):
   jid='job-storage-worker';path=broker.state_path(jid)
   plan={'id':'plan-test','sha256':'test','kind':'prediction','resource_class':'apple_gpu_exclusive','normalized_request':{}}
   common.atomic_json(path,{'id':jid,'pid':os.getpid(),'status':'running'})
   common.atomic_json(path.parent/'plan.json',plan)
   with patch.object(broker,'load_plan',return_value=plan), patch.object(broker.signal,'signal'), patch.object(broker,'_finish_manifest'), patch.object(broker,'_execute_prediction',return_value=0) as execute:
    with patch('iprotein_mcp.gpu_storage.check',return_value={'status':'timeout'}):
     self.assertEqual(broker.run_worker(jid),1)
    execute.assert_not_called()
    self.assertEqual(common.load_json(path)['status'],'failed')
    with patch('iprotein_mcp.gpu_storage.check',return_value={'status':'ok'}):
     self.assertEqual(broker.run_worker(jid),0)
    execute.assert_called_once()
    self.assertEqual(common.load_json(path)['status'],'completed')

if __name__=='__main__':unittest.main()
