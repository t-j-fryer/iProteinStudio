"""CPU contract tests; actual sampling equivalence is the managed benchmark."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import benchmark

class Contract(unittest.TestCase):
    def execute(self, text, error=False):
        with tempfile.TemporaryDirectory() as tmp:
            original=lambda *a,**k: None
            upstream=SimpleNamespace(load_model_from_parameter_dict=original)
            def run(**kwargs):
                upstream.load_model_from_parameter_dict('weights','cpu')
                if error:raise RuntimeError('upstream failed')
                p=Path(tmp)/'unit';p.mkdir();(p/'designs.fasta').write_text(text)
            upstream.run_inference=run
            upstream.parse_args=lambda _: {}
            benchmark.MODEL=(upstream,object(),{},0.25)
            seed_calls=[]
            fake_numpy=SimpleNamespace(random=SimpleNamespace(seed=lambda x:seed_calls.append(('numpy',x))))
            fake_torch=SimpleNamespace(manual_seed=lambda x:seed_calls.append(('torch',x)))
            argv=sys.argv
            with patch.dict(sys.modules,{'numpy':fake_numpy,'torch':fake_torch}):
                try:
                    row=benchmark.task(dict(output=str(Path(tmp)/'unit'),input='fixture.pdb',
                        count=1,seed=123,weights='weights',key='test'))
                    self.assertEqual(seed_calls,[('numpy',123),('torch',123)])
                    self.assertEqual(row['count'],1)
                    self.assertEqual(json.loads((Path(tmp)/'unit/receipt.json').read_text()),row)
                finally:
                    self.assertIs(sys.argv,argv)
                    self.assertIs(upstream.load_model_from_parameter_dict,original)

    def test_valid_output_and_rng_reset(self):self.execute('>fixture score=-0.3\nACDEFG\n')
    def test_wrong_count_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'Invalid sampler output'):self.execute('>a\nAAA\n>b\nAAA\n')
    def test_incomplete_sequence_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'Invalid sampler output'):self.execute('>a\nAAX\n')
    def test_loader_restored_after_upstream_failure(self):
        with self.assertRaisesRegex(RuntimeError,'upstream failed'):self.execute('',True)

if __name__=='__main__':unittest.main()
