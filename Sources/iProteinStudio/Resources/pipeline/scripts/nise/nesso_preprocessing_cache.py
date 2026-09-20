"""Reuse fresh-worker ligand conformers while calling the same upstream parser.

Each new exact SMILES string takes the ordinary subprocess path once. Cache hits
use those exact conformer bytes, avoiding request-order-dependent RDKit draws.
Only Studio's one canonical protein + one SMILES ligand contract is supported.
"""
from collections import OrderedDict
import hashlib
from pathlib import Path

class PreprocessingCache:
    def __init__(self, amino_acids, capacity=8):
        if capacity < 1:raise ValueError('Positive conformer-cache capacity required')
        self.amino_acids=amino_acids
        self.capacity=capacity
        self.conformers=OrderedDict()
        self.hits=0
        self.misses=0
        self.noncanonical_requests=0

    def run(self, query, mol_dir, processed):
        import yaml
        from nesso.main import preprocess_yamls
        from nesso.data.yaml_input import parse_schema
        from nesso.data.types import Manifest
        schema=yaml.safe_load(query.read_text())
        protein,ligand=schema['sequences']
        sequence=protein['protein']['sequence']
        smiles=ligand['ligand']['smiles']
        if set(sequence)-set('ACDEFGHIKLMNPQRSTVWY'):
            # Unknown/modified residues retain upstream's complete CCD path.
            self.noncanonical_requests+=1
            return preprocess_yamls([query],mol_dir=mol_dir,ccd_pkl=self.amino_acids.path,
                structures_dir=processed/'structures',records_dir=processed/'records',num_workers=1)
        molecules=self.amino_acids.get()  # Also verifies that CCD identity did not change.
        if smiles not in self.conformers:
            manifest,failures=preprocess_yamls([query],mol_dir=mol_dir,ccd_pkl=self.amino_acids.path,
                structures_dir=processed/'structures',records_dir=processed/'records',num_workers=1)
            if failures or len(manifest.records)!=1:
                raise RuntimeError('NESSO conformer cache cannot retain failed preprocessing')
            source=mol_dir/(query.stem+'__'+ligand['ligand']['id']+'.pkl')
            self.conformers[smiles]=source.read_bytes()
            if len(self.conformers)>self.capacity:self.conformers.popitem(last=False)
            self.misses+=1
            return manifest,failures
        raw=self.conformers[smiles]
        self.conformers.move_to_end(smiles)
        saved=processed/'cached_ligand.pkl';saved.write_bytes(raw)
        ligand['ligand']['conformer']=str(saved.resolve())
        structures=processed/'structures';records=processed/'records'
        structures.mkdir(parents=True,exist_ok=True);records.mkdir(parents=True,exist_ok=True)
        struct,rec,_,_=parse_schema(schema,mol_dir,ccd_dict=molecules,record_id=query.stem)
        struct.dump(structures/f'{rec.id}.npz');rec.dump(records/f'{rec.id}.json')
        self.hits+=1
        return Manifest([rec]),[]

    def receipt(self):
        return dict(policy='fresh-worker-conformer-reuse-v1',hits=self.hits,misses=self.misses,
                    noncanonical_requests=self.noncanonical_requests,
                    capacity=self.capacity,entries=len(self.conformers),
                    conformer_sha256=[hashlib.sha256(value).hexdigest() for value in self.conformers.values()])
