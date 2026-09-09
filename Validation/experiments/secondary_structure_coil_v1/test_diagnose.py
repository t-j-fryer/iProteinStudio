"""Behavior checks for exploratory localization, not scientific validation."""
import importlib.util
from pathlib import Path
import unittest
import numpy as np

spec = importlib.util.spec_from_file_location('coil_diagnose', Path(__file__).with_name('diagnose.py'))
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)


def plan(n, masked=()):
    return {'positions':[{'index':i, 'region':'turn' if i%3==0 else 'strand'} for i in range(1,n+1)], 'x_positions':list(masked)}


class CoilDiagnosisTests(unittest.TestCase):
    def test_segments_include_termini_and_split_at_noncoil(self):
        self.assertEqual(list(d.contiguous_segments('ccabbcccac')), [(0,2),(5,8),(9,10)])
        self.assertEqual(list(d.contiguous_segments('aaaa')), [])
        self.assertEqual(list(d.contiguous_segments('cccc')), [(0,4)])

    def test_bin_boundaries(self):
        self.assertEqual([d.length_bin(n) for n in (1,3,4,7,8,15,16,90)], ['1-3','1-3','4-7','4-7','8-15','8-15','16+','16+'])
        self.assertEqual([d.confidence_bin(x) for x in (49.99,50,69.99,70)], ['below50','50to70','50to70','70plus'])

    def test_visible_confidence_gate_does_not_penalize_x_alone(self):
        n=32; mask=range(1,n+1,2)
        confidence=np.array([10 if i in mask else 90 for i in range(1,n+1)])
        _,segments,metrics=d.summarize_structure('c'*n,confidence,plan(n,mask))
        self.assertEqual(segments[0]['visible_mean_plddt'],90)
        self.assertEqual(segments[0]['masked_mean_plddt'],10)
        self.assertEqual(metrics['max_coil_length_visible_mean_below60'],0)
        self.assertFalse(d.gates_for_row(metrics)['coil_ge24_visiblemean_below60'])

    def test_visible_gate_requires_four_visible_residues(self):
        _,_,metrics=d.summarize_structure('c'*32,np.full(32,30),plan(32,range(1,30)))
        self.assertEqual(metrics['max_coil_length_visible_mean_below50'],0)

    def test_segment_mean_not_contiguous_individual_low_confidence(self):
        # One confident residue splits an individually low-confidence run, but
        # does not split the structural coil segment.
        confidence=np.full(32,30.0); confidence[15]=90
        _,_,metrics=d.summarize_structure('c'*32,confidence,plan(32,range(2,33,2)))
        self.assertEqual(metrics['max_contiguous_coil_below50'],16)
        self.assertEqual(metrics['max_coil_length_visible_mean_below50'],32)

    def test_partition_fractions_sum_to_coil_fraction(self):
        codes='cccaaacccccbbbbcccccc'
        _,_,metrics=d.summarize_structure(codes,np.linspace(30,90,len(codes)),plan(len(codes),range(1,len(codes)+1,2)))
        for keys in ([f'coil_length_{b}_fraction' for b in d.LENGTH_BINS], [f'coil_confidence_{b}_fraction' for b in d.CONFIDENCE_BINS], ['coil_terminal_fraction','coil_internal_fraction'], ['coil_at_planned_turn_fraction_all_residues','coil_at_planned_strand_fraction_all_residues']):
            self.assertAlmostEqual(sum(metrics[k] for k in keys),metrics['coil_fraction'])

    def test_equal_trajectory_weight_not_cycle_count(self):
        rows=[dict(arm='beta',run='1',cycle=1,value=0),dict(arm='beta',run='1',cycle=2,value=10),dict(arm='beta',run='2',cycle=1,value=20)]
        means=d.trajectory_means(rows)
        self.assertEqual([r['value'] for r in means],[5,20])

    def test_nonfinite_confidence_fails(self):
        with self.assertRaisesRegex(ValueError,'invalid confidence'):
            d.summarize_structure('ac',np.array([float('nan'),70]),plan(2,[1]))


if __name__=='__main__':
    unittest.main()
