"""Native CPU authoring/audits for bundled frameworks and mixed-length inputs.

Requires the existing RFD4 runtime, never model weights or GPU inference.
The test view isolates shipped input assets from the installed application.
"""
import csv,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
REPO=Path(__file__).resolve().parents[1]
PIPE=REPO/'Sources/iProteinStudio/Resources/pipeline'
RUNTIME=Path(os.environ['NANOHUNTER_ROOT'])

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
    def test_lengths_get_distinct_audited_native_inputs(self):
        out=self.run_request('lengths',dict(task='protein',source=str(self.source),count=3,length_plan=dict(minimum=75,maximum=77)))
        paths=json.loads((out/'length_inputs.json').read_text())
        self.assertEqual(set(paths),{'75','76','77'})
        for length,path in paths.items():
            spec=json.loads((Path(path).parent/'condition_spec.json').read_text())
            self.assertTrue(spec['contig'].startswith(length+'-'+length+','))
            self.assertTrue(json.loads((Path(path).parent/'feature_audit.json').read_text())['passed'])

if __name__=='__main__':unittest.main()
