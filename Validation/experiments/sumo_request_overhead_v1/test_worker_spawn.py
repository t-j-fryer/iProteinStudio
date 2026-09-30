"""A spawned data-loader child must import the harness without launching it."""
import multiprocessing as mp
from pathlib import Path
import runpy
import unittest

def import_worker(queue):
    runpy.run_path(str(Path(__file__).with_name('worker.py')), run_name='__mp_main__')
    queue.put('imported without prediction or filesystem mutations')

class WorkerSpawn(unittest.TestCase):
    def test_spawn_import_has_no_prediction_side_effects(self):
        context=mp.get_context('spawn');queue=context.Queue()
        process=context.Process(target=import_worker,args=(queue,));process.start();process.join(15)
        if process.is_alive():process.terminate();process.join();self.fail('Harness import hung')
        self.assertEqual(process.exitcode,0)
        self.assertEqual(queue.get(timeout=2),'imported without prediction or filesystem mutations')
        queue.close();queue.join_thread()

if __name__=='__main__':unittest.main()
