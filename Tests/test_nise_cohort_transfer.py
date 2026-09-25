"""Portable cohort corruption, relocation, molecule and search-boundary tests."""
import io, json, pickle, shutil, sys, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
SCRIPTS=ROOT/'Sources/iProteinStudio/Resources/pipeline/scripts'
sys.path[:0]=[str(SCRIPTS/'nise'),str(SCRIPTS),str(ROOT/'Tests')]
import cohort_transfer as C
from runtime import Journal, atomic

class TransferTests(unittest.TestCase):
    def fixture(self, root):
        from rdkit import Chem
        import numpy as np
        import contract
        root.mkdir();req=contract.normalize(dict(smiles='C',hotspot_atoms=['C1'],ligand_atom_signature='0'*64,ligand_atoms_generated_for='C'))
        atomic(root/'nise_config.json',dict(request=req));atomic(root/'ligand_atom_map.json',dict(atoms=[dict(name='C1',el='C')],smiles_used='C'))
        (root/'ligand.yaml').write_text('version: 1\n')
        journal=Journal(root)
        for i in range(3):
            name=f'L000_c1_{i}';unit=root/'phase0/cycle01/fold'/name;pred=unit/'out/boltz_results_yaml/predictions'/name
            pred.mkdir(parents=True);pdb=pred/f'{name}_model_0.pdb'
            lines=[]
            for j,(an,element) in enumerate([('N','N'),('CA','C'),('C','C'),('O','O')],1):
                lines.append(f'ATOM  {j:5d} {an:^4} ALA A   1    {float(j):8.3f}{0.:8.3f}{0.:8.3f}  1.00 90.00          {element:>2}  ')
            lines.append(f'HETATM{5:5d} {"C1":^4} LIG B   1    {0.:8.3f}{1.:8.3f}{0.:8.3f}  1.00 90.00           C  ')
            pdb.write_text('\n'.join(lines)+'\n')
            ref=root/'phase0/cycle00/L000_ref.pdb';ref.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(pdb,ref)
            np.savez(pred/f'pre_affinity_{name}.npz',x=np.zeros((1,3)), pocket=np.array(None, dtype=object))
            processed=unit/'out/boltz_results_yaml/processed';molpath=processed/f'mols/{name}.pkl';molpath.parent.mkdir(parents=True)
            mol=Chem.MolFromSmiles('C');conf=Chem.Conformer(1);conf.SetAtomPosition(0,(0,1,0));mol.AddConformer(conf);mol.GetAtomWithIdx(0).SetProp('name','C1')
            molpath.write_bytes(pickle.dumps({'LIG1':mol}))
            y=unit/f'yaml/{name}.yaml';y.parent.mkdir();y.write_text('version: 1\n')
            spec=dict(sequence='A',smiles='C',phase='structure',seed=0,affinity=True,potentials=True,pocket=dict(binder='A',contacts=[['B','C1']],force=True,max_distance=6.0))
            journal.save(unit/'completed.json',spec,dict(prediction=dict(name=name,pdb=str(pdb),ligand_plddt=90.,pbind=None)),[pdb,pred/f'pre_affinity_{name}.npz',molpath,y])
            atomic(root/f'candidates/{name}.json',dict(name=name,sequence='A',pdb=str(pdb),ref_pdb=str(ref),geometry_passed=i<2,atom_checks={'passed':i<2},ca_rmsd=.5,ligand_rmsd=.6,passed=False,score=.01,pbind=.001))
        return req

    def test_exact_geometry_cohort_no_affinity_bias_relocation_replay_and_tamper(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);self.fixture(base/'source');d=C.export(base/'source',base/'package')
            self.assertEqual((d['candidate_count'],d['lineage_count']),(2,1))
            self.assertTrue(all(x['operation']['result']['prediction']['pbind'] is None for x in d['candidates']))
            output=base/'relocated';output.mkdir();shutil.copytree(base/'package',output/'cohort')
            cfg=dict(request={**d['request'],'trajectories':1},cohort=dict(path='cohort',sha256=C.sha(output/'cohort/cohort.json')))
            C.materialize(output,cfg)
            import numpy as np
            cache=next(output.glob('phase0/cycle01/fold/*/out/boltz_results_yaml/predictions/*/pre_affinity*.npz'))
            with np.load(cache,allow_pickle=True) as arrays:
                self.assertIsNone(arrays['pocket'].item())
                np.testing.assert_array_equal(arrays['x'],np.zeros((1,3)))
            receipts=list(output.glob('phase0/cycle01/fold/*/completed.json'));before=[p.read_bytes() for p in receipts]
            C.materialize(output,cfg);self.assertEqual(before,[p.read_bytes() for p in receipts])
            from rdkit import Chem
            src=base/'source/phase0/cycle01/fold/L000_c1_0/out/boltz_results_yaml/processed/mols/L000_c1_0.pkl'
            dst=output/src.relative_to(base/'source');m=C.MoleculeOnlyUnpickler(io.BytesIO(src.read_bytes())).load()['LIG1'];n=C.MoleculeOnlyUnpickler(io.BytesIO(dst.read_bytes())).load()['LIG1']
            self.assertEqual(m.ToBinary(Chem.PropertyPickleOptions.AllProps),n.ToBinary(Chem.PropertyPickleOptions.AllProps))
            pdb=next(output.glob('phase0/cycle01/fold/*/out/boltz_results_yaml/predictions/*/*.pdb'));pdb.write_text('changed')
            with self.assertRaisesRegex(RuntimeError,'changed'):C.materialize(output,cfg)
            with self.assertRaisesRegex(ValueError,'ligand/geometry'):C.validate(output/'cohort',{**cfg['request'],'smiles':'CC'})

    def test_paths_and_pickle_code_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            for rel in ('../escape','/tmp/escape','a/../../escape','a\\b'):
                with self.assertRaises(ValueError):C.safe(p,rel)
            (p/'link').symlink_to('/tmp')
            with self.assertRaises(ValueError):C.safe(p,'link/file')
            (p/'bad.pkl').write_bytes(pickle.dumps(eval))
            with self.assertRaisesRegex(ValueError,'Unsupported object'):C.molecule_json(p/'bad.pkl')
            import numpy as np
            np.savez(p/'bad.npz',pocket=np.array(eval,dtype=object))
            with self.assertRaisesRegex(ValueError,'Object arrays'):
                C.restore_npz(p/'bad.npz',p/'restored.npz')

    def test_corrupt_package_duplicate_or_affinity_state_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);self.fixture(p/'source');d=C.export(p/'source',p/'package')
            name=d['candidates'][0]['operation']['result']['prediction']['pdb'];(p/'package'/name).write_text('bad')
            with self.assertRaisesRegex(ValueError,'changed'):C.validate(p/'package')

class BrokerCohortTests(unittest.TestCase):
    def test_both_screeners_bind_all_assets_and_use_cached_stage_route(self):
        from unittest.mock import Mock
        sys.path.insert(0,str(ROOT/'Sources/iProteinStudio/Resources/pipeline/mcp'))
        from iprotein_mcp.desktop import desktop_plan
        import contract
        with tempfile.TemporaryDirectory() as td:
            root=Path(td).resolve();source=root/'source';TransferTests().fixture(source)
            output=root/'projects/demo/nise_runs/imported';output.mkdir(parents=True)
            data=C.export(source,output/'cohort')
            snapshot=output/'.studio_runtime/pipeline/scripts/nise';snapshot.mkdir(parents=True)
            for name in ('cohort_transfer.py','campaign.py','contract.py'):
                shutil.copyfile(SCRIPTS/'nise'/name,snapshot/name)
            stub=Mock();stub.saved_request.side_effect=contract.saved_request
            stub.preflight.side_effect=lambda root,request: request
            stub.required_files.return_value=[];stub.prediction_budget.return_value={}
            for engine in ('nesso','psichic'):
                request={**data['request'],'trajectories':1,'screening_engine':engine}
                C.write(output/'nise_config.json',dict(output=str(output),request=request,
                    cohort=dict(path='cohort',sha256=C.sha(output/'cohort/cohort.json'))))
                with patch('iprotein_mcp.desktop.runtime_root',return_value=root), \
                     patch('iprotein_mcp.desktop.project_root',return_value=root/'projects/demo'), \
                     patch('iprotein_mcp.nise.contract',return_value=stub), \
                     patch('iprotein_mcp.desktop._persist') as persist:
                    desktop_plan(dict(project='demo',workflow='nise',output=str(output)))
                    args=persist.call_args.args
                    self.assertIn('--stage-batches',args[2]['steps'][0]['command'])
                    self.assertEqual(args[2]['request']['screening_engine'],engine)
                    self.assertEqual(args[2]['imported_cohort']['candidates'],2)
                    frozen={item['path'] for item in args[5]}
                    self.assertTrue({str(output/'cohort'/p) for p in data['files']}<=frozen)
                    self.assertIn(str(output/'cohort/cohort.json'),frozen)


class SearchBoundaryTests(unittest.TestCase):
    def test_import_screens_full_cohort_skips_generation_preserves_lineages_and_replays(self):
        from test_nise_search_policy import EfficientBackend
        from test_nise_science import SearchTests
        import nise_run, nise_lib
        class Imported(EfficientBackend):
            def __init__(self,root):
                super().__init__(root);self.screened=[]
                self.imported_candidates=[dict(name=f'L{t:03d}_c1_{i}',origin=f'L{t:03d}',sequence='A'*65,ref_pdb=f'parent{t}.pdb') for t in (0,2) for i in range(2)]
            def screen_initial(self,sequences,smiles,directory,owners,stage):
                self.screened.append((str(directory),dict(sequences),dict(owners)))
                # Deterministic scorer boundary: keep one per source lineage.
                names={}
                for n in sorted(sequences):names.setdefault(owners[n],n)
                return {n:sequences[n] for n in names.values()}
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);b=Imported(root)
            args=SearchTests().arguments(root)+['--selective-affinity','--phase0-refine-cycles','2','--max-cycles','1']
            with patch.object(nise_lib,'self_consistency',return_value=NS(ca_rmsd=.5,ligand_rmsd=.5,ok=True)):
                nise_run.main(args,backend=b)
                self.assertEqual(len(b.screened[0][1]),4)
                self.assertEqual(set(b.screened[0][2].values()),{'L000','L002'})
                self.assertFalse((root/'phase0/cycle00').exists())
                self.assertFalse((root/'phase0/cycle01/design').exists())
                self.assertTrue((root/'phase0/cycle02/design').exists())
                self.assertEqual(json.loads((root/'search_summary.json').read_text())['n_trajectories'],2)
                replay=Imported(root);nise_run.main(args,backend=replay)
                self.assertEqual((replay.design_calls,replay.fold_calls,replay.affinity_calls),(0,0,0))

if __name__=='__main__':unittest.main()
