"""Read-only archive inventory; omit sequences, coordinates and user paths."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import zipfile

parser=argparse.ArgumentParser()
parser.add_argument('archive',type=Path)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
epoch=datetime.datetime(2001,1,1,tzinfo=datetime.timezone.utc)
with zipfile.ZipFile(args.archive) as archive:
    entries=[i for i in archive.infolist() if not i.is_dir() and not i.filename.startswith('__MACOSX/')]
    runs=[];batches=[]
    for info in entries:
        name=info.filename
        if name.endswith('/studio_run.json'):
            data=json.loads(archive.read(info));form=data.get('savedFormState',{})
            runs.append(dict(scaffold=form.get('scaffoldID'),state=data.get('state'),predictor=form.get('designPredictor'),designer=form.get('designer'),trajectories=data.get('requestedTrajectories'),cycles=data.get('optimizationCycles'),created_at=(epoch+datetime.timedelta(seconds=data['createdAt'])).isoformat(),updated_at=(epoch+datetime.timedelta(seconds=data['updatedAt'])).isoformat(),creation_to_update_seconds=data['updatedAt']-data['createdAt']))
        if name.endswith('/studio_engine_batch.json'):
            data=json.loads(archive.read(info));batches.append(dict(campaigns=len(data['campaigns']),budgets=data['campaignBudgets']))
    first=next(i.filename.rsplit('/',1)[0] for i in entries if 'boltz_7xl0_' in i.filename and i.filename.endswith('/studio_run.json'))
    snapshot=json.loads(archive.read(first+'/.studio_runtime/pipeline/snapshot.json'))
    payload=dict(archive_sha256=hashlib.sha256(args.archive.read_bytes()).hexdigest(),files=len(entries),batches=batches,runs=runs,
                 app_version=snapshot['app_version'],mcp_version=archive.read(first+'/.studio_runtime/pipeline/mcp/MCP_VERSION').decode().strip(),
                 logs=[i.filename.split('/')[-1] for i in entries if i.filename.endswith(('.log','.err','.out'))],
                 job=json.loads(archive.read(first+'/studio_job.json')),
                 calibration_files=[i.filename.split('/_calibration/',1)[1] for i in entries if '/_calibration/' in i.filename],
                 calibration_directory_entries=[dict(path=i.filename.split('/_calibration/',1)[1],zip_local_time=list(i.date_time),bytes=i.file_size) for i in archive.infolist() if '/_calibration/' in i.filename and not i.filename.startswith('__MACOSX/')],
                 timing_caution='ZIP timestamps are local, two-second-resolution filesystem metadata, not a precise job execution timeline.')
args.output.write_text(json.dumps(payload,indent=2)+'\n')
print(json.dumps({k:v for k,v in payload.items() if k not in ('runs','calibration_directory_entries')},indent=2))
