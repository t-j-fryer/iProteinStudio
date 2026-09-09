#!/usr/bin/env python3
"""Resident NESSO + ESM worker using beta's float32 native-MPS reference path.

One request is fully processed at a time. The owning broker's process group and
execution lease cover this child; it is not a separate GPU service.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time

from nesso_contract import SCALARS, installation, sha256, validate_installation, validate_scores, placement_score, RANKING_POLICY
from runtime import atomic


class Engine:
    def __init__(self, root):
        if os.environ.get('PYTORCH_ENABLE_MPS_FALLBACK') != '0':
            raise RuntimeError('NESSO requires explicitly disabled MPS fallback')
        validate_installation(root)
        self.base = installation(root)
        import torch
        from transformers import AutoModelForMaskedLM, AutoTokenizer
        from nesso.model.models.nesso1 import Nesso1
        if not torch.backends.mps.is_available():
            raise RuntimeError('NESSO requires native Apple MPS')
        torch.set_float32_matmul_precision('highest')
        torch.set_grad_enabled(False)
        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(self.base / 'esm', local_files_only=True)
        self.esm = AutoModelForMaskedLM.from_pretrained(self.base / 'esm', local_files_only=True,
                                                       use_safetensors=True).float().eval().to('mps')
        self.model = Nesso1.from_pretrained(self.base / 'model', map_location='cpu')
        self.model.use_kernels = False
        self.model.predict_args.update(dict(recycling_steps=5, refine_protein_inference=True,
            pose_protein_cutoff=15.0, affinity_protein_cutoff=15.0,
            refine_protein_cutoff=22.0, refine_protein_tokens_budget=256, save_metadata=False))
        self.model.float().eval().to('mps')
        if not self.model.affinity_prediction or any(next(m.parameters()).device.type != 'mps' for m in (self.esm, self.model)):
            raise RuntimeError('NESSO model device or affinity head mismatch')
        torch.mps.synchronize()

    def score(self, sequence, smiles, directory, seed):
        import yaml
        from safetensors.torch import save_file
        from nesso.data.featurizer import NessoFeaturizer
        from nesso.data.inference import InferenceDataset, inference_collate
        from nesso.main import preprocess_yamls
        torch = self.torch
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        torch.manual_seed(seed)
        # Preserve beta's embedding shape including BOS/EOS tokens.
        started = time.monotonic()
        esm_dir = directory / 'esm'; esm_dir.mkdir(exist_ok=True)
        encoded = {k: v.to('mps') for k, v in self.tokenizer(sequence, return_tensors='pt').items()}
        with torch.inference_mode():
            output = self.esm(**encoded, output_hidden_states=True)
            embedding = output.hidden_states[-1].squeeze(0).unsqueeze(0).float().cpu().contiguous()
        if embedding.shape != (1, len(sequence) + 2, 1280) or not torch.isfinite(embedding).all():
            raise RuntimeError('Invalid NESSO ESM embedding')
        esm_path = esm_dir / (hashlib.md5(sequence.encode()).hexdigest() + '.safetensors')
        save_file({'embeddings': embedding}, esm_path)
        del encoded, output, embedding
        esm_seconds = time.monotonic() - started
        query = directory / 'input.yaml'
        query.write_text(yaml.safe_dump({'sequences': [
            {'protein': {'id': 'A', 'sequence': sequence, 'esm': str(esm_path.resolve())}},
            {'ligand': {'id': 'B', 'smiles': smiles}}], 'properties': [{'affinity': {'binder': 'B'}}]}, sort_keys=False))
        processed = directory / 'processed'
        mol = processed / 'rdkit_conformers'; mol.mkdir(parents=True, exist_ok=True)
        manifest, failures = preprocess_yamls([query], mol_dir=mol, ccd_pkl=self.base / 'ccd.pkl',
            structures_dir=processed / 'structures', records_dir=processed / 'records', num_workers=1)
        if failures or len(manifest.records) != 1:
            raise RuntimeError('NESSO input preprocessing failed; no candidate may be skipped')
        from ligand_atoms import audit_nesso_ligand
        from nesso.data.yaml_input import _assign_ligand_atom_names
        atomic(directory / 'ligand_identity.json', audit_nesso_ligand(smiles, mol, _assign_ligand_atom_names))
        manifest.dump(processed / 'manifest.json')
        dataset = InferenceDataset(manifest=manifest, target_dir=processed,
            featurizer=NessoFeaturizer(esm_emb_dir=esm_dir, esm_emb_dim=1280, esm_num_layers=33),
            ligand_dir=mol, ccd_pkl=self.base / 'ccd.pkl')
        sample = dataset[0]
        if sample.get('exception'):
            raise RuntimeError('NESSO featurization failed')
        batch = inference_collate([sample])
        batch = {k: v.to('mps') if isinstance(v, torch.Tensor) else v for k, v in batch.items()}
        torch.mps.synchronize()
        started = time.monotonic()
        with torch.inference_mode():
            predicted = self.model.predict_step(batch, 0)
        torch.mps.synchronize()
        if predicted.get('exception'):
            raise RuntimeError('NESSO prediction failed')
        values = validate_scores({k: (None if k == 'entropy_crop_pl' and predicted.get(k) is None
                                      else float(predicted[k].detach().float().cpu().item())) for k in SCALARS})
        result = dict(scores=values, placement=placement_score(values), ranking_policy=dict(RANKING_POLICY), esm_seconds=esm_seconds, inference_seconds=time.monotonic()-started,
                      device='mps', precision='float32', recycling_steps=5, refine_protein_inference=True,
                      model_load_count=2, mps_current_bytes=torch.mps.current_allocated_memory())
        atomic(directory / 'affinity.json', result)
        return result


def serve(config_path):
    config = json.loads(config_path.read_text())
    queue = Path(config['queue'])
    output = Path(config['output']).resolve()
    def owned(path):
        path = Path(path).resolve()
        if output not in path.parents:
            raise RuntimeError('NESSO request path is outside its campaign')
        return path
    owned(queue)
    started = time.monotonic()
    engine = Engine(Path(config['root']))
    atomic(queue / 'ready.json', dict(device='mps', fallback=0, pid=os.getpid(), model_load_count=2,
        config_sha256=sha256(config_path), startup_seconds=time.monotonic()-started))
    while not (queue / 'stop.json').exists():
        try:
            os.kill(config['owner_pid'], 0)
        except ProcessLookupError:
            return
        for path in sorted((queue / 'requests').glob('*.json')):
            response = queue / 'responses' / path.name
            if response.exists():
                continue
            request = json.loads(path.read_text())
            try:
                result = engine.score(request['sequence'], request['smiles'], owned(request['directory']), config['seed'])
                atomic(response, dict(ok=True, request_id=request['request_id'], input_sha256=sha256(path), result=result))
            except Exception as e:
                atomic(response, dict(ok=False, request_id=request.get('request_id'), error=str(e)))
                raise  # A failed model never silently serves a later candidate.
        time.sleep(0.1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    serve(parser.parse_args().config)
