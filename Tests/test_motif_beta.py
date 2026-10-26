"""Execute atom-level beta contracts with released inputs and synthetic outputs."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'Sources/iProteinStudio/Resources/pipeline/scripts'
sys.path.insert(0, str(SCRIPTS))
from motif_beta import contract, geometry, templates, search, source_guide
import gemmi
import numpy as np


def fixture(base, identifier='M0054_1qfe'):
    bundle = base / 'bundle'
    contract.prepare(bundle, dict(case_id=identifier, length=50))
    c = contract.case(identifier)
    conditioning = json.loads((bundle / 'bundle.json').read_text())['conditioning_ligands']
    st = gemmi.Structure(); model = gemmi.Model('1'); chain = gemmi.Chain('A')
    by_pos = {2 + i * 3: r for i, r in enumerate(c['protein_motif'])}
    mapping = {}
    for pos in range(1, 51):
        source = by_pos.get(pos)
        res = gemmi.Residue(); res.seqid = gemmi.SeqId(pos, ' ')
        res.name = source['component'] if source else 'ALA'
        atoms = source['atoms'] if source else {
            a: dict(element=e, xyz_angstrom=[float(pos * 3 + dx), float(pos % 3), float(pos % 7)])
            for a, e, dx in [('N', 'N', 0), ('CA', 'C', 1), ('C', 'C', 2), ('O', 'O', 2.5), ('CB', 'C', 1.5)]}
        for name, item in atoms.items():
            atom = gemmi.Atom(); atom.name = name; atom.element = gemmi.Element(item['element'])
            atom.pos = gemmi.Position(*item['xyz_angstrom']); atom.occ = 1; atom.b_iso = 90
            res.add_atom(atom)
        chain.add_residue(res)
        if source: mapping[source['source_selector']] = 'A' + str(pos)
    model.add_chain(chain)
    ligand_map = []
    for i, source in enumerate(c['ligands']):
        cid = chr(66 + i); chain = gemmi.Chain(cid)
        res = gemmi.Residue(); res.seqid = gemmi.SeqId(1, ' '); res.name = source['component']; res.het_flag = 'H'
        for name, item in source['atoms'].items():
            atom = gemmi.Atom(); atom.name = name; atom.element = gemmi.Element(item['element'])
            atom.pos = gemmi.Position(*item['xyz_angstrom']); atom.occ = 1; atom.b_iso = 90
            res.add_atom(atom)
        chain.add_residue(res); model.add_chain(chain)
        ligand_map.append(dict(source_chain=conditioning[i]['conditioning_chain'], source_residue=conditioning[i]['conditioning_residue'],
                               component=source['component'], output_chain=cid, output_residue=1))
    st.add_model(model); pdb = base / 'root.pdb'; st.write_pdb(str(pdb))
    metadata = dict(diffused_index_map=mapping, ligand_instance_map=ligand_map,
                    motif_fixed_atoms={r['source_selector']: r['conditioning_atoms'] for r in c['protein_motif']})
    ref = base / 'root.json'
    geometry.freeze_root(bundle, pdb, metadata, ref)
    return pdb, ref, metadata


class MotifBetaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)

    def test_all_41_exact_inputs_and_replay(self):
        for case in contract.catalog()['cases']:
            path = self.base / case['case_id']
            cfg = dict(case_id=case['case_id'])
            saved = contract.prepare(path, cfg)
            self.assertEqual(saved, contract.prepare(path, cfg))
            spec = json.loads((path / 'rfd3.yaml').read_text())
            self.assertEqual(set(spec['unindex'].split(',')), {r['source_selector'] for r in case['protein_motif']})
            self.assertNotIn('ORI', (path / 'conditioning.pdb').read_text())
            conditioned = geometry.read(path / 'conditioning.pdb')
            protein_chains = {r['chain'] for r in case['protein_motif']}
            for mapping, ligand in zip(saved['conditioning_ligands'], case['ligands']):
                self.assertNotIn(mapping['conditioning_chain'], protein_chains)
                key = f"{mapping['conditioning_chain']}:{mapping['conditioning_residue']}:"
                self.assertEqual(set(conditioned[key]['atoms']), set(geometry.heavy(ligand)))
                for name in geometry.heavy(ligand):
                    np.testing.assert_allclose(conditioned[key]['atoms'][name]['xyz'], ligand['atoms'][name]['xyz_angstrom'])
            self.assertEqual(len(spec['select_fixed_atoms']), len(case['protein_motif']) + len(case['ligands']))
        (path / 'source.pdb').write_text('changed')
        with self.assertRaises(ValueError): contract.verify(path)

    def test_contract_and_equal_budget(self):
        cfg = contract.normalize({})
        self.assertEqual(contract.budget(cfg)['proposals_per_arm'], 8)
        for change in [dict(roots=6), dict(stage='cycles', engine='intellifold'), dict(ligand_profile='base_spec'),
                       dict(source_tolerance=float('nan')), dict(engine='protenix-mini'), dict(roots=True),
                       dict(guidance_source='tip-atoms'), dict(case_id='M0630_1j79', stage='backbones'),
                       dict(profile='studio-ame-beta-v1')]:
            with self.assertRaises(ValueError): contract.normalize(change)
        self.assertEqual(sum(n for _, n in search.allocation(['a', 'b', 'c'], 4)), 4)

    def test_frozen_reference_replay_preserves_bytes_and_detects_change(self):
        pdb, ref, metadata = fixture(self.base)
        before = (ref.read_bytes(), ref.stat().st_mtime_ns)
        geometry.freeze_root(self.base / 'bundle', pdb, metadata, ref)
        self.assertEqual((ref.read_bytes(), ref.stat().st_mtime_ns), before)
        st = gemmi.read_structure(str(pdb))
        st[0]['A'][0][0].pos.x += 1
        st.write_pdb(str(pdb))
        with self.assertRaisesRegex(ValueError, 'Cannot change a frozen'):
            geometry.freeze_root(self.base / 'bundle', pdb, metadata, ref)
        self.assertEqual((ref.read_bytes(), ref.stat().st_mtime_ns), before)

    def test_native_ligand_labels_require_explicit_entity_map(self):
        from motif_beta.prediction_identity import restore
        pdb, ref, _ = fixture(self.base)
        expected = json.loads(ref.read_text())['ligands'][0]['component']
        native = self.base / 'native.pdb'
        native.write_text(''.join(line[:17] + 'LIG' + line[20:] if line.startswith('HETATM') else line
                                  for line in pdb.read_text().splitlines(keepends=True)))
        before = native.read_bytes()
        doc = {'sequences': [{'ligand': {'id': 'B', 'ccd': expected}}]}
        mapped, receipt = restore(native, doc, self.base / 'mapped.pdb')
        self.assertEqual(native.read_bytes(), before)
        self.assertEqual(geometry.read(mapped), geometry.read(pdb))
        self.assertEqual(json.loads(receipt.read_text())['native_sha256'], contract.digest(native))
        self.assertTrue(geometry.evaluate(ref, mapped, 90)['guarded_pass'])
        with self.assertRaisesRegex(ValueError, 'submitted entity'):
            restore(native, {'sequences': [{'ligand': {'id': 'C', 'ccd': expected}}]}, self.base / 'bad.pdb')
        native.write_text(native.read_text().replace('LIG', 'BAD'))
        with self.assertRaisesRegex(ValueError, 'Unexpected native ligand'):
            restore(native, doc, self.base / 'bad.pdb')

    def test_geometry_rigid_invariance_missing_and_ligand_motion(self):
        pdb, ref, _ = fixture(self.base)
        scores = geometry.evaluate(ref, pdb, 90)
        self.assertTrue(scores['guarded_pass'])
        st = gemmi.read_structure(str(pdb))
        for chain in st[0]:
            for res in chain:
                for a in res:
                    x, y, z = a.pos.x, a.pos.y, a.pos.z
                    a.pos = gemmi.Position(-y + 17, x - 3, z + 5)
        moved = self.base / 'moved.pdb'; st.write_pdb(str(moved))
        self.assertLess(geometry.evaluate(ref, moved, 90)['objective'], 1e-5)
        for res in st[0]['B']:
            for a in res: a.pos.x += 4
        st.write_pdb(str(moved))
        bad = geometry.evaluate(ref, moved, 90)
        self.assertFalse(bad['paper_like_pass'])
        self.assertAlmostEqual(bad['worst_ligand_centroid'], 4, places=4)
        del st[0]['B']; st.write_pdb(str(moved))
        with self.assertRaises(ValueError): geometry.evaluate(ref, moved, 90)
        with self.assertRaises(ValueError): geometry.evaluate(ref, pdb, 90, guided=True)
        with self.assertRaises(ValueError): geometry.evaluate(ref, pdb, float('nan'))
        self.assertFalse(geometry.evaluate(ref, pdb, 80)['paper_like_pass'])

    def test_multiligand_worst_not_average(self):
        pdb, ref, _ = fixture(self.base, 'M0040_13pk')
        st = gemmi.read_structure(str(pdb))
        for res in st[0]['D']:
            for atom in res: atom.pos.x += 4
        st.write_pdb(str(pdb))
        result = geometry.evaluate(ref, pdb, 90)
        self.assertEqual(len(result['ligands']), 3)
        self.assertAlmostEqual(result['worst_ligand_centroid'], 4, places=4)
        self.assertFalse(result['paper_like_pass'])

    def test_atom_completeness_identity_and_degenerate_fit_fail(self):
        pdb, ref, _ = fixture(self.base)
        st = gemmi.read_structure(str(pdb))
        st[0]['B'][0].remove_atom(st[0]['B'][0][0].name, '\x00')
        broken = self.base / 'broken.pdb'; st.write_pdb(str(broken))
        with self.assertRaisesRegex(ValueError, 'atom set'): geometry.evaluate(ref, broken, 90)
        st = gemmi.read_structure(str(pdb)); st[0]['A'][1].name = 'GLN'; st.write_pdb(str(broken))
        with self.assertRaisesRegex(ValueError, 'identity'): geometry.evaluate(ref, broken, 90)
        with self.assertRaisesRegex(ValueError, 'Degenerate'):
            geometry.fit(np.array([[0., 0, 0], [1., 0, 0], [2., 0, 0]]), np.array([[0., 0, 0], [1., 0, 0], [2., 0, 0]]))

    def test_centroid_does_not_hide_pose(self):
        pdb, ref, _ = fixture(self.base)
        st = gemmi.read_structure(str(pdb)); atoms = [a for r in st[0]['B'] for a in r]
        center = np.mean([[a.pos.x, a.pos.y, a.pos.z] for a in atoms], axis=0)
        for a in atoms: a.pos = gemmi.Position(2 * center[0] - a.pos.x, 2 * center[1] - a.pos.y, a.pos.z)
        st.write_pdb(str(pdb))
        result = geometry.evaluate(ref, pdb, 90)
        self.assertLess(result['worst_ligand_centroid'], .001)
        self.assertGreater(result['ligands'][0]['pose_rmsd'], 1)

    def test_search_rejects_guidance_mixed_roots_and_deduplicates(self):
        pdb, ref, _ = fixture(self.base)
        m = geometry.evaluate(ref, pdb, 90)
        a = dict(id='a', metrics=m); b = dict(id='b', metrics={**m, 'objective': .5})
        self.assertEqual(search.rank([b, a], 4), [a])
        b['metrics']['sequence'] = 'different'
        self.assertEqual(search.advance('greedy', [a, b]), [a])
        self.assertEqual(search.advance('beam', [a, b], 2), [a, b])
        b['metrics']['guided'] = True
        with self.assertRaises(ValueError): search.rank([a, b], 2)
        b['metrics']['guided'] = False; b['metrics']['reference_sha256'] = 'other'
        with self.assertRaises(ValueError): search.rank([a, b], 2)

    def test_all_template_adapters_keep_exact_positions(self):
        pdb, ref, _ = fixture(self.base)
        sequence = geometry.evaluate(ref, pdb, 90)['sequence']
        for engine in contract.ENGINES:
            out = self.base / engine
            result = templates.prepare(ref, sequence, engine, out)
            self.assertEqual(result, templates.prepare(ref, sequence, engine, out))
            structure = gemmi.read_structure(str(out / 'motif.cif'))
            self.assertEqual([r.seqid.num for r in structure[0]['A']], [2, 5, 8])
            self.assertEqual(result['query_positions_1based'], [2, 5, 8])
            if engine == 'intellifold':
                self.assertEqual([i for i, c in enumerate((out / 'motif.a3m').read_text().splitlines()[1]) if c != '-'], [1, 4, 7])
            if engine == 'protenix-v2':
                import protenix_predict
                doc = {'sequences': [{'protein': dict(id='A', sequence=sequence, msa='empty')}], **result['fragment']}
                path = out / 'job.yaml'; path.write_text(json.dumps(doc))
                converted, _, _ = protenix_predict.convert_yaml(path, template_capable=True)
                sidecar = Path(converted['sequences'][0]['proteinChain']['templatesPath'])
                self.assertEqual(json.loads(sidecar.read_text())[0]['queryIndices'], [1, 4, 7])

    def test_all_41_source_guides_without_generated_backbone(self):
        for c in contract.catalog()['cases']:
            sequence = list('A' * 50)
            mapping = {r['source_selector']: 2 + 3 * i for i, r in enumerate(reversed(c['protein_motif']))}
            for r in c['protein_motif']:
                sequence[mapping[r['source_selector']] - 1] = geometry.LETTERS[r['component']]
            sequence = ''.join(sequence)
            ref = self.base / c['case_id'] / 'source.json'
            result = source_guide.prepare(c['case_id'], mapping, sequence, ref)
            self.assertNotIn('backbone_atoms', result)
            self.assertFalse(result['backbone_generated'])
            if result['selected_atom_rmsd_to_benchmark'] is not None:
                self.assertLess(result['selected_atom_rmsd_to_benchmark'], 1e-6)
            else:
                self.assertLess(len(result['selected_atoms']), 3)
            self.assertEqual(result, source_guide.prepare(c['case_id'], mapping, sequence, ref))
            for engine in contract.ENGINES:
                receipt = templates.prepare(ref, sequence, engine, ref.parent / engine)
                self.assertEqual(receipt['coordinate_source'], 'benchmark-residues')
                st = gemmi.read_structure(str(ref.parent / engine / 'motif.cif'))
                self.assertEqual(len(st[0]['A']), len(mapping))
                for r in c['protein_motif']:
                    exported = next(res for res in st[0]['A'] if res.seqid.num == mapping[r['source_selector']])
                    for atom in exported:
                        np.testing.assert_allclose(list(atom.pos), r['atoms'][atom.name]['xyz_angstrom'], atol=1e-5)

    def test_source_guide_mapping_tip_atoms_and_mutations_fail(self):
        c = contract.case('M0054_1qfe')
        mapping = {r['source_selector']: i + 1 for i, r in enumerate(c['protein_motif'])}
        sequence = ''.join(geometry.LETTERS[r['component']] for r in c['protein_motif']) + 'AAA'
        ref = self.base / 'source.json'
        for bad in ({}, dict.fromkeys(mapping, 1), {**mapping, 'A86': True}, {**mapping, 'A86': 7}):
            with self.assertRaises(ValueError): source_guide.prepare(c['case_id'], bad, sequence, ref)
        with self.assertRaisesRegex(ValueError, 'identity'):
            source_guide.prepare(c['case_id'], mapping, 'AAAAAA', ref)
        st = gemmi.read_structure(str(contract.DATA / c['source_file']))
        st[0]['A'][0].remove_atom('N', '\x00')
        tips = self.base / 'missing-backbone.pdb'; st.write_pdb(str(tips))
        with self.assertRaisesRegex(ValueError, 'N/CA/C/O'):
            source_guide.prepare(c['case_id'], mapping, sequence, ref, structure=tips)

    def test_imported_protein_preserves_one_coordinate_frame(self):
        c = contract.case('M0054_1qfe')
        mapping = {r['source_selector']: i + 1 for i, r in enumerate(c['protein_motif'])}
        sequence = 'EHKAAA'
        st = gemmi.read_structure(str(contract.DATA / c['source_file']))
        for chain in st[0]:
            for residue in chain:
                for atom in residue: atom.pos.x += 20
        path = self.base / 'native.pdb'; st.write_pdb(str(path))
        ref = self.base / 'source.json'
        result = source_guide.prepare(c['case_id'], mapping, sequence, ref, structure=path)
        self.assertEqual(result['source_mode'], 'imported-protein-residues')
        self.assertLess(result['selected_atom_rmsd_to_benchmark'], 1e-5)
        self.assertAlmostEqual(result['atoms']['A:1:']['atoms']['CA']['xyz'][0],
                               c['protein_motif'][0]['atoms']['CA']['xyz_angstrom'][0] + 20, places=4)
        self.assertEqual(set(result['atoms']), {'A:1:', 'A:2:', 'A:3:'})
        with self.assertRaisesRegex(ValueError, 'Cannot change'):
            source_guide.prepare(c['case_id'], mapping, sequence, ref)

    def test_full_policy_orchestration_and_budgets_with_fake_models(self, guidance_source='rfd3-root'):
        from motif_beta import cycling
        pdb, ref, _ = fixture(self.base)
        sequence = geometry.evaluate(ref, pdb, 90)['sequence']
        cfg = contract.normalize(dict(case_id='M0054_1qfe', length=50, stage='cycles', guidance_source=guidance_source))
        calls = []
        def designer(root, reference, structure, directory, method, count, seed):
            calls.append(('design', method, count))
            return [dict(valid=True, sequence=sequence) for _ in range(count)]
        class FakePredictor:
            def __init__(self, *args): pass
            def predict(self, docs, directory, seed):
                calls.append(('fold', directory.name, len(docs)))
                # Assert untemplated ranking really receives no template key.
                self_guided = directory.name == 'guided'
                for document in docs.values():
                    assert ('templates' in document) == self_guided
                    assert document['sequences'][0]['protein']['msa'] == 'empty'
                return {name: str(pdb) for name in docs}
            def close(self): calls.append(('close',))
        with patch.object(cycling, 'chemistry_audit', return_value={'ready': True}):
            result = cycling.run(self.base, self.base, cfg,
                [dict(id='root1', reference=str(ref), backbone=str(pdb))],
                predictor_factory=FakePredictor, designer=designer)
        self.assertEqual(result['attempted_sequences'], 64)
        self.assertEqual(result['checked'], 64)
        self.assertEqual(sum(c[2] for c in calls if c[:2] == ('fold', 'untemplated')), 64)
        self.assertEqual(sum(c[2] for c in calls if c[:2] == ('fold', 'guided')), 64)
        self.assertEqual(calls[-1], ('close',))
        self.assertFalse(result['independent_family_validation'])

    def test_source_guide_policy_orchestration(self):
        self.test_full_policy_orchestration_and_budgets_with_fake_models('benchmark-residues')
        receipts = list(self.base.glob('cycles/**/template.json'))
        self.assertTrue(receipts)
        self.assertEqual({json.loads(p.read_text())['coordinate_source'] for p in receipts}, {'benchmark-residues'})

    def test_operation_replay_detects_changed_outputs(self):
        from motif_beta.cycling import commit, replay
        marker = self.base / 'complete.json'; artifact = self.base / 'out.txt'
        artifact.write_text('original')
        commit(marker, {'seed': 1}, ['result'], [artifact])
        self.assertEqual(replay(marker, {'seed': 1}), ['result'])
        with self.assertRaises(ValueError): replay(marker, {'seed': 2})
        artifact.write_text('changed')
        with self.assertRaises(ValueError): replay(marker, {'seed': 1})

    def test_original_input_scoring_is_distinct_from_root_recovery(self):
        pdb, ref, _ = fixture(self.base)
        st = gemmi.read_structure(str(pdb))
        # Change one catalytic atom in the root, then freeze that as the root
        # geometry while retaining the original input objective.
        st[0]['A'][4].find_atom('NE2', '\x00').pos.x += .8
        changed = self.base / 'changed.pdb'; st.write_pdb(str(changed))
        data = json.loads(ref.read_text())
        data['atoms'] = geometry.read(changed)
        other = self.base / 'other-reference.json'; contract.atomic(other, data)
        score = geometry.evaluate(other, changed, 90)
        self.assertLess(score['motif_rmsd'], 1e-6)
        self.assertGreater(score['source_rmsd'], .1)
        self.assertGreater(score['objective'], .04)
        self.assertEqual(score['ranking_motif_reference'], 'original_input_selected_atoms')
        self.assertEqual([r['query_position'] for r in score['input_motif']['residues']], [2, 5, 8])
        self.assertEqual([r['source_residue'] for r in score['input_motif']['residues']], ['A86', 'A143', 'A170'])
        # Motif-only assessment accepts apo or sparse predictor outputs without
        # requiring unrelated ligands, and uses the same source atom alignment.
        del st[0]['B']; st.write_pdb(str(changed))
        report = geometry.input_motif_report(other, changed)
        self.assertAlmostEqual(report['rmsd'], score['source_rmsd'])

    def test_root_ranking_uses_pre_copy_input_motif_geometry(self):
        from motif_beta.runner import rank_roots
        rows = [dict(id='worse', candidate_motif_rmsd_to_input=1.5, input_motif={'rmsd': 0.0}),
                dict(id='better', candidate_motif_rmsd_to_input=.1, input_motif={'rmsd': .001})]
        ranked = rank_roots(rows)
        self.assertEqual([r['id'] for r in ranked], ['better', 'worse'])
        self.assertEqual([r['motif_rank'] for r in ranked], [1, 2])
        rows[0]['candidate_motif_rmsd_to_input'] = float('nan')
        with self.assertRaises(ValueError): rank_roots(rows)


if __name__ == '__main__': unittest.main()
