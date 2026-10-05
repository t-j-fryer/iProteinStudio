"""Execute all supported patch migrations and their selection semantics."""
import importlib.util
from pathlib import Path
import textwrap
import unittest

import numpy as np

PATH = Path(__file__).resolve().parents[1] / 'Sources/iProteinStudio/Resources/rfd3_overlay/scripts/patch_foundry_rasa.py'
spec = importlib.util.spec_from_file_location('rasa_patch', PATH)
patcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patcher)


class RasaPatchTests(unittest.TestCase):
    def test_fresh_previous_and_idempotent_patch(self):
        for source in (patcher.old, patcher.previous, patcher.new):
            self.assertEqual(patcher.patch_source(source), patcher.new)

    def test_unknown_source_fails_closed(self):
        with self.assertRaises(ValueError):
            patcher.patch_source('unknown upstream revision')

    def test_rasa_preserved_but_fixed_mask_and_sequence_respect_selections(self):
        class Atoms:
            def __init__(self, values):
                self.values = np.array(values)

            def get_annotation_categories(self):
                return ['rasa_bin', 'is_motif_atom_with_fixed_coord', 'is_motif_atom_with_fixed_seq']

            def get_annotation(self, name):
                return self.values

        # Execute the actual inserted code, including the fixed-default reset.
        for annotation, initial, selected, default, expected in (
            ('rasa_bin', [0, 3, 3], 2, 3, [0, 2, 3]),
            ('is_motif_atom_with_fixed_coord', [1, 1, 1], 1, 0, [0, 1, 0]),
            ('is_motif_atom_with_fixed_seq', [0, 0, 0], 0, 1, [1, 0, 1]),
        ):
            aa = Atoms(initial)
            env = dict(np=np, aa=aa, annotation_name=annotation, start=0, end=3,
                       mask=np.array([False, True, False]), set_value=selected, default_value=default)
            exec(textwrap.dedent(patcher.new), env)
            np.testing.assert_array_equal(aa.values, expected)


if __name__ == '__main__':
    unittest.main()
