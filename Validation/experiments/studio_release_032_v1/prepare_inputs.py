"""CPU fixtures only. Job preparation/execution uses the existing release adapter."""
import argparse,json,sys
from pathlib import Path
from rdkit import Chem
from rdkit.Chem import AllChem,rdMolTransforms
p=argparse.ArgumentParser();p.add_argument('output',type=Path);p.add_argument('--source',type=Path,required=True);a=p.parse_args()
out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
manifest=json.loads(Path(__file__).with_name('manifest.json').read_text())
sys.path.insert(0,str(a.source/'Sources/iProteinStudio/Resources/rfd3'))
from ligand_intelligence import canonical_atom_names
mol=Chem.AddHs(Chem.MolFromSmiles('CCCO'));assert AllChem.EmbedMolecule(mol,randomSeed=42)==0
names=canonical_atom_names(Chem.MolFromSmiles('CCCO'))
conformers=[]
for label,angle in [('gauche',60),('trans',180)]:
 copy=Chem.Mol(mol);rdMolTransforms.SetDihedralDeg(copy.GetConformer(),0,1,2,3,angle)
 path=out/(label+'.sdf');w=Chem.SDWriter(str(path));w.write(Chem.RemoveHs(copy));w.close()
 conformers.append(dict(label=label,path=str(path),weight=1))
inputs=Path.home()/'.iproteinstudio/projects/studio-release-032/inputs'
requests=[]
for row in manifest['routes']:
 name=row['name'];cfg={k:v for k,v in row.items() if k not in ('name','framework_weights','conformers')}
 if name=='framework-weights':
  cfg.update(task='nanobody',source=str(inputs/'target.cif'),scaffold_weights=row['framework_weights'],scaffold_msa='auto',target_msa=str(inputs/'target.a3m'),sequence_model='abmpnn',search='beam',beam_width=1)
 elif name=='native-objective':
  cfg.update(task='protein',source=str(inputs/'target.cif'),target_msa=str(inputs/'target.a3m'),length=75)
 else:
  cfg.update(task='ligand',ligand_smiles='CCCO',length=75,search='beam',beam_width=1,sequence_model='lasermpnn',ligand_atom_conditions={names[0]:['buried'],names[1]:['hotspot'],names[3]:['hbondDonor','hbondAcceptor']})
  if row.get('conformers'):cfg['ligand_conformers']=conformers
 requests.append(dict(name=name,request=cfg))
(out/'requests.json').write_text(json.dumps(requests,indent=2)+'\n')
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(out/'requests.json')
