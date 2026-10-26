"""Bounded, identity-preserving candidate review and portable export."""
from __future__ import annotations
import base64
import hashlib
import io
import json
import math
import re
import zipfile
import tempfile
from pathlib import Path
from .common import StudioError, agent_root, atomic_json, canonical_digest, file_digest, load_json, CSV_COMPLETE_SCAN, csv_rows
from . import catalog

MAX_CANDIDATES = 20000
MAX_EXPORT_BYTES = 64 * 1024 * 1024

def _clean(value):
    if isinstance(value, float) and not math.isfinite(value): return None
    if isinstance(value, dict): return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, list): return [_clean(v) for v in value]
    return value

def _index(run_id):
    token = CSV_COMPLETE_SCAN.set(True)
    try:
        return _complete_index(run_id)
    finally:
        CSV_COMPLETE_SCAN.reset(token)


def _complete_index(run_id):
    root = catalog.resolve_run(run_id)
    kind = catalog.classify_run(root)
    if kind == 'iterative_batch':
        overview = catalog._iterative_batch_overview(root, MAX_CANDIDATES+1, None, None, False)
    elif kind == 'iterative': overview = catalog._iterative_overview(root, MAX_CANDIDATES+1)
    elif kind == 'rfdiffusion3': overview = catalog._rfd3_overview(root, MAX_CANDIDATES+1)
    elif kind == 'nise': overview = catalog._nise_overview(root, MAX_CANDIDATES+1)
    else: overview = catalog.results_overview(run_id, False, MAX_CANDIDATES+1)
    if overview.get('truncated'):
        raise StudioError('Candidate index exceeds the bounded scan. Select an individual child campaign.')
    records = []
    sequence_cache = {}
    source_cache = {}
    for group in overview['groups']:
        source_id = group.get('campaign_run_id', run_id)
        source_root = catalog.resolve_run(source_id)
        if catalog.classify_run(source_root) == 'iterative' and source_id not in sequence_cache:
            sequences = {}
            rows = catalog._iterative_rows(source_root) + csv_rows(source_root/'summary_all_runs.csv')
            for row in rows:
                if not row.get('binder_sequence'): continue
                try: key = (str(int(row['run'])), str(int(row['cycle'])))
                except (KeyError, ValueError, TypeError): raise StudioError('Invalid saved sequence identity.')
                sequence = row['binder_sequence'].strip()
                if key in sequences and sequences[key] != sequence:
                    raise StudioError('Conflicting sequences for the same saved run/cycle.')
                sequences[key] = sequence
            sequence_cache[source_id] = sequences
        if source_id not in source_cache:
            source_cache[source_id] = []
            for relative in ('studio_run.json', 'studio_job.json', 'config/studio_request.json', 'rfd4_config.json', 'settings.json'):
                path = (source_root/relative).resolve()
                if path.is_file():
                    if source_root not in path.parents: raise StudioError('Unsafe source manifest.')
                    source_cache[source_id].append(dict(path=relative, sha256=file_digest(path)))
        for variant in group.get('variants', []):
            group_id = '|'.join(group['id'].split('|')[-2:]) if 'campaign_run_id' in group else group['id']
            identity = dict(run_id=source_id, group_id=group_id, variant_id=variant['id'])
            sequence = variant.get('sequence')
            if not sequence and source_id in sequence_cache:
                trajectory = group['id'].split('|')[-1]
                sequence = sequence_cache[source_id].get((trajectory,str(variant.get('cycle'))))
            record = dict(candidate_id=canonical_digest(identity), **identity, workflow=kind,
                sequence=sequence, cycle=variant.get('cycle'), source_manifests=source_cache[source_id],
                framework_id=group.get('framework_id'), design_engine=group.get('design_engine'),
                is_hit=variant.get('is_hit'), failed_filters=variant.get('failed_filters', []),
                selection={k:v for k,v in variant.items() if k in {
                    'metrics','passed_selection','passed_self_consistency','score_status','branch',
                    'final_eligible','nesso_screening_scores','psichic_screening_scores'}},
                artifacts=variant.get('artifacts', []),
                interpretation='Computational candidate; artifact-specific checks are not experimental binding evidence.')
            for artifact in record['artifacts']:
                for key in ('path', 'confidence_json'):
                    if not artifact.get(key): continue
                    relative = Path(artifact[key])
                    path = (source_root / relative).resolve()
                    if relative.is_absolute() or source_root not in path.parents or not path.is_file():
                        raise StudioError('Candidate artifact is missing or outside the run.')
                    if path.stat().st_size > MAX_EXPORT_BYTES:
                        raise StudioError('Candidate artifact exceeds the export size limit.')
                    artifact[key + '_sha256'] = file_digest(path)
            records.append(_clean(record))
            if len(records)>MAX_CANDIDATES: raise StudioError('Too many candidates; select an individual campaign.')
    records.sort(key=lambda r:r['candidate_id'])
    return records

def candidates_list(run_id, limit=50, cursor=None):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise StudioError('Page size must be between 1 and 100.')
    if cursor is not None and (not isinstance(cursor, str) or len(cursor) > 4096):
        raise StudioError('Invalid candidate cursor.')
    records = _index(run_id)
    digest = canonical_digest(records)
    offset = 0
    if cursor:
        try:
            data = json.loads(base64.urlsafe_b64decode(cursor.encode()))
            if data['run_id']!=run_id or data['snapshot_sha256']!=digest:
                raise StudioError('Results changed since the previous page. Restart pagination to obtain a consistent snapshot.')
            offset=data['offset']
            if type(offset) is not int or not 0<=offset<=len(records):raise ValueError()
        except (ValueError,KeyError,TypeError,UnicodeError) as exc:raise StudioError('Invalid candidate cursor.') from exc
    end=min(offset+limit,len(records))
    next_cursor = base64.urlsafe_b64encode(json.dumps(dict(run_id=run_id,snapshot_sha256=digest,offset=end)).encode()).decode() if end<len(records) else None
    return dict(schema_version=1,run_id=run_id,snapshot_sha256=digest,total_count=len(records),
                offset=offset,candidates=records[offset:end],next_cursor=next_cursor)

def candidate_export(run_id, candidate_ids, snapshot_sha256):
    if not isinstance(candidate_ids, list) or not 1 <= len(candidate_ids) <= 100:
        raise StudioError('Select between 1 and 100 candidates.')
    records = _index(run_id)
    if canonical_digest(records)!=snapshot_sha256:raise StudioError('Results changed; list candidates again before exporting.')
    by_id={r['candidate_id']:r for r in records}
    if len(set(candidate_ids))!=len(candidate_ids) or any(k not in by_id for k in candidate_ids):
        raise StudioError('Export requires distinct candidate IDs from the current run snapshot.')
    selected=[by_id[k] for k in candidate_ids]
    files={}; total=0
    for candidate in selected:
        root=catalog.resolve_run(candidate['run_id'])
        for index,artifact in enumerate(candidate['artifacts']):
            for key in ['path','confidence_json']:
                if not artifact.get(key):continue
                relative=Path(artifact[key])
                path=(root/relative).resolve()
                if relative.is_absolute() or root not in path.parents or path.suffix.lower() not in {'.pdb','.cif','.mmcif','.json'} or not path.is_file():
                    raise StudioError('Unsafe or missing candidate artifact.')
                size=path.stat().st_size
                if total+size>MAX_EXPORT_BYTES:raise StudioError('Export exceeds 64 MiB; select fewer candidates.')
                with path.open('rb') as handle: data=handle.read(MAX_EXPORT_BYTES-total+1)
                total+=len(data)
                if hashlib.sha256(data).hexdigest()!=artifact[key+'_sha256']:
                    raise StudioError('Artifact changed during export; refresh the candidate snapshot.')
                if total>MAX_EXPORT_BYTES:raise StudioError('Export exceeds 64 MiB.')
                name=f"artifacts/{candidate['candidate_id']}/{index}-{key}{path.suffix.lower()}"
                files[name]=data
                artifact[key]=name
                artifact[key+'_sha256']=hashlib.sha256(data).hexdigest()
    sources = {}
    for candidate in selected:
        root = catalog.resolve_run(candidate['run_id'])
        for item in candidate['source_manifests']:
            path = (root/item['path']).resolve()
            name = 'sources/'+canonical_digest(candidate['run_id'])+'/'+item['path']
            if name in sources: continue
            if root not in path.parents or not path.is_file(): raise StudioError('Unsafe source manifest.')
            with path.open('rb') as handle: data=handle.read(MAX_EXPORT_BYTES-total+1)
            total += len(data)
            if total > MAX_EXPORT_BYTES or hashlib.sha256(data).hexdigest()!=item['sha256']:
                raise StudioError('Source manifest changed or exceeds the export limit.')
            files[name]=data
            sources[name]=dict(run_id=candidate['run_id'], source_path=item['path'])
    fasta=[]
    for candidate in selected:
        seq=candidate.get('sequence')
        if seq:
            if not isinstance(seq,str) or not re.fullmatch('[A-Z]+',seq):raise StudioError('Invalid saved candidate sequence.')
            fasta.append('>'+candidate['candidate_id']+'\n'+seq+'\n')
    files['sequences.fasta']=''.join(fasta).encode()
    manifest=dict(schema_version=1,run_id=run_id,source_snapshot_sha256=snapshot_sha256,
        candidates=selected,sources=sources,missing_sequences=[r['candidate_id'] for r in selected if not r.get('sequence')],files={k:dict(sha256=hashlib.sha256(v).hexdigest(),bytes=len(v)) for k,v in files.items()})
    files['manifest.json']=json.dumps(manifest,indent=2,allow_nan=False).encode()
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,data in sorted(files.items()):
            info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,data)
    data=stream.getvalue();digest=hashlib.sha256(data).hexdigest()
    dest=agent_root()/'exports';dest.mkdir(exist_ok=True)
    path=dest/(digest+'.zip')
    if path.exists() and file_digest(path)!=digest:raise StudioError('Existing export checksum mismatch.')
    if not path.exists():
        with tempfile.NamedTemporaryFile(dir=dest, suffix='.part', delete=False) as handle:
            handle.write(data); temp=Path(handle.name)
        temp.replace(path)
    return dict(schema_version=1,export_sha256=digest,bytes=len(data),candidate_count=len(selected),
                uri='iprotein://exports/'+digest,format='zip',local_path=str(path),
                retrieval='Use export_read in bounded chunks; decode base64 and verify the complete SHA-256.')

def export_read(export_sha256,offset=0,length=196608):
    if type(offset) is not int or offset < 0 or type(length) is not int or not 1 <= length <= 196608:
        raise StudioError('Invalid export chunk range.')
    if not re.fullmatch('[0-9a-f]{64}',export_sha256):raise StudioError('Invalid export digest.')
    path=agent_root()/'exports'/(export_sha256+'.zip')
    if not path.is_file() or file_digest(path)!=export_sha256:raise StudioError('Export missing or changed.')
    size=path.stat().st_size
    if offset>size:raise StudioError('Offset exceeds export size.')
    with path.open('rb') as handle:handle.seek(offset);data=handle.read(length)
    end=offset+len(data)
    return dict(schema_version=1,export_sha256=export_sha256,offset=offset,total_bytes=size,
                chunk_sha256=hashlib.sha256(data).hexdigest(),data_base64=base64.b64encode(data).decode(),
                next_offset=end if end<size else None)

def candidates_compare(run_ids,metric,threshold):
    summaries=[]
    for run_id in run_ids:
        records=_index(run_id);groups={}
        for row in records:
            for artifact in row['artifacts']:
                key=(artifact.get('predictor'),artifact.get('role'),artifact.get('prediction_context'))
                group=groups.setdefault(key,{'candidates':set(),'values':{}})
                group['candidates'].add(row['candidate_id'])
                value=artifact.get('metrics',{}).get(metric)
                if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value):
                    group['values'].setdefault(row['candidate_id'],[]).append(value)
        for (predictor,role,context),group in groups.items():
            ambiguous=sum(len(v)!=1 for v in group['values'].values())
            values=[v[0] for v in group['values'].values() if len(v)==1]
            summaries.append(dict(run_id=run_id,predictor=predictor,role=role,prediction_context=context,
                total_candidates=len(group['candidates']),with_single_metric=len(values),
                missing_metric=len(group['candidates'])-len(group['values']),ambiguous_samples=ambiguous,
                passed=sum(v>=threshold for v in values),threshold=threshold,comparison='>=',
                fraction=sum(v>=threshold for v in values)/len(values) if values else None))
    return dict(schema_version=1,metric=metric,summaries=summaries,
        interpretation='Descriptive counts across available cycles, separated by predictor/context. Missing and multiply sampled metrics are excluded explicitly; this does not establish matched experiments or experimental binding.')
