"""Pool ownership, membership, cancellation, callback serialization and policy guards."""
import json
from pathlib import Path
import sys,tempfile,threading,time,unittest
from unittest.mock import patch
from types import SimpleNamespace as NS
SCRIPTS=Path(__file__).resolve().parents[1]/'Sources/iProteinStudio/Resources/pipeline/scripts'
sys.path[:0]=[str(SCRIPTS/'nise'),str(SCRIPTS)]
from batch_runtime import PoolBackend,partition_inputs
from runtime import atomic,digest
from continuation import validate

class PoolTests(unittest.TestCase):
    def test_partition_covers_ragged_inputs_once_and_is_order_independent(self):
        for n in (0,1,3,24):
            entries={str(i):{'sequence':'A'*(65+i*3)} for i in range(n)}
            a=partition_inputs(entries,2);b=partition_inputs(dict(reversed(list(entries.items()))),2)
            self.assertEqual(a,b)
            self.assertEqual(sorted(k for group in a for k in group),sorted(entries))
            self.assertTrue(all(a))

    def exercise(self, fail=False):
        live=[];seen=[];barrier=threading.Barrier(2);inside=0
        class Client:
            def __init__(self,*a,**k):self.closed=False;live.append(self)
            def close(self):self.closed=True
        class Backend(PoolBackend):
            def _execute_batch(self,d,p,a,phase,affinity,commit,apo,client):
                barrier.wait(timeout=2)
                if fail and client is live[0]:raise RuntimeError('worker failed')
                if fail:
                    end=time.monotonic()+3
                    while not client.closed and time.monotonic()<end:time.sleep(.01)
                    if not client.closed:raise AssertionError('Sibling was not stopped')
                    return
                for name in p:commit(name)
        with tempfile.TemporaryDirectory() as td,patch('batch_runtime.BatchClient',Client),patch.dict(sys.modules,{'nise_lib':NS()}):
            b=Backend(td,td,{'scheduler':'resident'},SCRIPTS)
            def commit(name):
                nonlocal inside
                inside+=1;self.assertEqual(inside,1);time.sleep(.01);seen.append(name);inside-=1
            args=NS(seed=0,use_potentials=True)
            entries={str(i):{'sequence':'A'*i} for i in range(1,5)}
            try:
                if fail:
                    with self.assertRaisesRegex(RuntimeError,'worker failed'):b._execute(Path(td),entries,args,'structure',False,commit)
                    self.assertTrue(all(c.closed for c in live))
                else:
                    b._execute(Path(td),entries,args,'structure',False,commit)
                    b._execute(Path(td),entries,args,'affinity',True,commit)
                    self.assertEqual(len(live),2);self.assertEqual(len(seen),8)
            finally:b.close()
            self.assertTrue(all(c.closed for c in live))
    def test_two_live_workers_reused_across_phases_serialized_commits(self):self.exercise()
    def test_failure_stops_sibling_before_join(self):self.exercise(True)
    def test_invalid_pool_size(self):
        with self.assertRaises(ValueError):PoolBackend('.', '.', {}, SCRIPTS, workers=4)
    def test_continuation_rejects_modified_receipt_and_execution_policy(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);atomic(root/'nise_config.json',{})
            code=root/'new/scripts/nise';code.mkdir(parents=True);(code/'batch_runtime.py').write_text('snapshot')
            atomic(root/'sampling.json',{'input':{},'files':{},'result':['AAA']})
            d={'schema':2,'submission':'stage-directory','base_config_sha256':digest(root/'nise_config.json'),
               'pipeline_snapshot':'new','checkpoints':{'sampling.json':digest(root/'sampling.json')},
               'execution':{'resident_workers':2,'rng_policy':'per-input-v1','cpu_threads':4}}
            atomic(root/'nise_continuation.json',d);validate(root)
            d['execution']['resident_workers']=4;atomic(root/'nise_continuation.json',d)
            with self.assertRaisesRegex(ValueError,'execution'):validate(root)
            d['execution']['resident_workers']=2;atomic(root/'nise_continuation.json',d)
            (root/'sampling.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'checkpoint'):validate(root)
if __name__=='__main__':unittest.main()
