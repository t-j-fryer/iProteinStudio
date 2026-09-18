"""Observer insertion must preserve computation and reject changed samplers."""
import sys
from pathlib import Path
from types import SimpleNamespace, MethodType
import unittest
import random

SCRIPTS = Path(__file__).resolve().parents[1] / "Sources/iProteinStudio/Resources/pipeline/scripts"
sys.path.insert(0, str(SCRIPTS))
from boltz_diffusion_observer import instrument_source

SOURCE = '''def sample(self):
    atom_coords = 0.0
    for step_idx, sigma_t in enumerate([3., 2., 1., 0.]):
        atom_coords_denoised = atom_coords + random.random()
        atom_coords_next = atom_coords_denoised / (sigma_t + 1)
        atom_coords = atom_coords_next
    return atom_coords
'''


class ObserverTests(unittest.TestCase):
    def test_insertion_preserves_computation_and_random_stream(self):
        recorded = []
        model = SimpleNamespace(_studio_observe=lambda *x: recorded.append(x))
        baseline, observed = dict(random=random), dict(random=random)
        exec(SOURCE, baseline)
        exec(instrument_source(SOURCE), observed)
        random.seed(29); expected = baseline['sample'](model); expected_next = random.random()
        random.seed(29); actual = observed['sample'](model); actual_next = random.random()
        self.assertEqual(actual, expected)
        self.assertEqual(actual_next, expected_next)
        self.assertEqual([x[0] for x in recorded], [1, 2, 3, 4])
        self.assertEqual(recorded[-1][2], actual)

    def test_rejects_different_step_boundary(self):
        for source in (SOURCE.replace('atom_coords = atom_coords_next', 'atom_coords += atom_coords_next'),
                       SOURCE.replace('step_idx', 'different_index')):
            with self.assertRaises(ValueError):
                instrument_source(source)


if __name__ == '__main__':
    unittest.main()
