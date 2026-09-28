import tempfile
import unittest
from pathlib import Path
import numpy as np
from common import align,pdb_audit,atomic,sha,verify_inventory

class AuditTests(unittest.TestCase):
    def test_target_fit_preserves_binder_displacement(self):
        from analyse import pose
        rng=np.random.default_rng(9)
        a=rng.normal(size=(98,3)); b=rng.normal(size=(96,3))
        ref={'A':{'ca':a.tolist()},'B':{'ca':b.tolist()}}
        moved={'A':{'ca':(a+np.array([2,0,0])).tolist()},'B':{'ca':b.tolist()}}
        result=pose(ref,moved)
        self.assertAlmostEqual(result['binder_ca_rmsd_after_sumo_core_fit'],2.0)
        self.assertLess(result['binder_own_ca_rmsd'],1e-12)
        self.assertLess(result['sumo_core_ca_rmsd'],1e-12)
    def test_rigid_motion_and_reflection(self):
        x=np.array([[0,0,0],[2,0,0],[0,3,0],[0,0,4]],float)
        r=np.array([[0,-1,0],[1,0,0],[0,0,1]])
        self.assertLess(align(x,x@r+7),1e-12)
        self.assertGreater(align(x,x*np.array([-1,1,1])),0.1)
    def test_nonfinite_rejected(self):
        with self.assertRaises(ValueError):align(np.eye(3),np.eye(3)*np.nan)
    def test_inventory_detects_changed_input(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'record.json';atomic(p,{'value':1});entries=[{'path':str(p),'sha256':sha(p)}]
            verify_inventory(entries);atomic(p,{'value':2})
            with self.assertRaises(RuntimeError):verify_inventory(entries)
    def test_sequence_and_backbone_required(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.pdb'; lines=[];serial=1
            for res in range(1,4):
                for atom,delta in [('N',-1),('CA',0),('C',1)]:
                    lines.append(f'ATOM  {serial:5d} {atom:^4s} ALA A{res:4d}    {(res-1)*3.8+delta:8.3f}{0.:8.3f}{0.:8.3f}  1.00 80.00           C')
                    serial+=1
            p.write_text('\n'.join(lines)+'\n')
            self.assertEqual(pdb_audit(p,'AAA')['ca_breaks'],0)
            with self.assertRaises(ValueError):pdb_audit(p,'AGA')
            p.write_text('\n'.join(line for line in lines if line[12:16].strip()!='N'))
            with self.assertRaises(ValueError):pdb_audit(p,'AAA')

if __name__=='__main__':unittest.main()
