"""Preflight and entry-point isolation for a real-model branch validation."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Sources/iProteinStudio/Resources/pipeline/scripts/nise"))
import branch_test
import campaign
from runtime import digest


class BranchTest(unittest.TestCase):
    def test_imported_assets_are_frozen_and_complete(self):
        settings = json.loads((ROOT / "Validation/experiments/biotin_parent_noising_v1/request.json").read_text())
        with tempfile.TemporaryDirectory() as raw:
            out = Path(raw); inputs = out / "branch_test_inputs"; inputs.mkdir()
            parent = dict(name="candidate", sequence="ACD", passed=True,
                          ligand_plddt=90, pbind=.5, score=1.4, ca_rmsd=.5, ligand_rmsd=.7)
            (inputs / "parent.json").write_text(json.dumps(parent))
            for name in ("parent.pdb", "reference.pdb", "ligand_atom_map.json"):
                (inputs / name).write_text("fixture")
            descriptor = dict(schema=1, cycle=2, source_run="previous", source_candidate="candidate",
                              files={p.name: digest(p) for p in inputs.iterdir()})
            self.assertEqual(len(branch_test.validate(out, settings, descriptor)), 4)
            for overrides in ({"noise_predictions":64}, {"partial_noising":False}, {"nesso_screen":True}, {"trajectories":2}):
                with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                    branch_test.validate(out, {**settings, **overrides}, descriptor)
            broken = copy.deepcopy(descriptor); broken['files'].pop('reference.pdb')
            with self.assertRaisesRegex(ValueError, "reference"):
                branch_test.validate(out, settings, broken)
            (inputs / 'parent.pdb').write_text('changed')
            with self.assertRaisesRegex(ValueError, "changed"):
                branch_test.validate(out, settings, descriptor)
            descriptor['files']['parent.pdb'] = digest(inputs / 'parent.pdb')
            parent['score'] = 2
            (inputs / 'parent.json').write_text(json.dumps(parent))
            descriptor['files']['parent.json'] = digest(inputs / 'parent.json')
            with self.assertRaisesRegex(ValueError, "objective"):
                branch_test.validate(out, settings, descriptor)

    def test_normal_campaign_cannot_silently_use_branch_descriptor(self):
        with tempfile.TemporaryDirectory() as raw:
            config = Path(raw) / 'nise_config.json'
            config.write_text(json.dumps({'branch_test': {}}))
            with self.assertRaisesRegex(ValueError, 'explicit branch-test'):
                campaign.run(config)
            config.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'explicit branch-test'):
                campaign.run(config, branch_test=True)


if __name__ == '__main__':
    unittest.main()
