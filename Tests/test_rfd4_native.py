"""Native upstream beam/oracle boundary, without loading model weights."""
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Sources/iProteinStudio/Resources/pipeline/scripts'))
from rfd4.contract import atomic, seal, normalize, prediction_budget
from rfd4.native import strategy, policies


class OracleTests(unittest.TestCase):
    def test_budget_terminal_checkpoint_and_separate_policies(self):
        cfg = normalize(dict(task='ligand', source='source.cif', native_search=True, ligand_smiles='CCC', predictor='boltz'))
        self.assertEqual(prediction_budget(cfg), 10)
        cfg['native_checkpoints'] = [8, 30]
        self.assertEqual(prediction_budget(cfg), 8)
        self.assertEqual(policies([8], False)['8']['rewards'], {'protein.ipsae_min': {'weight':1.0}})
        with self.assertRaises(ValueError): normalize(dict(cfg, native_checkpoints=[31]))

    @patch.dict(os.environ, DEBUG="false")  # Match the adapter's upstream import environment.
    def test_upstream_generation_and_oracle_cache_contract(self):
        import numpy as np
        import biotite.structure as bs
        from rfproteina.search.beam_search import BeamSearchStrategy
        from rfproteina.rewards.reward_model import RewardModel
        array = bs.AtomArray(3)
        array.chain_id[:] = 'A'; array.res_id[:] = [1,2,3]
        array.res_name[:] = 'ALA'; array.atom_name[:] = 'CA'; array.element[:] = 'C'
        array.coord[:] = np.array([[0,0,0],[3.8,0,0],[7.6,0,0]])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            class Scorer:
                calls = 0
                def run(self, key, structures):
                    self.calls += 1
                    evidence = root / 'prediction.txt'; evidence.write_text('oracle fixture')
                    receipt = root / 'oracle/completed.json'
                    seal(receipt, dict(fixture=True), [evidence])
                    return {name: dict(score=1.5, metrics={'boltz.pbind':.7,'boltz.ligand_plddt':80}, receipts=[str(receipt)]) for name in structures}
            scorer = Scorer()
            cfg = dict(checkpoints=[8,15], beam_width=2, n_branch=2, settings={'task':'ligand'}, output=str(root))
            adapter = strategy(cfg, scorer, root / 'family')
            self.assertIs(type(adapter).generate, BeamSearchStrategy.generate)
            self.assertIs(type(adapter)._simulate_and_compute_reward, BeamSearchStrategy._simulate_and_compute_reward)
            reward = RewardModel(policies([8], True)['8']['rewards'])
            inputs = [dict(example_id='rollout_0',generated_atom_array=array)]
            args = dict(metric_names=['boltz'],design_ids=['rollout_0'])
            with patch('torch.mps.synchronize'):
                values, _ = adapter._compute_rewards(SimpleNamespace(device='cpu'), inputs, reward, **args)
                self.assertAlmostEqual(values.item(), 1.5)
                adapter._compute_rewards(SimpleNamespace(device='cpu'), inputs, reward, **args)
                self.assertEqual(scorer.calls, 1)
                array.res_name[0] = 'GLY'
                with self.assertRaisesRegex(RuntimeError, 'sequences'):
                    adapter._compute_rewards(SimpleNamespace(device='cpu'), inputs, reward, **args)


if __name__ == '__main__': unittest.main()
