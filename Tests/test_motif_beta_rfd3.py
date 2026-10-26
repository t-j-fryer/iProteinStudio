"""Native RFD3 input prevalidation for remapped motif ligands; no model load."""
import json,os,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Sources/iProteinStudio/Resources/pipeline/scripts'))
from motif_beta.contract import prepare

class NativeMotifInputs(unittest.TestCase):
    def test_native_parser_keeps_conditioning_ligand_selectors(self):
        os.environ['DEBUG']='false'
        from rfd3.inference.input_parsing import DesignInputSpecification
        for case in ('M0349_1e3v','M0040_13pk','M0050_1dbt'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as tmp:
                folder=Path(tmp)
                saved=prepare(folder,{'case_id':case,'length':128})
                spec=json.loads((folder/'rfd3.yaml').read_text());spec.pop('run')
                parsed=DesignInputSpecification.safe_init(**spec)
                self.assertIsNotNone(parsed)
                self.assertEqual(len(saved['conditioning_ligands']),len(json.loads((folder/'case.json').read_text())['ligands']))

if __name__=='__main__':unittest.main()
