"""Synthetic count fixtures only; these are not measured natural distributions."""
import unittest
from reference_bins import summarize


def row(**updates):
    value=dict(reference_id='synthetic_fixture',cluster_id='fixture_cluster',origin='natural',
               source='synthetic unit-test fixture only',assignment_method='PSEA',assignment_version='test',
               fold_class='example_class',support_class='none_declared',length=100,
               helix_residues=20,sheet_residues=30,coil_residues=50,unassigned_residues=0)
    value.update(updates)
    return value


class ReferenceBinsTests(unittest.TestCase):
    def test_joint_bin_boundaries_and_no_threshold(self):
        result=summarize([row()])
        self.assertEqual(result['strata'][0]['bins'][0]['lower_percent'],dict(helix=20,sheet=30,coil=50))
        self.assertIsNone(result['acceptance_thresholds'])

    def test_full_fraction_stays_inside_last_bin(self):
        result=summarize([row(helix_residues=100,sheet_residues=0,coil_residues=0)])
        self.assertEqual(result['strata'][0]['bins'][0]['lower_percent']['helix'],90)

    def test_missing_residues_are_reported_not_coil(self):
        result=summarize([row(coil_residues=40,unassigned_residues=10)])
        self.assertEqual(result['complete_proteins'],0)
        self.assertEqual(result['excluded'][0]['unassigned_residues'],10)

    def test_redundancy_and_mixed_assignment_versions_fail(self):
        with self.assertRaises(ValueError):summarize([row(),row()])
        with self.assertRaises(ValueError):summarize([row(),row(cluster_id='second',assignment_version='different')])

    def test_empty_and_invalid_counts_fail(self):
        with self.assertRaises(ValueError):summarize([])
        with self.assertRaises(ValueError):summarize([row(coil_residues=51)])

    def test_support_strata_remain_separate(self):
        result=summarize([row(),row(cluster_id='second',support_class='cofactor')])
        self.assertEqual(len(result['strata']),2)


if __name__=='__main__':unittest.main()
