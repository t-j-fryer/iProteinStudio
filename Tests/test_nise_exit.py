"""Geometry acceptance, chemical identity and shared-stage ordering contracts."""
import unittest
from pathlib import Path
import sys
from types import SimpleNamespace as NS
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'Sources/iProteinStudio/Resources/pipeline/scripts/nise')]
import biotin_exit, nise_run, contract, geometry_runtime

class ExitTests(unittest.TestCase):
    def test_chemical_roles_follow_graph_not_names(self):
        from rdkit import Chem
        m=Chem.MolFromSmiles(biotin_exit.REFERENCE)
        manifest=dict(smiles_used=biotin_exit.REFERENCE,atoms=[dict(index=a.GetIdx(),name='atom'+str(a.GetIdx())) for a in m.GetAtoms()])
        r=biotin_exit.roles(manifest)
        self.assertEqual(r['carbonyl'],'atom1');self.assertEqual(r['leaving'],'atom2')
        manifest['smiles_used']='CCO'
        with self.assertRaisesRegex(ValueError,'free-biotin'):biotin_exit.roles(manifest)

    def test_ambiguous_is_not_pass_and_no_rotational_rescue(self):
        for label,passed in [('open',True),('restricted',True),('unresolved',False),('blocked',False)]:
            with patch('linker_geometry.evaluate',return_value=dict(label=label,reason='fixture')) as evaluate, patch('linker_geometry.guarded',return_value=dict(broad_forward_exit=True)):
                r=biotin_exit.classify({})
                self.assertEqual(r['passed'],passed)
                self.assertFalse(r['rotation_rescue'])
                self.assertEqual(evaluate.call_count,1 if label=='open' else 2)

    def test_rmsd_failures_skip_exit_and_affinity_candidates(self):
        backend=NS(check_atom_requirements_batch=lambda preds:{k:k=='pass' for k in preds},record_candidate=lambda *args:None)
        seen=[]
        def check(preds):seen.extend(preds);return {k:k=='pass' for k in preds}
        backend.check_atom_requirements_batch=check
        preds={k:NS(pdb=k,ligand_plddt=90,pbind=None) for k in ['rmsd_fail','exit_fail','pass']}
        args=NS(backend=backend,selective_affinity=True,ligand_sasa_max=None)
        def sc(path,*a,**kw):return NS(ok=path!='rmsd_fail',ca_rmsd=0,ligand_rmsd=0)
        with patch.object(nise_run.L,'self_consistency',side_effect=sc):
            nodes=nise_run.evaluate_candidates(preds,{k:'AAA' for k in preds},{k:k for k in preds},args,1,2.5,2.5)
        self.assertEqual(seen,['exit_fail','pass']);self.assertEqual([n.name for n in nodes],['pass'])

    def test_legacy_defaults_and_exit_requires_selective_affinity(self):
        self.assertEqual(contract.normalize({'smiles':'CCO'})['exposure_mode'],'sasa')
        with self.assertRaisesRegex(ValueError,'geometry-before-affinity'):
            contract.normalize(dict(smiles=biotin_exit.REFERENCE,exposure_mode=biotin_exit.PROTOCOL,selective_affinity=False))

    def test_worker_bound_uses_cpu_and_memory(self):
        with patch.object(geometry_runtime,'_sysctl',side_effect=[12,64*1024**3]):
            self.assertEqual(geometry_runtime.worker_count(64),8)
        with patch.object(geometry_runtime,'_sysctl',side_effect=[4,8*1024**3]):
            self.assertEqual(geometry_runtime.worker_count(),2)

if __name__=='__main__':unittest.main()
