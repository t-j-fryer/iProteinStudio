"""Read hash-bound geometry verdicts without importing scientific runtimes."""
import hashlib
import json
from pathlib import Path
from .common import file_digest


def read(root, structure):
    path=Path(root)/structure
    path=path.resolve();root=Path(root).resolve()
    if root not in path.parents:return None
    sidecar=Path(str(path)+'.ligand_geometry.json')
    if not sidecar.is_file():return None
    saved=json.loads(sidecar.read_text());result=saved['result'];canonical=saved['result_json']
    if (hashlib.sha256(canonical.encode()).hexdigest()!=saved['result_sha256'] or json.loads(canonical)!=result
            or file_digest(path)!=result['structure_sha256']):
        raise ValueError('Ligand geometry receipt no longer matches its structure/result.')
    return dict(passed=result['passed'],failures=result['failures'],policy=result['policy'],
                receipt=str(sidecar.relative_to(root)),linker_exit=(result.get('linker_exit') or {}).get('label'),
                cone_samples=(result.get('cone') or {}).get('counts'))


def apply(root, row, structure):
    if not structure:return row
    required=False
    for name,key in (('rfd4_config.json','settings'),('nise_config.json','request'),('studio_run.json','request'),('config/campaign.json',''),('config.json','')):
        config=Path(root)/name
        if config.is_file():
            value=json.loads(config.read_text());settings=value.get(key,{}) if key else value
            required=required or isinstance(settings.get('ligand_geometry'),dict)
    result=read(root,structure)
    if result is None:
        if required and row.get('assessment_mode')!='apo' and row.get('prediction_context') not in ('binder_alone','apo'):
            return dict(row,is_hit=False,hit_filter_passed=False,geometry_passed=False,geometry_status='awaiting_or_missing_geometry_receipt')
        return row
    row=dict(row);row['ligand_geometry']=result
    if not required:return row
    # A geometry pass never reverses another saved gate's failure.
    verdict=row.get('is_hit',row.get('hit_filter_passed',row.get('hit',row.get('passed',row.get('geometry_passed')))))
    prior_false=verdict is False or str(verdict).lower() in ('false','0','fail','no')
    row['is_hit']=result['passed'] and not prior_false
    row['hit_filter_passed']=row['is_hit']
    row['geometry_passed']=result['passed']
    return row
