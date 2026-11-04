"""Native CPU authoring/audits for bundled frameworks and mixed-length inputs.

Requires the existing RFD4 runtime, never model weights or GPU inference.
The test view isolates shipped input assets from the installed application.
"""
import csv,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]
PIPE=REPO/'Sources/iProteinStudio/Resources/pipeline'
RUNTIME=Path(os.environ['NANOHUNTER_ROOT'])
sys.path.insert(0,str(PIPE/'scripts'))

class NativeInputs(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.out=Path(self.temp.name);self.root=self.out/'runtime';self.root.mkdir()
        (self.root/'components').symlink_to(RUNTIME/'components',target_is_directory=True)
        (self.root/'examples').symlink_to(PIPE/'examples',target_is_directory=True)
        (self.root/'rfd3_scripts').symlink_to(RUNTIME/'rfd3_scripts',target_is_directory=True)
        source=PIPE/'examples/nanobody_scaffolds/structures/7xl0_vobarilizumab.pdb'
        self.source=self.out/'target.pdb'
        self.source.write_text('\n'.join(line[:21]+'B'+line[22:] for line in source.read_text().splitlines() if line.startswith('ATOM'))+'\nEND\n')
    def run_request(self,name,request):
        output=self.out/name;output.mkdir();config=output/'settings.json';config.write_text(json.dumps(request))
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(PIPE/'scripts')+os.pathsep+str(RUNTIME/'rfd3_scripts'))
        for action in ['author','audit']:
            completed=subprocess.run([sys.executable,'-B',str(PIPE/'scripts/rfd4_cli.py'),action,'--root',str(self.root),'--config',str(config),'--output',str(output)],capture_output=True,text=True,env=env,timeout=300)
            self.assertEqual(completed.returncode,0,name+' '+action+'\n'+completed.stdout[-1500:]+completed.stderr[-5000:])
        return output
    def test_all_eight_frameworks_preserve_framework_sequence_and_cdr_ranges(self):
        rows=list(csv.DictReader((PIPE/'examples/nanobody_scaffolds/catalog.tsv').read_text().splitlines(),delimiter='\t'))
        for row in rows:
            with self.subTest(framework=row['scaffold_id']):
                ranges=','.join(f"CDR{i}:"+row[f'cdr{i}_range_1based'] for i in (1,2,3))
                out=self.run_request(row['scaffold_id'],dict(task='nanobody',source=str(self.source),scaffold_id=row['scaffold_id'],cdr_ranges=ranges))
                identity=json.loads((out/'framework_identity.json').read_text())
                self.assertEqual(identity['sequence'],row['sequence'])
                self.assertEqual(identity['ranges'],{f'CDR{i}':list(map(int,row[f'cdr{i}_range_1based'].split('-'))) for i in (1,2,3)})
                self.assertTrue(json.loads((out/'feature_audit.json').read_text())['passed'])
    def test_weighted_frameworks_get_distinct_native_inputs(self):
        out=self.run_request('frameworks',dict(task='nanobody',source=str(self.source),count=3,
            scaffold_weights={'7xl0_vobarilizumab':2,'7eow_caplacizumab':1},scaffold_msa='empty'))
        paths=json.loads((out/'scaffold_inputs.json').read_text())
        self.assertEqual(len(paths),2)
        for scaffold,path in paths.items():
            folder=Path(path).parent
            self.assertTrue(json.loads((folder/'feature_audit.json').read_text())['passed'])
            self.assertEqual(json.loads((folder/'framework_identity.json').read_text())['scaffold_id'],scaffold)

    def test_ligand_controls_and_imported_conformer_reach_native_features(self):
        from rdkit import Chem
        from rdkit.Chem import AllChem
        mol=Chem.AddHs(Chem.MolFromSmiles('CCO'));AllChem.EmbedMolecule(mol,randomSeed=42)
        mol=Chem.RemoveHs(mol);sdf=self.out/'ethanol.sdf'
        writer=Chem.SDWriter(str(sdf));writer.write(mol);writer.close()
        from rfd4.inputs import ligand_source
        sys.path.insert(0,str(RUNTIME/'rfd3_scripts'))
        from ligand_intelligence import canonical_atom_names
        names=canonical_atom_names(Chem.MolFromSmiles('CCO'))
        out=self.run_request('ligand-controls',dict(task='ligand',ligand_smiles='CCO',length=65,count=2,
            ligand_conformers=[dict(label='A',path=str(sdf),weight=1)],length_plan=dict(minimum=65,maximum=66),
            ligand_atom_conditions={names[0]:['buried','hotspot'],names[1]:['exposed'],names[2]:['hbondDonor','hbondAcceptor']}))
        paths=json.loads((out/'ligand_inputs.json').read_text())['A']
        self.assertEqual(set(paths),{'65','66'})
        for path in paths.values():
            folder=Path(path).parent
            self.assertTrue(json.loads((folder/'feature_audit.json').read_text())['passed'])
            spec=json.loads((folder/'condition_spec.json').read_text())['conditions']
            self.assertIn('1',spec['C_RAS']);self.assertIn('3',spec['C_RAS']);self.assertIn('3',spec['C_HB'])
            self.assertIsNotNone(json.loads((folder/'molecule.json').read_text())['conformer_source_sha256'])

    def test_lengths_get_distinct_audited_native_inputs(self):
        out=self.run_request('lengths',dict(task='protein',source=str(self.source),count=3,length_plan=dict(minimum=75,maximum=77)))
        paths=json.loads((out/'length_inputs.json').read_text())
        self.assertEqual(set(paths),{'75','76','77'})
        for length,path in paths.items():
            spec=json.loads((Path(path).parent/'condition_spec.json').read_text())
            self.assertTrue(spec['contig'].startswith(length+'-'+length+','))
            self.assertTrue(json.loads((Path(path).parent/'feature_audit.json').read_text())['passed'])

if __name__=='__main__':unittest.main()
