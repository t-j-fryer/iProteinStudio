"""Validate an explicit code/scheduler continuation without editing old plans."""
import json
from pathlib import Path
from runtime import Journal, digest


def validate(output):
    output=Path(output).resolve();path=output/'nise_continuation.json'
    descriptor=json.loads(path.read_text())
    if descriptor.get('schema') not in (1,2) or descriptor.get('submission')!='stage-directory':
        raise ValueError('Unknown NISE continuation policy')
    if descriptor['schema'] == 2:
        execution = descriptor.get('execution', {})
        if (set(execution) != {'resident_workers', 'rng_policy', 'cpu_threads'}
                or type(execution['resident_workers']) is not int or execution['resident_workers'] not in (1,2)
                or execution['rng_policy'] != 'per-input-v1' or execution['cpu_threads'] != 4):
            raise ValueError('Invalid explicit resident-pool execution policy')
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
