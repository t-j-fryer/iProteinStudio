"""Execute the ported search/funnel with deterministic model fixtures.

Run in the managed Boltz environment (NumPy, RDKit, YAML, gemmi); no inference.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Sources/iProteinStudio/Resources/pipeline/scripts/nise"))
os.environ.setdefault("NANOHUNTER_ROOT", str(ROOT))
import nise_lib as science
import nise_run
import preorg
from runtime import Backend, Journal, atomic


class FixtureBackend:
    """Model-boundary fake; use the real search, ranking and operation journal."""
    def __init__(self, root, fail_after=None):
        self.output = root
        self.journal = Journal(root)
        self.design_calls = self.fold_calls = 0
        self.fail_after = fail_after

    def freeze_config(self, cfg):
        pass

    def design(self, pdb, directory, n, smiles, args, seq_temp, fs_temp, seed, designed, constrain_ss):
        receipt = Path(directory) / "sampling.json"
        specification = dict(n=n, seed=seed)
        saved = self.journal.load(receipt, specification)
        if saved is not None:
            return saved
        self.design_calls += 1
        sequences = ["A" * 65] * n
        self.journal.save(receipt, specification, sequences)
        return sequences

    def fold(self, sequences, smiles, directory, args, pocket=None):
        result = {}
        for name, sequence in sequences.items():
            unit = Path(directory) / name
            receipt = unit / "completed.json"
            spec = dict(sequence=sequence, pocket=pocket)
            saved = self.journal.load(receipt, spec)
            if saved is None:
                if self.fail_after is not None and self.fold_calls >= self.fail_after:
                    raise RuntimeError("injected model interruption")
                self.fold_calls += 1
                unit.mkdir(parents=True, exist_ok=True)
                pdb = unit / (name + ".pdb"); pdb.write_text("fixture structure\n")
                saved = dict(name=name, pdb=str(pdb), ligand_plddt=95.0, pbind=0.9)
                self.journal.save(receipt, spec, saved, [pdb])
            result[name] = SimpleNamespace(**saved)
        return result

    def record_candidate(self, node, passed, pred):
        Backend.record_candidate(self, node, passed, pred)

    def write_summary(self, summary):
        atomic(self.output / "search_summary.json", summary)


class SearchTests(unittest.TestCase):
    def test_initial_nesso_funnel_both_generators_filters_and_replay(self):
        import nesso_screen
        from nesso_contract import installation, SCALARS
        class ScoreClient:
            calls = 0
            def __init__(self, *args): pass
            def close(self): pass
            def score(self, sequence, smiles, directory):
                type(self).calls += 1
                values = {**dict.fromkeys(SCALARS, 0.0), 'entropy_crop_pl': .2, 'affinity_probability_binary': .8}
                atomic(directory / 'affinity.json', values)
                return {'scores': values}
        class InitialBackend(FixtureBackend):
            screen_initial = Backend.screen_initial
            def __init__(self, root):
                super().__init__(root)
                self.root = root
                self.scripts = ROOT / 'Sources/iProteinStudio/Resources/pipeline/scripts'
                self.settings = dict(seed=0, scheduler='cycle-wave', phase0_nesso_screen=True,
                                     phase0_nesso_refine_top_k=1, phase0_nesso_expand_top_k=2)
                self.nesso_worker = None; self.nesso_scores = {}
                self.batches = []; self.atom_visits = []
                base = installation(root); base.mkdir(parents=True)
                (base / 'receipt.json').write_text('fixture installation')
            def initial_contacts(self, smiles, count): return ['C1']
            def initial_backbones(self, smiles, directory, args):
                directory.mkdir(parents=True, exist_ok=True)
                result = {}
                for i in range(args.num_starts):
                    p = directory / f'L{i:03d}.pdb'; p.write_text('fixture backbone')
                    result[f'L{i:03d}'] = str(p)
                return result
            def fold(self, sequences, smiles, directory, args, pocket=None):
                self.batches.append((Path(directory).resolve().relative_to(self.output.resolve()).as_posix(), len(sequences), pocket is not None))
                return super().fold(sequences, smiles, directory, args, pocket)
            def check_atom_requirements(self, pred):
                self.atom_visits.append(pred.name)
                # Reject one preselected expansion lineage: no fallback folding.
                return not ('_e' in pred.name and pred.name.startswith('L000'))
        for method in ['protein-hunter', 'rfdiffusion3']:
            with self.subTest(method=method), tempfile.TemporaryDirectory() as raw:
                root = Path(raw); backend = InitialBackend(root)
                ScoreClient.calls = 0
                args = self.arguments(root) + ['--backbone-method', method, '--num-starts', '3',
                    '--phase0-refine-cycles', '2', '--phase0-seqs1', '3', '--phase0-gate-seqs', '3',
                    '--phase0-seqs2', '5', '--max-cycles', '1']
                # The helper disables pockets; remove it to check the real stage routing.
                args.remove('--no-phase0-constraints')
                with patch.object(nesso_screen, 'NessoClient', ScoreClient), patch.object(
                        science, 'self_consistency', return_value=SimpleNamespace(ca_rmsd=.5, ligand_rmsd=.5, ok=True)):
                    nise_run.main(args, backend=backend)
                    self.assertIn(('phase0/cycle01/fold', 3, True), backend.batches)
                    self.assertIn(('phase0/cycle02/fold', 3, True), backend.batches)
                    self.assertIn(('phase0/cycle03/fold', 9, False), backend.batches)
                    self.assertIn(('phase0/cycle04/fold', 2, False), backend.batches)
                    self.assertEqual(ScoreClient.calls, 63)  # 9 + 9 + 45, never cycle00 or gate
                    self.assertEqual(len([n for n in backend.atom_visits if '_e' in n]), 2)
                    summary = json.loads((root / 'search_summary.json').read_text())
                    self.assertEqual(summary['n_trajectories'], 1)
                    calls = backend.design_calls, backend.fold_calls, ScoreClient.calls
                    before = (root / 'trajectory.csv').read_bytes()
                    nise_run.main(args, backend=backend)
                    self.assertEqual((backend.design_calls, backend.fold_calls, ScoreClient.calls), calls)
                    self.assertEqual((root / 'trajectory.csv').read_bytes(), before)

    def test_rfd3_replaces_only_the_initial_hallucination_then_uses_the_same_search(self):
        class DiffusionBackend(FixtureBackend):
            def initial_backbones(self, smiles, directory, args):
                directory.mkdir(parents=True, exist_ok=True)
                result = {}
                for index in range(args.num_starts):
                    path = directory / f'L{index:03d}_ref.pdb'
                    path.write_text('fixture diffusion backbone\n')
                    result[f'L{index:03d}'] = str(path)
                return result
            def fold(self, sequences, smiles, directory, args, pocket=None):
                if Path(directory).name == 'cycle00':
                    raise AssertionError('RFdiffusion3 must replace cycle00 Boltz hallucination')
                return super().fold(sequences, smiles, directory, args, pocket)
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            backend = DiffusionBackend(root)
            with patch.object(science, 'generate_random_binder', side_effect=AssertionError('unexpected hallucination')), patch.object(
                    science, 'self_consistency', return_value=SimpleNamespace(ca_rmsd=.5, ligand_rmsd=.5, ok=True)):
                arguments = self.arguments(root) + ['--backbone-method', 'rfdiffusion3']
                nise_run.main(arguments, backend=backend)
                self.assertEqual(json.loads((root / 'search_summary.json').read_text())['n_trajectories'], 2)
                self.assertTrue((root / 'phase0/cycle01/design').is_dir())
                before = (root / 'trajectory.csv').read_bytes()
                calls = (backend.design_calls, backend.fold_calls)
                nise_run.main(arguments, backend=backend)
                self.assertEqual((backend.design_calls, backend.fold_calls), calls)
                self.assertEqual((root / 'trajectory.csv').read_bytes(), before)

    def arguments(self, root):
        ligand = root / "ligand.yaml"
        ligand.write_text('sequences:\n  - ligand:\n      smiles: "CCO"\n')
        return ["--template-yaml", str(ligand), "--out-dir", str(root), "--num-starts", "2",
                "--trajectories", "2", "--phase0-refine-cycles", "1", "--phase0-seqs1", "2",
                "--phase0-seqs2", "2", "--nise-seqs", "2", "--max-cycles", "3", "--patience", "2",
                "--no-phase0-constraints"]

    def run_search(self, root, backend):
        with patch.object(science, "self_consistency", return_value=SimpleNamespace(ca_rmsd=0.5, ligand_rmsd=0.5, ok=True)):
            nise_run.main(self.arguments(root), backend=backend)

    def test_search_resumes_phase0_without_losing_independent_trajectories(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            interrupted = FixtureBackend(root, fail_after=3)
            with self.assertRaisesRegex(RuntimeError, "injected model interruption"):
                self.run_search(root, interrupted)
            resumed = FixtureBackend(root)
            self.run_search(root, resumed)
            summary = json.loads((root / "search_summary.json").read_text())
            self.assertEqual(summary["n_trajectories"], 2)
            self.assertEqual(len({r["origin"] for r in summary["trajectory_winners"]}), 2)
            before = (root / "trajectory.csv").read_bytes()
            replay = FixtureBackend(root)
            self.run_search(root, replay)
            self.assertEqual((replay.design_calls, replay.fold_calls), (0, 0))
            self.assertEqual((root / "trajectory.csv").read_bytes(), before)
            self.assertFalse((root / "cycle03").exists(), "Patience should stop each trajectory after two non-improving cycles")

    def test_two_parents_advance_and_nesso_shortlists_each_trajectory_before_boltz(self):
        import re
        import nesso_screen
        from nesso_contract import installation, SCALARS
        from test_nesso_screen import FakeClient
        class ScreenBackend(FixtureBackend):
            def __init__(self, root):
                super().__init__(root)
                self.root = root
                self.scripts = ROOT / "Sources/iProteinStudio/Resources/pipeline/scripts"
                self.settings = dict(seed=0, scheduler="cycle-wave", nesso_top_k=2, beam=2)
                self.nesso_worker = None
                self.nesso_scores = {}
                self.before = []; self.after = []
            def fold(self, sequences, smiles, directory, args, pocket=None):
                if all(re.fullmatch(r"c\d+_t\d+_n\d+_s\d+", n) for n in sequences):
                    self.before.append(len(sequences))
                    sequences = nesso_screen.screen(self, sequences, smiles, Path(directory).parent / "nesso")
                    self.after.append(len(sequences))
                return super().fold(sequences, smiles, directory, args, pocket)
            def record_advancement(self, cycle, trajectories):
                Backend.record_advancement(self, cycle, trajectories)
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            base = installation(root); base.mkdir(parents=True)
            (base / "receipt.json").write_text("fixture")
            FakeClient.calls = FakeClient.loads = FakeClient.closes = 0
            FakeClient.fail_at = None
            backend = ScreenBackend(root)
            arguments = self.arguments(root) + ["--beam", "2", "--nise-seqs", "3"]
            with patch.object(nesso_screen, "NessoClient", FakeClient), patch.object(science, "self_consistency",
                    return_value=SimpleNamespace(ca_rmsd=0.5, ligand_rmsd=0.5, ok=True)):
                nise_run.main(arguments, backend=backend)
                self.assertEqual(backend.before, [6, 12])
                self.assertEqual(backend.after, [4, 4])
                advancement = json.loads((root / "cycle01/advancement.json").read_text())
                self.assertEqual([len(t["selected"]) for t in advancement["trajectories"]], [2, 2])
                first = (root / "trajectory.csv").read_bytes()
                counts = (backend.fold_calls, backend.design_calls, FakeClient.calls)
                nise_run.main(arguments, backend=backend)
                self.assertEqual(counts, (backend.fold_calls, backend.design_calls, FakeClient.calls))
                self.assertEqual(first, (root / "trajectory.csv").read_bytes())

    def test_missing_affinity_is_an_error_even_in_legacy_auto_mode(self):
        for probability in (None, float("nan"), -1, 2):
            with self.subTest(probability=probability), self.assertRaises(ValueError):
                science.rank_score(SimpleNamespace(name="fixture", ligand_plddt=95, pbind=probability), "auto")

    def test_ligand_atom_correspondence_must_match_before_rmsd(self):
        def atom(name):
            line = list(" " * 80)
            line[:6] = "HETATM"; line[12:16] = name.rjust(4)
            line[21] = "B"; line[76:78] = " C"
            return "".join(line)
        records = {"prediction": [atom("C1"), atom("C2")], "reference": [atom("C2"), atom("C3")]}
        with patch.object(science, "_iter_pdb_atoms", side_effect=lambda p: records[p]):
            with self.assertRaisesRegex(ValueError, "correspondence"):
                science.self_consistency("prediction", "reference")

    def test_beta_preorganisation_can_reorder_shortlist_without_becoming_a_gate(self):
        first = SimpleNamespace(preorg_rmsd=0.956, global_ca_rmsd=0.583)
        second = SimpleNamespace(preorg_rmsd=1.255, global_ca_rmsd=0.923)
        self.assertGreater(preorg.combine(1.9542, first)[0], preorg.combine(1.9613, second)[0])
        self.assertEqual(preorg.combine(1.5, SimpleNamespace(preorg_rmsd=5, global_ca_rmsd=8))[0], 1.5)

    def test_apo_input_contains_no_ligand_affinity_or_pocket_constraint(self):
        import yaml
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "apo.yaml"
            preorg.write_apo_yaml(path, "ACDEFG")
            document = yaml.safe_load(path.read_text())
            self.assertEqual(set(document), {"sequences", "version"})
            self.assertEqual(document["sequences"], [{"protein": {"id": "A", "sequence": "ACDEFG", "msa": "empty"}}])


if __name__ == "__main__":
    unittest.main(verbosity=2)
