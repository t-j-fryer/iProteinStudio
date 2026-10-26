"""Native CPU sparse-template feature tests; run separately in each engine env.

MOTIF_FEATURE_ENGINE=protenix-v2 or intellifold. No models or weights loaded.
"""
import importlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Sources/iProteinStudio/Resources/pipeline/scripts'))
from motif_beta import contract, geometry, source_guide, templates

ENGINE = os.environ.get('MOTIF_FEATURE_ENGINE', 'protenix-v2')
PACKAGE = 'protenix' if ENGINE == 'protenix-v2' else 'intellifold'


def features(folder, sequence, receipt):
    utils = importlib.import_module(PACKAGE + '.data.template.template_utils')
    module = importlib.import_module(PACKAGE + '.data.template.template_featurizer')
    if ENGINE == 'protenix-v2':
        import protenix_predict
        document = dict(sequences=[dict(protein=dict(id='A', sequence=sequence, msa='empty'))], **receipt['fragment'])
        path = folder / 'query.yaml'; path.write_text(json.dumps(document))
        converted, _, _ = protenix_predict.convert_yaml(path, template_capable=True)
        entries = json.loads(Path(converted['sequences'][0]['proteinChain']['templatesPath']).read_text())
        featurizer = utils.TemplateHitFeaturizer(mmcif_dir=str(folder), fetch_remote=False)
        result = featurizer.parse_json_templates(entries, sequence)
    else:
        parser = importlib.import_module(PACKAGE + '.data.template.template_parser')
        # Exercise Studio's actual user-template policy, including its local-only
        # whitelist. No model/CCD/database download is invoked.
        import intellifold_user_template
        import intellifold.data.module.inference as inference
        intellifold_user_template.install(folder / 'intellifold_manifest.json')
        featurizer = inference.construct_template_featurizer()
        hits = parser.HmmsearchA3MParser.parse(sequence, (folder / 'motif.a3m').read_text(), skip_first=False)
        result, _ = featurizer.get_templates('sparse', sequence, hits)
    if result.errors or len(result.features) != 1:
        raise AssertionError(str(result.errors) + ' ' + str(result.warnings))
    packaged = utils.TemplateFeatures.package_template_features(hit_features=result.features)
    dense = utils.TemplateFeatures.fix_template_features(packaged, len(sequence))
    obj = module.Templates.from_data_dict(dense)
    model_features = obj.as_protenix_dict() if ENGINE == 'protenix-v2' else obj.as_dict()
    return model_features


@unittest.skipUnless(importlib.util.find_spec(PACKAGE), 'Run with the requested installed engine Python.')
class NativeMotifFeatures(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        os.environ.setdefault('INTELLIFOLD_CACHE', str(self.base / 'cache'))

    def make(self, case, name='base', transform=None):
        mapping = {r['source_selector']: 2 + 4 * i for i, r in enumerate(reversed(case['protein_motif']))}
        sequence = list('A' * 60)
        for r in case['protein_motif']: sequence[mapping[r['source_selector']] - 1] = geometry.LETTERS[r['component']]
        sequence = ''.join(sequence)
        ref = self.base / case['case_id'] / name / 'guide.json'
        guide = source_guide.prepare(case['case_id'], mapping, sequence, ref)
        if transform:
            transform(guide)
            ref.write_text(json.dumps(guide))
        folder = ref.parent / ENGINE
        receipt = templates.prepare(ref, sequence, ENGINE, folder)
        return features(folder, sequence, receipt), sorted(mapping.values())

    def test_all_41_native_feature_masks(self):
        audit = []
        for case in contract.catalog()['cases']:
            with self.subTest(case=case['case_id']):
                f, positions = self.make(case)
                observed = (np.flatnonzero(f['template_atom_mask'][0].any(-1)) + 1).tolist()
                self.assertEqual(observed, positions)
                frames = f['template_backbone_frame_mask'][0]
                if frames.ndim == 2: frames = np.diag(frames)
                self.assertEqual((np.flatnonzero(frames) + 1).tolist(), positions)
                self.assertTrue(np.isfinite(f['template_unit_vector']).all())
                audit.append(dict(case_id=case['case_id'], query_positions=observed))
        if os.environ.get('MOTIF_FEATURE_AUDIT'):
            contract.atomic(os.environ['MOTIF_FEATURE_AUDIT'], dict(engine=ENGINE, cases=audit, inference=False))

    def test_distal_sidechains_do_not_supply_atomic_template_constraints(self):
        c = contract.case('M0054_1qfe')
        before, _ = self.make(c)
        def move_tip(ref):
            for residue in ref['atoms'].values():
                for name, atom in residue['atoms'].items():
                    if name not in {'N', 'CA', 'C', 'O', 'CB'}:
                        atom['xyz'][0] += 3
        after, _ = self.make(c, 'tips-moved', move_tip)
        for key in ('template_distogram', 'template_unit_vector', 'template_backbone_frame_mask', 'template_pseudo_beta_mask'):
            np.testing.assert_allclose(before[key], after[key], atol=2e-5, err_msg=key)
        self.assertFalse(np.allclose(before['template_atom_positions'], after['template_atom_positions']))


if __name__ == '__main__': unittest.main()
