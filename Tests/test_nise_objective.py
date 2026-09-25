"""Execute scorer-objective selection, geometry exclusion and durable replay; no models."""
import csv,json,re,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
SCRIPTS=ROOT/'Sources/iProteinStudio/Resources/pipeline/scripts'
sys.path[:0]=[str(SCRIPTS/'nise'),str(SCRIPTS),str(ROOT/'Tests')]
import contract,nise_run,nise_lib,nesso_screen,psichic_screen,psichic_contract
from runtime import Backend,atomic
from batch_runtime import BatchBackend,PoolBackend
from test_nise_search_policy import EfficientBackend
from test_nise_science import FixtureBackend
import test_nise_science as fixtures
from nesso_contract import SCALARS,installation

class Scorer:
    calls=0
    def __init__(self,*args):pass
    def close(self):pass
    def score(self,sequence,smiles,directory):
        directory=Path(directory);name=directory.name
        type(self).calls+=1
        probability=.7
        if name.startswith('L001'):probability=.1
        if '_t' in name:
            k=int(name.rsplit('_s',1)[1]);probability={0:.99,1:.85,2:.6}[k%3]
        values={**dict.fromkeys(SCALARS,0.),'entropy_crop_pl':.2,'affinity_probability_binary':probability}
        atomic(directory/'affinity.json',values)
        return {'scores':values}
    def score_many(self,items,smiles):
        results=[]
        for item in items:
            v=self.score(item['sequence'],smiles,item['directory'])['scores']['affinity_probability_binary']
            values=dict(predicted_binding_affinity=5.,predicted_nonbinder=1-v,predicted_agonist=v/2,predicted_antagonist=v/2)
            atomic(Path(item['directory'])/'affinity.json',values);results.append({'scores':values})
        return results

class ObjectiveBackend(EfficientBackend):
    objective_score=Backend.objective_score
    freeze_config=Backend.freeze_config
    write_summary=Backend.write_summary
    def __init__(self,root,engine,fail_after=None):
        super().__init__(root)
        self.settings=contract.normalize(dict(smiles='CCO',scoring_mode='screening',screening_engine=engine,
            phase0_nesso_screen=True,nesso_screen=True,nesso_top_k=3,nise_seqs=3,first_cycle_seqs=3,
            phase0_nesso_refine_top_k=1,phase0_nesso_expand_top_k=3,trajectories=2,beam=2,
            nesso_early_score_gate=1.2,psichic_early_score_gate=.5))
        self.objective=contract.objective(self.settings);self.fail_after=fail_after
        self.screened=[]
    def fold(self,sequences,smiles,directory,args,pocket=None):
        assert args.boltz_phase=='structure'
        if sequences and all(re.fullmatch(r'c\d+_t\d+_n\d+_s\d+',n) for n in sequences):
            sequences=nesso_screen.screen(self,sequences,smiles,Path(directory).parent/'nesso')
        result=FixtureBackend.fold(self,sequences,smiles,directory,args,pocket)
        for n,p in result.items():
            p.pbind=None
            # Boltz confidence would prefer s2; the objective must choose s1.
            p.ligand_plddt=99 if n.endswith('_s2') else 20
        return result
    def affinity(self,*args,**kwargs):raise AssertionError('Affinity head must never execute')
    def write_atom_report(self):pass

class ObjectiveTests(unittest.TestCase):
    def test_contract_independent_gates_and_invalid_combinations(self):
        self.assertEqual(contract.normalize({'smiles':'CCO'})['scoring_mode'],'boltz')
        valid=dict(smiles='CCO',scoring_mode='screening',nesso_screen=True,phase0_nesso_screen=True)
        for engine,maximum in [('nesso',2),('psichic',1)]:
            cfg=contract.normalize({**valid,'screening_engine':engine})
            self.assertEqual(contract.objective(cfg)['early_gate'],.4 if engine=='nesso' else .2)
            old=contract.normalize(contract.saved_request({**valid,'screening_engine':engine,'search_policy_version':3}))
            self.assertEqual(contract.objective(old)['early_gate'],0)
            explicit=contract.normalize({**valid,'screening_engine':engine,engine+'_early_score_gate':0})
            self.assertEqual(contract.objective(explicit)['early_gate'],0)
            self.assertEqual(contract.objective(cfg)['maximum'],maximum)
        for changes in [dict(nesso_screen=False),dict(phase0_nesso_screen=False),dict(selective_affinity=False),dict(partial_noising=True),dict(psichic_early_score_gate=1.1),dict(nesso_early_score_gate=float('nan')),dict(search_policy_version=1)]:
            with self.assertRaises(ValueError):contract.normalize({**valid,**changes})

    def test_true_objective_both_engines_generators_interruption_and_replay(self):
        for engine in ('nesso','psichic'):
            for generator in ('protein-hunter','rfdiffusion3','imported'):
                with self.subTest(engine=engine,generator=generator), tempfile.TemporaryDirectory() as td:
                    root=Path(td);base=installation(root);base.mkdir(parents=True);(base/'receipt.json').write_text('{}')
                    (root/'runtime.json').write_text('{}')
                    args=fixtures.SearchTests().arguments(root)+['--selective-affinity','--num-starts','3','--phase0-refine-cycles','2',
                        '--phase0-seqs1','3','--nise-seqs','3','--first-cycle-seqs','3','--beam','2','--max-cycles','4',
                        '--patience','2','--min-improvement','0.01','--backbone-method','protein-hunter' if generator=='imported' else generator]
                    def backend(fail_after=None):
                        result=ObjectiveBackend(root,engine,fail_after=fail_after)
                        if generator=='imported':
                            result.imported_candidates=[dict(name=f'L{i:03}_c1_{k}',origin=f'L{i:03}',sequence='A'*65,ref_pdb=f'phase0/cycle00/L{i:03}_ref.pdb') for i in range(3) for k in range(3)]
                        return result
                    with patch.object(nesso_screen,'NessoClient',Scorer), patch.object(psichic_screen,'PsichicClient',Scorer), \
                         patch.object(psichic_contract,'installation',return_value=root), \
                         patch.object(nise_lib,'self_consistency',return_value=NS(ca_rmsd=.5,ligand_rmsd=.5,ok=True)):
                        # Interrupt inside cycle01 after structure work has begun.
                        with self.assertRaisesRegex(RuntimeError,'interruption'):
                            nise_run.main(args,backend=backend(fail_after=4))
                        run=backend();nise_run.main(args,backend=run)
                        summary=json.loads((root/'search_summary.json').read_text())
                        self.assertEqual(summary['objective']['engine'],engine)
                        self.assertEqual(summary['evaluation_cost']['affinity_evaluations'],0)
                        self.assertIsNone(summary['best_pbind'])
                        self.assertAlmostEqual(summary['best_score'],1.65 if engine=='nesso' else .85)
                        self.assertTrue((root/'cycle03/advancement.json').is_file())
                        self.assertFalse((root/'cycle04/advancement.json').is_file())
                        with (root/'trajectory.csv').open() as stream: rows=list(csv.DictReader(stream))
                        initial=[r for r in rows if r['phase']=='phase0.c1']
                        self.assertEqual({r['origin'] for r in initial},{'L000','L002'})
                        candidates=[json.loads(p.read_text()) for p in (root/'candidates').glob('c01*.json')]
                        self.assertTrue(any(not c['geometry_passed'] and c['name'].endswith('_s0') for c in candidates))
                        advancement=json.loads((root/'cycle01/advancement.json').read_text())
                        self.assertTrue(all(t['current_beam'][0]['name'].endswith('_s1') for t in advancement['trajectories']))
                        self.assertTrue(all(t['current_beam'][0]['score_engine']==engine for t in advancement['trajectories']))
                        self.assertTrue(all(r['score_engine']==engine for r in rows))
                        self.assertTrue(all(r['pbind']=='' for r in rows))
                        before=(root/'trajectory.csv').read_bytes();calls=Scorer.calls
                        replay=backend();nise_run.main(args,backend=replay)
                        self.assertEqual((root/'trajectory.csv').read_bytes(),before)
                        self.assertEqual((replay.fold_calls,replay.design_calls,Scorer.calls-calls),(0,0,0))
                        # An objective change cannot silently reuse search state.
                        with self.assertRaisesRegex(RuntimeError,'settings differ'):
                            other=backend();other.objective={**other.objective,'early_gate':.123};nise_run.main(args,backend=other)

    def test_native_backends_refuse_affinity_and_missing_objective(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);settings=dict(scoring_mode='screening',screening_engine='nesso',scheduler='resident')
            for cls in (Backend,BatchBackend):
                b=cls(root,root,settings,SCRIPTS)
                self.assertFalse(b.allow_boltz_affinity)
                with self.assertRaisesRegex(RuntimeError,'disabled'):b.affinity({},root,NS())
                with self.assertRaisesRegex(RuntimeError,'Missing saved'):b.objective_score('missing')
                with self.assertRaisesRegex(RuntimeError,'structure-only'):b.fold({},'CCO',root,NS())
            captured=[]
            class Worker:
                def __init__(self,*args,**kwargs):captured.append(args)
                def close(self):pass
            with patch('batch_runtime.BatchClient',Worker):
                batch=BatchBackend(root,root,settings,SCRIPTS)
                batch._worker(NS(seed=0,use_potentials=True))
                self.assertIs(captured[0][-1],False)
                pool=PoolBackend(root,root,settings,SCRIPTS,workers=2)
                with patch.object(pool,'_execute_batch') as execute:
                    pool._execute(root,{'a':{'sequence':'AAA'},'b':{'sequence':'AAAA'}},NS(seed=0,use_potentials=True),'structure',False,lambda _:None)
                    self.assertEqual(execute.call_count,2)
                    self.assertTrue(all(args[-1] is False for args in captured))
                pool.close()

if __name__=='__main__':unittest.main()
