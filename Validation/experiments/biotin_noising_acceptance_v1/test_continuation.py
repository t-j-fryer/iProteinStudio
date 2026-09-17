import json
from pathlib import Path
import tempfile
import unittest

from continue_after_pilot import check_branch


class AcceptanceGuard(unittest.TestCase):
    def test_requires_passing_complete_repair_and_reduced_parent_pool(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            def put(name, value):
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(json.dumps(value))
            selection = {'trajectories': {'0': {'status': 'selected', 'selected_backbone': {'name': 'mask'},
                                               'advanced': ['repair']}}}
            proposals = {'normal_parent_limit': 2, 'parents': {'0': [{}, {}]}, 'sampled': 6}
            candidate = dict(branch='partial-noising-repair', passed=True, final_eligible=True,
                             sequence='ACDEF', score=1.2, pbind=.5, ligand_plddt=70.,
                             atom_checks={'passed': True, 'exposure': {'O18': {}, 'O19': {}}})
            put('cycle02/partial_noising/selection.json', selection)
            put('cycle02/proposal_round.json', proposals)
            put('candidates/repair.json', candidate)
            self.assertEqual(check_branch(root), ['repair'])
            for patch in ({'passed': False}, {'final_eligible': False}, {'sequence': 'AXDEF'},
                          {'score': float('nan')}, {'branch': 'mpnn'},
                          {'atom_checks': {'passed': True, 'exposure': {'O19': {}}}}):
                put('candidates/repair.json', {**candidate, **patch})
                with self.assertRaises(RuntimeError):
                    check_branch(root)
            put('candidates/repair.json', candidate)
            put('cycle02/proposal_round.json', {**proposals, 'parents': {'0': [{}, {}, {}]}, 'sampled': 9})
            with self.assertRaises(RuntimeError):
                check_branch(root)
            put('cycle02/proposal_round.json', proposals)
            selection['trajectories']['0']['advanced'] = []
            put('cycle02/partial_noising/selection.json', selection)
            with self.assertRaises(RuntimeError):
                check_branch(root)


if __name__ == '__main__':
    unittest.main()
