"""Owned-process identity and reparenting checks without signalling real jobs."""
import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'Sources/iProteinStudio/Resources/pipeline/mcp'))
from iprotein_mcp.process_tree import ProcessTree

def row(parent,group,born,state='S'):
    return dict(parent=parent,group=group,born=born,state=state)

class Tests(unittest.TestCase):
    def test_reparented_separate_group_is_retained_but_unrelated_process_is_not(self):
        rows={10:row(1,10,'leader'),11:row(10,11,'child'),40:row(1,40,'unrelated')}
        with patch('iprotein_mcp.process_tree.snapshot',side_effect=lambda:dict(rows)):
            family=ProcessTree(10)
            rows[11]['parent']=1;del rows[10]
            family.refresh(force=True)
            self.assertEqual(set(family.alive()),{11})
            with patch('iprotein_mcp.process_tree.os.kill') as kill:
                family.send(15);kill.assert_called_once_with(11,15)

    def test_reused_pid_is_not_signalled(self):
        rows={10:row(1,10,'leader'),11:row(10,11,'child')}
        with patch('iprotein_mcp.process_tree.snapshot',side_effect=lambda:dict(rows)):
            family=ProcessTree(10)
            rows[11]=row(1,11,'replacement');del rows[10]
            with patch('iprotein_mcp.process_tree.os.kill') as kill:
                family.send(15);kill.assert_not_called()

    def test_original_group_survivor_is_found_after_leader_exits(self):
        rows={10:row(1,10,'leader')}
        with patch('iprotein_mcp.process_tree.snapshot',side_effect=lambda:dict(rows)):
            family=ProcessTree(10)
            rows[12]=row(1,10,'survivor');del rows[10]
            family.refresh(force=True)
            self.assertEqual(set(family.alive()),{12})
            rows[12]['state']='Z';self.assertFalse(family.alive())

if __name__=='__main__':unittest.main()
