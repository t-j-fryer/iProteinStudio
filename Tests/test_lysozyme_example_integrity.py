"""Audit the shipped experimental T4 lysozyme example, without inference."""
import hashlib,json,re,shlex,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
EXAMPLE=ROOT/'Sources/iProteinStudio/Resources/examples/t4_lysozyme'
AA=dict(zip('ALA ARG ASN ASP CYS GLN GLU GLY HIS ILE LEU LYS MET PHE PRO SER THR TRP TYR VAL'.split(),'ARNDCQEGHILKMFPSTWYV'))
class LysozymeExampleTests(unittest.TestCase):
 def test_exact_sequence_coordinates_and_reference(self):
  source=(EXAMPLE/'2LZM.pdb').read_text().splitlines();target=(EXAMPLE/'target.pdb').read_text().splitlines()
  self.assertIn('2LZM',source[0]);self.assertIn('T4 LYSOZYME',' '.join(source[:10]))
  atoms=[l for l in source if l.startswith('ATOM  ')];mapped=[l for l in target if l.startswith('ATOM  ')]
  self.assertEqual(len(atoms),1309);self.assertEqual({l[21] for l in atoms},{'A'})
  self.assertEqual(mapped,[l[:21]+'B'+l[22:] for l in atoms])
  residues={int(l[22:26]):l[17:20] for l in atoms};self.assertEqual(set(residues),set(range(1,165)))
  sequence=''.join(AA[residues[i]] for i in range(1,165))
  seqres=''.join(AA[x] for l in source if l.startswith('SEQRES') for x in l[19:70].split())
  self.assertEqual(sequence,seqres)
  self.assertEqual((EXAMPLE/'target.fasta').read_text().splitlines()[1],sequence)
  swift=(ROOT/'Sources/iProteinStudio/Models/ExampleTarget.swift').read_text()
  self.assertIn('sequence: "'+sequence+'"',swift);self.assertNotIn('static let acbx',swift)
  self.assertIn(sequence,(ROOT/'Sources/iProteinStudio/Resources/pipeline/examples/t4_lysozyme_bind.yaml').read_text())
 def test_cif_matches_pdb_atoms(self):
  lines=(EXAMPLE/'2LZM.cif').read_text().splitlines();tags=[l.strip() for l in lines if l.startswith('_atom_site.') ]
  self.assertTrue(tags);columns={t:i for i,t in enumerate(tags)}
  rows=[shlex.split(l) for l in lines if l.startswith('ATOM ')]
  self.assertEqual(len(rows),1309)
  pdb=[l for l in (EXAMPLE/'2LZM.pdb').read_text().splitlines() if l.startswith('ATOM  ')]
  for row,line in zip(rows,pdb):
   self.assertEqual(row[columns['_atom_site.auth_asym_id']],'A')
   self.assertEqual(int(row[columns['_atom_site.auth_seq_id']]),int(line[22:26]))
   self.assertEqual(row[columns['_atom_site.auth_atom_id']],line[12:16].strip())
   for tag,beg,end in [('Cartn_x',30,38),('Cartn_y',38,46),('Cartn_z',46,54)]:
    self.assertEqual(float(row[columns['_atom_site.'+tag]]),float(line[beg:end]))
 def test_provenance_and_no_unclaimed_alignment(self):
  record=json.loads((EXAMPLE/'provenance.json').read_text());self.assertEqual(record['pdb_id'],'2LZM')
  for name,digest in record['sha256'].items():self.assertEqual(hashlib.sha256((EXAMPLE/name).read_bytes()).hexdigest(),digest)
  self.assertFalse((EXAMPLE/'target_msa.a3m').exists())
if __name__=='__main__':unittest.main()
