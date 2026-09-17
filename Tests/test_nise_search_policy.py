"""NISE efficient search: real orchestration, deterministic model boundaries."""
import copy
import json
import os
from pathlib import Path
import random
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'Sources/iProteinStudio/Resources/pipeline/scripts'
sys.path[:0] = [str(SCRIPTS / 'nise'), str(SCRIPTS), str(ROOT / 'Tests')]
os.environ.setdefault('NANOHUNTER_ROOT', str(ROOT))
from search_policy import affinity_selection, proposal_levels
from runtime import Backend, atomic, digest
from test_nise_science import FixtureBackend
import test_nise_science as fixtures
import nise_run
import nise_lib as science
import contract


class PolicyTests(unittest.TestCase):
    def test_exact_upper_bound_preserves_exhaustive_winners_and_ties(self):
        rng = random.Random(31)
        for diverse in (False, True):
            for batch in (1, 8):
                for repeat in range(12):
                    nodes = [NS(name=f'n{i:03}', ligand_plddt=rng.randrange(101),
                                probability=rng.choice([0, .3, .8, 1]), score=None, group=i % 7)
                             for i in range(100)]
                    def score(items):
                        for n in items: n.score = n.ligand_plddt / 100 + n.probability
                    reference = copy.deepcopy(nodes); score(reference)
                    def winners(items):
                        result = []
                        for g in range(7):
                            result += sorted([n for n in items if n.group == g and n.score >= .8],
                                             key=lambda n: (-n.score, n.name))[:1 if diverse else 3]
                        return [n.name for n in sorted(result, key=lambda n: (-n.score, n.name))[:4 if diverse else 100]]
                    scored, skipped = affinity_selection(nodes, score, lambda n:n.group,
                        per_group=1 if diverse else 3, total_groups=4 if diverse else None,
                        minimum=.8, batch_size=batch)
                    self.assertEqual(winners(scored), winners(reference))
        tied = [NS(name='a', ligand_plddt=100, score=2), NS(name='b', ligand_plddt=100, score=None)]
        scored, skipped = affinity_selection(tied[1:], lambda ns: [setattr(n,'score',2) for n in ns],
                                             lambda n:0, previous=tied[:1])
        self.assertEqual(len(scored),1)
        self.assertFalse(skipped)

    def test_validation_levels_and_migration(self):
        self.assertEqual(proposal_levels(64, True, 16), [16,32,64])
        self.assertEqual(proposal_levels(50, True, 16), [16,32,50])
        self.assertEqual(proposal_levels(64, False, 16), [64])
        new = contract.normalize({'smiles':'CCO'})
        self.assertEqual((new['num_starts'],new['patience'],new['adaptive_proposals']), (1000,4,False))
        self.assertEqual((new['max_cycles'],new['beam'],new['early_score_gate']), (30,3,.8))
        old = contract.normalize({'smiles':'CCO','search_policy_version':1})
        self.assertEqual((old['num_starts'],old['patience']), (100,5))
        self.assertEqual((old['max_cycles'],old['beam'],old['selective_affinity']), (30,1,False))
        for changes in ({'early_score_gate':float('nan')},{'early_score_gate':2.1},
                        {'min_improvement':-1}, {'selective_affinity':1},
                        {'adaptive_proposals':True,'initial_proposals':65},
                        {'adaptive_proposals':True,'initial_proposals':2}):
            with self.assertRaises(ValueError): contract.normalize({'smiles':'CCO',**changes})
        budget = contract.prediction_budget({'smiles':'CCO','adaptive_proposals':True,'nesso_screen':True})
        self.assertEqual(budget['first_cycle_boltz_max'], 8*48)
        self.assertEqual(budget['later_cycle_boltz_max'], 8*32)


class EfficientBackend(FixtureBackend):
    screen_initial = Backend.screen_initial
    record_advancement = Backend.record_advancement
    def __init__(self, root, nesso=False, fail_affinity=None):
        super().__init__(root)
        self.root = root; self.scripts = SCRIPTS
        self.settings = dict(seed=0, scheduler='cycle-wave', beam=3, nesso_top_k=3,
            phase0_nesso_screen=nesso, phase0_nesso_refine_top_k=1, phase0_nesso_expand_top_k=3)
        self.nesso_worker = None; self.nesso_scores = {}; self.nesso = nesso
        self.affinity_calls = 0; self.fail_affinity = fail_affinity
        self.samples = []; self.affinity_names = []
    def initial_contacts(self,*a): return ['C1']
    def check_atom_requirements(self,pred): return not pred.name.endswith('_s0')
    def finish_scoring_stage(self): pass
    def initial_backbones(self, smiles, directory, args):
        directory.mkdir(parents=True,exist_ok=True)
        result={}
        for i in range(args.num_starts):
            p=directory/f'L{i:03}.pdb';p.write_text('fixture')
            result[f'L{i:03}']=str(p)
        return result
    def design(self,pdb,directory,n,*args):
        self.samples.append((str(directory),n,pdb))
        return super().design(pdb,directory,n,*args)
    def fold(self,sequences,smiles,directory,args,pocket=None):
        import re, nesso_screen
        if self.nesso and sequences and all(re.fullmatch(r'c\d+_t\d+_n\d+_s\d+', n) for n in sequences):
            sequences=nesso_screen.screen(self,sequences,smiles,Path(directory).parent/'nesso')
        preds=super().fold(sequences,smiles,directory,args,pocket)
        for pred in preds.values(): pred.pbind=None; pred.ligand_plddt=50
        return preds
    def affinity(self,predictions,directory,args):
        result={}
        for name,pred in predictions.items():
            receipt=Path(directory)/name/'affinity_completed.json'
            saved=self.journal.load(receipt,{'name':name})
            if saved is None:
                if self.fail_affinity == self.affinity_calls or (self.fail_affinity == 'topup' and name == 'c01_t0_n0_s4'):
                    raise RuntimeError('affinity interrupted')
                self.affinity_calls += 1
                self.affinity_names.append(name)
                # Early first-round gate rejects L001; all other scores plateau.
                saved=.1 if name.startswith('L001_c1_') else .5
                self.journal.save(receipt,{'name':name},saved)
            result[name]=NS(**vars(pred));result[name].pbind=saved
        return result


class SearchPolicyIntegration(unittest.TestCase):
    def test_improvement_stops_only_that_trajectory_topups_and_cap_is_eight(self):
        class Improving(EfficientBackend):
            def affinity(self,predictions,directory,args):
                result=super().affinity(predictions,directory,args)
                for name,p in result.items():
                    if name.startswith('c') and '_t0_' in name:
                        p.pbind=.5+.02*int(name[1:3])
                return result
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); backend=Improving(root)
            args=fixtures.SearchTests().arguments(root)+['--selective-affinity',
                '--adaptive-proposals','--initial-proposals','3','--nise-seqs','12','--beam','3',
                '--max-cycles','8','--patience','10','--min-improvement','.01']
            with patch.object(science,'self_consistency',return_value=NS(ca_rmsd=.5,ligand_rmsd=.5,ok=True)):
                nise_run.main(args,backend=backend)
            self.assertTrue((root/'cycle08').is_dir())
            self.assertFalse((root/'cycle09').exists())
            first=json.loads((root/'cycle01/topup0003/proposal_round.json').read_text())
            next_round=json.loads((root/'cycle01/topup0006/proposal_round.json').read_text())
            self.assertEqual(first['needs_topup'],[1])
            self.assertEqual(set(next_round['parents']),{'1'})
            final=json.loads((root/'cycle08/advancement.json').read_text())
            self.assertEqual(final['trajectories'][0]['no_improve'],0)
            self.assertEqual(len(final['trajectories'][0]['last_improving_beam']),3)
            self.assertEqual(final['trajectories'][0]['best_node']['cycle'],8)

    def test_routes_topups_early_gate_geometry_patience_and_resume(self):
        import nesso_screen
        from nesso_contract import installation, SCALARS
        class ScoreClient:
            def __init__(self,*a):pass
            def close(self):pass
            def score(self,sequence,smiles,directory):
                values={**dict.fromkeys(SCALARS,0.0),'entropy_crop_pl':.2,'affinity_probability_binary':.8}
                atomic(directory/'affinity.json',values)
                return {'scores':values}
        for method in ('protein-hunter','rfdiffusion3'):
            for nesso in (False,True):
                with self.subTest(method=method,nesso=nesso), tempfile.TemporaryDirectory() as raw:
                    root=Path(raw)
                    install=installation(root);install.mkdir(parents=True);(install/'receipt.json').write_text('fixture')
                    args=fixtures.SearchTests().arguments(root)+['--backbone-method',method,'--num-starts','3',
                        '--selective-affinity','--early-score-gate','.8','--adaptive-proposals',
                        '--initial-proposals','3','--nise-seqs','12','--beam','3','--min-improvement','.01']
                    interrupted=EfficientBackend(root,nesso,fail_affinity=2)
                    with patch.object(nesso_screen,'NessoClient',ScoreClient), patch.object(science,'self_consistency',
                            return_value=NS(ca_rmsd=.5,ligand_rmsd=.5,ok=True)):
                        with self.assertRaisesRegex(RuntimeError,'affinity interrupted'):
                            nise_run.main(args,backend=interrupted)
                        interrupted_topup=EfficientBackend(root,nesso,fail_affinity='topup')
                        with self.assertRaisesRegex(RuntimeError,'affinity interrupted'):
                            nise_run.main(args,backend=interrupted_topup)
                        backend=EfficientBackend(root,nesso)
                        nise_run.main(args,backend=backend)
                        rows=list(__import__('csv').DictReader((root/'trajectory.csv').open()))
                        self.assertNotIn('L001',{r['origin'] for r in rows})
                        self.assertFalse(any('_c2_' in n and '_e' not in n for n in backend.affinity_names))
                        self.assertFalse(any(n.endswith('_s0') for n in backend.affinity_names))
                        summary=json.loads((root/'search_summary.json').read_text())
                        self.assertEqual(summary['n_trajectories'],2)
                        self.assertFalse((root/'cycle03').exists())
                        for cycle in (1,2):
                            rounds=[json.loads(p.read_text()) for p in sorted((root/f'cycle{cycle:02}').glob('topup*/proposal_round.json'))]
                            self.assertEqual([r['additional_proposals_per_parent'] for r in rounds],[3,3,6])
                            self.assertEqual(rounds[0]['parents'],rounds[-1]['parents'])
                            self.assertTrue(all(not r['rollback'] for r in rounds))
                        checkpoint=json.loads((root/'cycle02/advancement.json').read_text())
                        self.assertTrue(all(t['no_improve']==2 for t in checkpoint['trajectories']))
                        self.assertEqual([len(t['current_beam']) for t in checkpoint['trajectories']],[3,3])
                        before=(root/'trajectory.csv').read_bytes()
                        replay=EfficientBackend(root,nesso)
                        nise_run.main(args,backend=replay)
                        self.assertEqual((replay.design_calls,replay.fold_calls,replay.affinity_calls),(0,0,0))
                        self.assertEqual(before,(root/'trajectory.csv').read_bytes())


class SplitWorkerTests(unittest.TestCase):
    def test_resident_boltz_split_preserves_filters_and_skips_refolding(self):
        import resident_predictor as resident
        class Manifest:
            def __init__(self,records):self.records=records
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); source=root/'yaml';source.mkdir();(source/'one.yaml').write_text('fixture')
            output=root/'out'; result=output/'boltz_results_yaml'
            leaf=result/'predictions/one';leaf.mkdir(parents=True)
            counts={'structure':0,'affinity':0}; observed_seeds=[]
            main=NS(filter_inputs_structure=lambda manifest,**kw:manifest,
                    filter_inputs_affinity=lambda manifest,**kw:manifest)
            def predict(**kwargs):
                observed_seeds.append(kwargs['args'][kwargs['args'].index('--seed')+1])
                manifest=Manifest([NS(id='one',affinity=True)])
                if main.filter_inputs_structure(manifest=manifest,outdir=result,override=True).records:
                    counts['structure']+=1
                    (leaf/'one_model_0.pdb').write_text('saved structure')
                    (leaf/'confidence_one_model_0.json').write_text('{}')
                    (leaf/'pre_affinity_one.npz').write_bytes(b'full precision coordinates')
                if main.filter_inputs_affinity(manifest=manifest,outdir=result,override=True).records:
                    counts['affinity']+=1
                    (leaf/'affinity_one.json').write_text('{"affinity_probability_binary":0.9}')
            main.predict=NS(main=predict)
            session=resident.BoltzSession.__new__(resident.BoltzSession)
            session.config={}; session.arguments=['--seed','7']; session.request_seed=123; session.root=root; session.boltz_main=main
            original=(main.filter_inputs_structure,main.filter_inputs_affinity)
            with patch.object(resident,'validate_geometry'):
                session.request_phase='structure';session.predict(source,output,1)
                before=digest(leaf/'one_model_0.pdb')
                self.assertEqual(counts,{'structure':1,'affinity':0})
                session.request_phase='affinity';session.predict(source,output,1)
                self.assertEqual(counts,{'structure':1,'affinity':1})
                self.assertEqual(before,digest(leaf/'one_model_0.pdb'))
                self.assertEqual(original,(main.filter_inputs_structure,main.filter_inputs_affinity))
                self.assertEqual(observed_seeds,['123','123'])
                self.assertEqual(session.arguments,['--seed','7'])
                session.request_seed=None
                session.predict(source,output,1)
                self.assertEqual(observed_seeds[-1],'7')
                session.request_seed=True
                with self.assertRaisesRegex(RuntimeError,'invalid per-request'):
                    session.predict(source,output,1)
                session.request_seed=None
                (leaf/'pre_affinity_one.npz').unlink()
                with self.assertRaisesRegex(RuntimeError,'missing saved affinity structure'):
                    session.predict(source,output,1)
                self.assertEqual(original,(main.filter_inputs_structure,main.filter_inputs_affinity))

    def test_backend_split_receipts_replay_without_models_and_detect_tampering(self):
        import runtime
        class Worker:
            calls=[]; seeds=[]
            def __init__(self,*a): pass
            def close(self): pass
            def predict(self,source,out,affinity,phase='complete',prediction_seed=None):
                self.calls.append(phase); self.seeds.append(prediction_seed)
                leaf=out/'boltz_results_yaml/predictions/one';leaf.mkdir(parents=True,exist_ok=True)
                if phase=='structure':
                    (leaf/'one_model_0.pdb').write_text('fixture')
                    (leaf/'pre_affinity_one.npz').write_bytes(b'npz fixture')
                    (leaf/'confidence_one_model_0.json').write_text('{}')
                else:
                    (leaf/'affinity_one.json').write_text('{"affinity_probability_binary":0.9}')
                return {'phase':phase}
        def parse(out,name):
            leaf=out/'boltz_results_yaml/predictions/one'
            p=leaf/'affinity_one.json'
            return science.Prediction(name,str(leaf/'one_model_0.pdb'),ligand_plddt=95,
                pbind=json.loads(p.read_text())['affinity_probability_binary'] if p.exists() else None)
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw); backend=Backend(root,root,{'scheduler':'cycle-wave'},SCRIPTS)
            backend.ligand_manifest={}
            args=NS(seed=0,use_potentials=True,boltz_phase='structure',prediction_seeds={'one':123})
            with patch.object(runtime,'ResidentClient',Worker), patch.object(Backend,'audit_structure'), \
                 patch('ligand_atoms.audit_atoms'), patch.object(science,'parse_prediction',side_effect=parse):
                preds=backend.fold({'one':'AAA'},'CCO',root/'fold',args)
                self.assertIsNone(preds['one'].pbind)
                scored=backend.affinity(preds,root/'fold',args)
                self.assertEqual(scored['one'].pbind,.9)
                self.assertEqual(Worker.calls,['structure','affinity'])
                backend.close()
                preds=backend.fold({'one':'AAA'},'CCO',root/'fold',args)
                self.assertIsNone(preds['one'].pbind)
                backend.affinity(preds,root/'fold',args)
                self.assertEqual(Worker.calls,['structure','affinity'])
                self.assertIsNone(backend.worker)
                self.assertEqual(Worker.seeds,[123,123])
                args.prediction_seeds={'one':124}
                with self.assertRaisesRegex(RuntimeError,'inputs changed'):
                    backend.fold({'one':'AAA'},'CCO',root/'fold',args)
                args.prediction_seeds={'one':123}
                backend.write_summary({})
                cost=json.loads((root/'search_cost.json').read_text())
                self.assertEqual((cost['structure_evaluations'],cost['affinity_evaluations']),(1,1))
                (Path(preds['one'].pdb).parent/'pre_affinity_one.npz').write_bytes(b'changed')
                with self.assertRaisesRegex(RuntimeError,'missing or changed'):
                    backend.affinity(preds,root/'fold',args)


if __name__=='__main__':unittest.main(verbosity=2)
