"""Native CPU chemistry/template parsing; no model inference or weights loaded."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from test_motif_beta import fixture, geometry, templates
from motif_beta import contract, designers, source_guide


class NativeInputs(unittest.TestCase):
    def setUp(self):
        self.cache = Path(os.environ.get('NANOHUNTER_ROOT', Path.home() / '.iproteinstudio')) / 'models/boltz2/mols'
        if not (self.cache / 'ADP.pkl').is_file():
            self.skipTest('Requires an installed Boltz CCD cache; no downloads performed.')
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)

    def test_boltz_parser_has_coordinates_only_at_mapped_query_positions(self):
        from motif_beta.boltz_templates import parse_mmcif
        pdb, ref, _ = fixture(self.base)
        sequence = geometry.evaluate(ref, pdb, 90)['sequence']
        templates.prepare(ref, sequence, 'boltz', self.base / 'template')
        parsed = parse_mmcif(str(self.base / 'template/motif.cif'), mols={}, moldir=str(self.cache),
                             use_assembly=False, compute_interfaces=False)
        self.assertEqual(parsed.sequences['A'], sequence)
        self.assertEqual([i + 1 for i, r in enumerate(parsed.data.residues) if r['is_present']], [2, 5, 8])

    def test_multiligand_protonation_keeps_heavy_atoms_and_motif_beta_masks(self):
        import gemmi
        pdb, ref, _ = fixture(self.base, 'M0040_13pk')
        result = designers.prepare(ref, pdb, self.cache, self.base / 'designers')
        self.assertEqual(result['lasermpnn_args'], ['--fix_beta'])
        self.assertEqual(len(result['input']['chemistry']), 3)
        st = gemmi.read_structure(str(self.base / 'designers/lasermpnn.pdb'))
        fixed = set(json.loads(ref.read_text())['identities'])
        for residue in st[0]['A']:
            self.assertEqual({a.b_iso for a in residue}, {1 if f'A:{residue.seqid.num}:' in fixed else 0})
        self.assertEqual(designers.prepare(ref, pdb, self.cache, self.base / 'designers'), result)

    def test_original_multichain_residues_parse_without_rfd3(self):
        from motif_beta.boltz_templates import parse_mmcif
        c = contract.case('M0050_1dbt')
        self.assertGreater(len({r['chain'] for r in c['protein_motif']}), 1)
        mapping = {r['source_selector']: 2 + i * 4 for i, r in enumerate(reversed(c['protein_motif']))}
        sequence = list('A' * 50)
        for r in c['protein_motif']: sequence[mapping[r['source_selector']] - 1] = geometry.LETTERS[r['component']]
        sequence = ''.join(sequence)
        ref = self.base / 'source.json'
        source_guide.prepare(c['case_id'], mapping, sequence, ref)
        templates.prepare(ref, sequence, 'boltz', self.base / 'template')
        parsed = parse_mmcif(str(self.base / 'template/motif.cif'), mols={}, moldir=str(self.cache),
                             use_assembly=False, compute_interfaces=False)
        self.assertEqual(parsed.sequences['A'], sequence)
        self.assertEqual([i + 1 for i, r in enumerate(parsed.data.residues) if r['is_present']], sorted(mapping.values()))

    def test_repeated_sequence_uses_explicit_mapping_in_native_yaml(self):
        from boltz.data.parse import schema, mmcif
        from motif_beta.boltz_templates import install
        c = contract.case('M0024_1nzy')
        mapping = {r['source_selector']: 2 + 4 * i for i, r in enumerate(c['protein_motif'])}
        sequence = list('A' * 50)
        for r in c['protein_motif']: sequence[mapping[r['source_selector']] - 1] = geometry.LETTERS[r['component']]
        sequence = ''.join(sequence)
        ref = self.base / 'source.json'
        source_guide.prepare(c['case_id'], mapping, sequence, ref)
        receipt = templates.prepare(ref, sequence, 'boltz', self.base / 'template')
        # This real native-parser ambiguity motivated the positional adapter.
        raw = mmcif.parse_mmcif(str(self.base / 'template/motif.cif'), mols={}, moldir=str(self.cache),
                                use_assembly=False, compute_interfaces=False)
        self.assertNotEqual([i + 1 for i, r in enumerate(raw.data.residues) if r['is_present']], sorted(mapping.values()))
        original = schema.parse_mmcif
        self.addCleanup(setattr, schema, 'parse_mmcif', original)
        install(); install()
        document = dict(version=1, sequences=[dict(protein=dict(id='A', sequence=sequence, msa='empty'))], **receipt['fragment'])
        target = schema.parse_boltz_schema('motif', document, {}, self.cache, boltz_2=True)
        parsed = target.templates['motif']
        self.assertEqual([i + 1 for i, r in enumerate(parsed.residues) if r['is_present']], sorted(mapping.values()))
        self.assertEqual(len(target.record.templates), 1)
        self.assertEqual(target.record.templates[0].query_st, 0)
        self.assertEqual(target.record.templates[0].query_en, len(sequence))

    def test_partial_ccd_is_rejected_not_silently_completed(self):
        report = designers.chemistry_audit(contract.case('M0054_1qfe'), self.cache)
        self.assertFalse(report['ready'])
        self.assertIn("CCD-only=['N']", report['blockers'][0]['error'])
        self.assertTrue(designers.chemistry_audit(contract.case('M0040_13pk'), self.cache)['ready'])


if __name__ == '__main__': unittest.main()
