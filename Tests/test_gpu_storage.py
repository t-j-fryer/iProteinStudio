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
  self.assertIn('retry',failure_message(r));self.assertIn('preserved',failure_message(r))
 def test_success_and_failure_child(self):
  ok=check(command=[sys.executable,'-c','print(\'{"status":"ok"}\')'])
  self.assertIsNone(failure_message(ok))
  r=check(command=[sys.executable,'-c','raise OSError("disk inaccessible")'])
  self.assertEqual(r['status'],'error');self.assertIn('disk inaccessible',r['detail'])
 def test_normal_worker_never_probes_shared_storage(self):
  from iprotein_mcp import broker,common
  with tempfile.TemporaryDirectory() as d, patch.dict(os.environ,{'IPROTEINSTUDIO_AGENT_ROOT':d}):
   jid='job-storage-worker';path=broker.state_path(jid)
   plan={'id':'plan-test','sha256':'test','kind':'prediction','resource_class':'apple_gpu_exclusive','normalized_request':{}}
   common.atomic_json(path,{'id':jid,'pid':os.getpid(),'status':'running'})
   common.atomic_json(path.parent/'plan.json',plan)
   with patch.object(broker,'load_plan',return_value=plan), patch.object(broker.signal,'signal'), patch.object(broker,'_finish_manifest'), patch.object(broker,'_execute_prediction',return_value=0) as execute:
    with patch('iprotein_mcp.gpu_storage.check',side_effect=AssertionError('Normal jobs must not probe')) as check_mock:
     self.assertEqual(broker.run_worker(jid),0)
    check_mock.assert_not_called();execute.assert_called_once()
   self.assertFalse((path.parent/'gpu_storage.json').exists())
 def test_explicit_diagnostic_reports_failure(self):
  import contextlib,io
  from iprotein_mcp.gpu_storage import main
  with patch('iprotein_mcp.gpu_storage.check',return_value={'status':'timeout'}), contextlib.redirect_stdout(io.StringIO()) as output:
   self.assertEqual(main(['--diagnose']),1)
  self.assertEqual(json.loads(output.getvalue())['status'],'timeout')

if __name__=='__main__':unittest.main()
