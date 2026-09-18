"""Atomic native-writer events: closed outputs, failure, and tamper rejection."""
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType,SimpleNamespace as NS
import unittest
from unittest.mock import patch

SCRIPTS=Path(__file__).resolve().parents[1]/'Sources/iProteinStudio/Resources/pipeline/scripts'
sys.path[:0]=[str(SCRIPTS/'nise'),str(SCRIPTS)]
from batch_runtime import verify_event
from batch_worker import observe_writers, main
from runtime import atomic,digest


class WriterCheckpointTests(unittest.TestCase):
    def test_worker_entrypoint_passes_path_to_shared_service(self):
        with patch('resident_predictor.make_session'),patch('resident_predictor.serve') as serve:
            main('worker.json')
            serve.assert_called_once_with(Path('worker.json'))

    def test_commits_only_closed_native_outputs_and_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'yaml';source.mkdir();(source/'L000.yaml').write_text('input')
            spec={'sequence':'A'};atomic(root/'batch.json',dict(phase='structure',affinity=False,specifications={'L000':spec}))
            leaf=root/'out/boltz_results_yaml/predictions/L000';leaf.mkdir(parents=True)
            class Writer:
                def write_on_batch_end(self,trainer,module,prediction,batch_indices,batch,batch_idx,dataloader_idx):
                    self.called=True
                    if not prediction['exception']:(leaf/'L000_model_0.pdb').write_text('closed output')
            class AffinityWriter(Writer):pass
            modules={name:ModuleType(name) for name in ('boltz','boltz.data','boltz.data.write','boltz.data.write.writer')}
            modules['boltz.data.write.writer'].BoltzWriter=Writer
            modules['boltz.data.write.writer'].BoltzAffinityWriter=AffinityWriter
            original=Writer.write_on_batch_end
            session=NS(request_phase='structure',root=root,model_load_count=1,model=NS(predict_step=lambda *a:None))
            with patch.dict(sys.modules,modules),patch('resident_predictor.validate_geometry'):
                with observe_writers(session,source,root/'out'):
                    session.model.predict_step({'record':[NS(id='L000')]})
                    writer=Writer();writer.write_on_batch_end(None,None,{'exception':False},[],{'record':[NS(id='L000')]},0,0)
                    self.assertTrue(writer.called)
                self.assertIs(Writer.write_on_batch_end,original)
                marker=root/'items/L000.json';event=verify_event(marker,spec)
                self.assertEqual(event['name'],'L000')
                with self.assertRaisesRegex(RuntimeError,'input changed'):verify_event(marker,{'sequence':'G'})
                (leaf/'L000_model_0.pdb').write_text('tampered')
                with self.assertRaisesRegex(RuntimeError,'artifact changed'):verify_event(marker,spec)
                marker.unlink()
                with self.assertRaisesRegex(RuntimeError,'failed to predict'):
                    with observe_writers(session,source,root/'out'):
                        Writer().write_on_batch_end(None,None,{'exception':True},[],{'record':[NS(id='L000')]},0,0)
                self.assertFalse(marker.exists())
                self.assertIs(Writer.write_on_batch_end,original)


if __name__=='__main__':unittest.main()
