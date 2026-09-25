"""Execute optional masking/repair search paths with deterministic model fixtures."""
import csv
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'Sources/iProteinStudio/Resources/pipeline/scripts/nise'), str(ROOT/'Tests')]
os.environ.setdefault('NANOHUNTER_ROOT', str(ROOT))
import contract
import partial_noising as noise
import nise_run
import nise_lib as science
from runtime import Backend, Journal, atomic
from test_nise_search_policy import EfficientBackend
import test_nise_science as fixtures


def pocket_pdb(path):
    import gemmi
    structure=gemmi.Structure(); model=gemmi.Model('1')
    for chain_id, rows in [('A',[(10,'ALA',[('CA',9,'C'),('CB',4,'C')]),
                               (20,'ALA',[('CA',6,'C')]),(30,'ALA',[('CA',20,'C'),('H',1,'H')])]),
                           ('B',[(1,'LIG',[('C1',0,'C'),('H1',20,'H')])])]:
        chain=gemmi.Chain(chain_id)
        for number,name,atoms in rows:
            residue=gemmi.Residue();residue.name=name;residue.seqid=gemmi.SeqId(number,' ')
            for atom_name,x,element in atoms:
                atom=gemmi.Atom();atom.name=atom_name;atom.element=gemmi.Element(element);atom.pos=gemmi.Position(x,0,0)
                residue.add_atom(atom)
            chain.add_residue(residue)
        model.add_chain(chain)
    structure.add_model(model); structure.write_pdb(str(path))


class PartialNoisingTests(unittest.TestCase):
    def test_defaults_budgets_legacy_migration_and_invalid_settings(self):
        cfg=contract.normalize({'smiles':'CCO'})
        self.assertEqual((cfg['nise_seqs'],cfg['first_cycle_seqs'],cfg['beam']),(32,64,3))
        self.assertFalse(cfg['partial_noising'])
        budget=contract.prediction_budget(cfg)
        self.assertEqual((budget['first_cycle_boltz_max'],budget['later_cycle_boltz_max']),(8*64,8*96))
        cfg['partial_noising']=True
        budget=contract.prediction_budget(cfg)
        self.assertEqual((budget['first_cycle_boltz_max'],budget['later_cycle_boltz_max']),(8*64,8*128))
        cfg['nesso_screen']=True
        budget=contract.prediction_budget(cfg)
        self.assertEqual((budget['first_cycle_boltz_max'],budget['later_cycle_boltz_max']),(8*16,8*(16+32+16)))
        for version in (1,2):
            old=contract.normalize(dict(smiles='CCO',search_policy_version=version,nise_seqs=17))
            self.assertEqual(old['first_cycle_seqs'],17);self.assertFalse(old['partial_noising'])
        for changes in ({'noise_percent':float('nan')},{'noise_radius':0},{'noise_advance':3},
                        {'noise_predictions':True},{'adaptive_proposals':True},{'first_cycle_seqs':2}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                contract.normalize({**cfg,**changes})

    def test_heavy_atom_distance_exact_sequence_positions_and_mask_replay(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);pdb=root/'parent.pdb';pocket_pdb(pdb)
            positions,labels=noise.pocket_positions(pdb,'AAA',6)
            self.assertEqual(positions,[0,1]);self.assertEqual(labels,['10','20','30'])
            self.assertEqual(noise.pocket_positions(pdb,'AAA',3)[0],[])
            with self.assertRaisesRegex(ValueError,'sequence'):
                noise.pocket_positions(pdb,'AGA',6)
            backend=NS(journal=Journal(root));parent=NS(name='parent',sequence='AAA',pdb=str(pdb))
            args=NS(noise_radius=6,noise_percent=50,noise_predictions=32,seed=42)
            result=noise.mask_proposals(backend,parent,root/'branch',args,2,0)
            self.assertEqual(len(result['proposals']),32)
            self.assertEqual(len({r['seed'] for r in result['proposals']}),32)
            self.assertTrue(all(p['sequence'].count('X')==1 and p['sequence'][2]=='A' for p in result['proposals']))
            with patch.object(noise,'pocket_positions',side_effect=AssertionError('must reuse masks')):
                self.assertEqual(noise.mask_proposals(backend,parent,root/'branch',args,2,0),result)
            pdb.write_text(pdb.read_text()+'REMARK changed\n')
            with self.assertRaisesRegex(RuntimeError,'inputs changed'):
                noise.mask_proposals(backend,parent,root/'branch',args,2,0)

    def test_patch_only_binder_unknowns_and_immutable_preparation(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);source=root/'source.pdb';pocket_pdb(source)
            source.write_text(source.read_text().replace('ALA','UNK').replace('LIG','UNK'))
            original=source.read_bytes();backend=NS(journal=Journal(root))
            target=root/'repair.pdb';noise.repair_input(backend,source,target)
            atomlines=[l for l in target.read_text().splitlines() if l.startswith(('ATOM  ','HETATM'))]
            self.assertTrue(all(l[17:20]=='ALA' for l in atomlines if l[21]=='A'))
            self.assertTrue(all(l[17:20]=='UNK' for l in atomlines if l[21]=='B'))
            self.assertEqual(source.read_bytes(),original)
            target.write_text('tampered')
            with self.assertRaisesRegex(RuntimeError,'artifact'):
                noise.repair_input(backend,source,target)

    def test_masked_intermediates_cannot_enter_apo_shortlist(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw)
            atomic(root/'candidates/masked.json',dict(name='masked',branch='masked-backbone',
                   sequence='AXA',trajectory=0,passed=True,score=1.99))
            backend=NS(output=root,settings={'top_x':8},close=lambda:None)
            Backend.preorganisation(backend,NS())
            self.assertEqual(json.loads((root/'preorg.json').read_text())['shortlist'],[])

    def test_disabled_field_migration_freezes_old_configuration_unchanged(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);prior=dict(nise_seqs=17)
            atomic(root/'config.json',prior)
            backend=NS(output=root,settings={'search_policy_version':2},allow_boltz_affinity=True)
            cfg=dict(prior,first_cycle_seqs=17,partial_noising=False,noise_radius=6.0,
                     noise_percent=25.0,noise_predictions=32,noise_mpnn_seqs=32,noise_advance=1)
            Backend.freeze_config(backend,cfg)
            self.assertEqual(json.loads((root/'config.json').read_text()),prior)
            with self.assertRaisesRegex(RuntimeError,'settings differ'):
                Backend.freeze_config(backend,{**cfg,'partial_noising':True})

    def test_routes_reserved_beams_interruption_and_no_new_work_replay(self):
        import nesso_screen
        from nesso_contract import installation,SCALARS
        class Scorer:
            def __init__(self,*a):pass
            def close(self):pass
            def score(self,sequence,smiles,directory):
                if 'X' in sequence:raise AssertionError('NESSO must not score masked sequences')
                values={**dict.fromkeys(SCALARS,0.0),'entropy_crop_pl':.2,'affinity_probability_binary':.8}
                atomic(directory/'affinity.json',values);return {'scores':values}
        class Fixture(EfficientBackend):
            def __init__(self,root,nesso=False,interrupt=False,reject=False):
                super().__init__(root,nesso);self.interrupt=interrupt;self.reject=reject
                self.settings.update(partial_noising=True,noise_advance=1)
                self.mask_batches=[]
            def check_atom_requirements(self,pred):
                return False if self.reject and ('_mask_' in pred.name or '_n999_' in pred.name) else super().check_atom_requirements(pred)
            def affinity(self,predictions,directory,args):
                result=super().affinity(predictions,directory,args)
                for name,pred in result.items():
                    if '_mask_' in name: pred.pbind=.99
                    elif '_n999_' in name: pred.pbind=.9 if self.nesso else .3
                return result
            def fold(self,seqs,smiles,directory,args,pocket=None):
                if any('_mask_' in n for n in seqs):
                    self.mask_batches.append(dict(args.prediction_seeds))
                    assert args.skip_nesso
                if self.interrupt and 'repair/fold' in str(directory):
                    raise RuntimeError('interrupted after masked backbone selection')
                return super().fold(seqs,smiles,directory,args,pocket)
        for method in ('protein-hunter','rfdiffusion3'):
            for nesso in (False,True):
                with self.subTest(method=method,nesso=nesso),tempfile.TemporaryDirectory() as raw:
                    root=Path(raw);install=installation(root);install.mkdir(parents=True);(install/'receipt.json').write_text('fixture')
                    args=fixtures.SearchTests().arguments(root)+['--backbone-method',method,'--num-starts','3',
                        '--first-cycle-seqs','4','--nise-seqs','3','--beam','3','--partial-noising',
                        '--noise-predictions','2','--noise-mpnn-seqs','3','--selective-affinity','--patience','4']
                    with patch.object(noise,'pocket_positions',return_value=([0,1,2,3],[str(i+1) for i in range(65)])),\
                         patch.object(science,'self_consistency',return_value=NS(ca_rmsd=.5,ligand_rmsd=.5,ok=True)),\
                         patch.object(nesso_screen,'NessoClient',Scorer):
                        first=Fixture(root,nesso,interrupt=True)
                        with self.assertRaisesRegex(RuntimeError,'interrupted after masked'):
                            nise_run.main(args,backend=first)
                        backend=Fixture(root,nesso);nise_run.main(args,backend=backend)
                        first_cycle=json.loads((root/'cycle01/proposal_round.json').read_text())
                        second_cycle=json.loads((root/'cycle02/proposal_round.json').read_text())
                        self.assertEqual(first_cycle['sampled'],2*4)
                        self.assertEqual(second_cycle['sampled'],2*2*3)
                        for cycle in (2,3):
                            proposals=json.loads((root/f'cycle{cycle:02}/proposal_round.json').read_text())
                            previous=json.loads((root/f'cycle{cycle-1:02}/advancement.json').read_text())
                            self.assertEqual(proposals['sampled'],2*2*3)
                            for t in previous['trajectories']:
                                expected=sorted(t['current_beam'],key=lambda n:(-n['score'],n['name']))[:2]
                                self.assertEqual([p['name'] for p in proposals['parents'][str(t['trajectory'])]],
                                                 [p['name'] for p in expected])
                                if cycle == 3:
                                    self.assertEqual(any(p['branch']=='partial-noising-repair' for p in expected),nesso)
                        self.assertFalse((root/'cycle01/partial_noising').exists())
                        for cycle in (2,3):
                            checkpoint=json.loads((root/f'cycle{cycle:02}/advancement.json').read_text())
                            for t in checkpoint['trajectories']:
                                branches=[n['branch'] for n in t['current_beam']]
                                self.assertEqual(branches.count('partial-noising-repair'),1)
                                self.assertEqual(branches.count('mpnn'),2)
                                self.assertNotIn('X',t['best_node']['sequence'])
                        masked=[json.loads(p.read_text()) for p in (root/'candidates').glob('*_mask_*')]
                        self.assertTrue(masked);self.assertTrue(all(not r['passed'] and not r['final_eligible'] for r in masked))
                        before=(root/'trajectory.csv').read_bytes()
                        replay=Fixture(root,nesso);nise_run.main(args,backend=replay)
                        self.assertEqual((replay.design_calls,replay.fold_calls,replay.affinity_calls),(0,0,0))
                        self.assertEqual(before,(root/'trajectory.csv').read_bytes())
                        if nesso:
                            with (root/'nesso_screening.csv').open() as f:rows=list(csv.DictReader(f))
                            self.assertTrue(any(r['stage']=='partial-noising-repair' for r in rows))
        # All masks can legitimately fail: retain normal winners, leave reserved slot empty.
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);args=fixtures.SearchTests().arguments(root)+['--beam','3','--first-cycle-seqs','4',
                '--nise-seqs','3','--partial-noising','--noise-predictions','2','--noise-mpnn-seqs','3','--selective-affinity']
            with patch.object(noise,'pocket_positions',return_value=([0,1],[str(i+1) for i in range(65)])),\
                 patch.object(science,'self_consistency',return_value=NS(ca_rmsd=.5,ligand_rmsd=.5,ok=True)):
                nise_run.main(args,backend=Fixture(root,reject=True))
            checkpoint=json.loads((root/'cycle02/advancement.json').read_text())
            self.assertTrue(all(len(t['current_beam'])==2 for t in checkpoint['trajectories']))

if __name__=='__main__':unittest.main()
