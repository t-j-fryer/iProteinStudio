"""Exercise native RFD4 authoring and featurization without model inference."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO=Path(__file__).resolve().parents[1]
PIPE=REPO/'Sources/iProteinStudio/Resources/pipeline'
ROOT=Path(os.environ['NANOHUNTER_ROOT'])

class NativeInputs(unittest.TestCase):
    def test_protein_and_nanobody_preserve_both_target_chains(self):
        scaffold=PIPE/'examples/nanobody_scaffolds/structures/7xl0_vobarilizumab.pdb'
        lines=[line for line in scaffold.read_text().splitlines() if line.startswith('ATOM')]
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);source=root/'assembly.pdb'
            source.write_text('\n'.join(line[:21]+chain+line[22:46]+f'{float(line[46:54])+offset:8.3f}'+line[54:] for chain,offset in [('B',0),('C',30)] for line in lines)+'\nEND\n')
            for task in ['protein','nanobody']:
                out=root/task;out.mkdir()
                request=dict(task=task,source=str(source),length=48,hotspot_residues=['B26','C33'])
                if task=='nanobody':request.update(scaffold_id='7xl0_vobarilizumab',cdr_ranges='CDR1:26-33,CDR2:51-57,CDR3:97-110')
                config=out/'settings.json';config.write_text(json.dumps(request))
                for action in ['author','audit']:
                    result=subprocess.run([sys.executable,'-B',str(PIPE/'scripts/rfd4_cli.py'),action,'--root',str(ROOT),'--config',str(config),'--output',str(out)],capture_output=True,text=True)
                    self.assertEqual(result.returncode,0,result.stdout[-1000:]+result.stderr[-4000:])
                identities=json.loads((out/'target_identity.json').read_text())['chains']
                self.assertEqual([row['output_chain'] for row in identities],['B','C'])
                self.assertEqual(identities[0]['sequence'],identities[1]['sequence'])
                spec=json.loads((out/'condition_spec.json').read_text())
                self.assertEqual(spec['contig'].count('/0'),2)
                self.assertEqual(len(spec['conditions']['C_HOT']['true']),2)
                self.assertTrue(json.loads((out/'feature_audit.json').read_text())['passed'])

if __name__=='__main__':unittest.main()
