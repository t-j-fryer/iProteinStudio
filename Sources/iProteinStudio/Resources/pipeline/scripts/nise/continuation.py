"""Validate an explicit code/scheduler continuation without editing old plans."""
import json
from pathlib import Path
from runtime import Journal, digest


def validate(output):
    output=Path(output).resolve();path=output/'nise_continuation.json'
    descriptor=json.loads(path.read_text())
    if descriptor.get('schema')!=1 or descriptor.get('submission')!='stage-directory':
        raise ValueError('Unknown NISE continuation policy')
    config=output/'nise_config.json'
    if digest(config)!=descriptor['base_config_sha256']:
        raise ValueError('Continuation changed the original scientific request')
    snapshot=(output/descriptor['pipeline_snapshot']).resolve()
    if output not in snapshot.parents or not (snapshot/'scripts/nise/batch_runtime.py').is_file():
        raise ValueError('Continuation code must be frozen inside its campaign')
    assets=[path,config]
    for relative,sha in descriptor['checkpoints'].items():
        receipt=(output/relative).resolve()
        if output not in receipt.parents or digest(receipt)!=sha:
            raise ValueError('Original continuation checkpoint changed')
        data=json.loads(receipt.read_text());Journal(output).load(receipt,data['input'])
        assets.append(receipt)
        assets.extend(output/p for p in data['files'])
    if not descriptor['checkpoints']:
        raise ValueError('Continuation requires completed operations to preserve')
    return snapshot,assets,descriptor
