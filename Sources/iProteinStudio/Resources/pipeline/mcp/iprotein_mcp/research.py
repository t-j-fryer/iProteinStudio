"""Optional official RCSB MCP runtime. No scientific engine or global client changes."""
from __future__ import annotations
import fcntl, hashlib, json, os, platform, re, subprocess, sys, tempfile, urllib.request, urllib.parse, signal
from pathlib import Path
from .common import StudioError, atomic_json, file_digest, runtime_root, utc_now, import_artifact

BRIDGE=Path(__file__).resolve().parents[1]
LOCK=BRIDGE/'rcsb-lock.json'
MAX_DOWNLOAD=64*1024*1024

def home(): return runtime_root()/'research/rcsb'

def _download(url, maximum=MAX_DOWNLOAD):
    try:
        with urllib.request.urlopen(url,timeout=30) as response:
            if urllib.parse.urlparse(response.geturl()).hostname not in {'files.pythonhosted.org','files.rcsb.org'}:
                raise StudioError('Unexpected download redirect.')
            data=response.read(maximum+1)
    except OSError as exc:
        raise StudioError('RCSB download failed: '+str(exc)) from exc
    if len(data)>maximum:raise StudioError('Download exceeds its bounded size.')
    return data

def status():
    p=home()/'current.json'
    if not p.exists():return dict(installed=False,version=None)
    receipt=json.loads(p.read_text());directory=(home()/receipt['directory']).resolve()
    if home().resolve() not in directory.parents:raise StudioError('Invalid RCSB runtime path.')
    inventory=directory/'receipt.json'
    healthy=inventory.is_file() and file_digest(inventory)==receipt['receipt_sha256'] and (directory/'site-packages').is_dir()
    return dict(installed=healthy,version=receipt.get('version'),directory=str(directory),
                expected_version=json.loads(LOCK.read_text())['rcsb_version'])

def install():
    if sys.version_info[:2]!=(3,11) or platform.machine()!='arm64' or sys.platform!='darwin':
        raise StudioError('Use Studio’s managed Python 3.11 on Apple silicon to install RCSB.')
    base=home();base.mkdir(parents=True,exist_ok=True)
    with (base/'install.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        package=json.loads(LOCK.read_text());identity=file_digest(LOCK)
        try: current=status()
        except (StudioError, ValueError, KeyError, OSError): current={'installed':False}
        if current['installed']:
            rec=json.loads((Path(current['directory'])/'receipt.json').read_text())
            if rec.get('lock_sha256')==identity:
                try:
                    _verified_python();return current
                except StudioError:
                    pass  # Repair installs a fresh generation; publish only after qualification.
        directory=Path(tempfile.mkdtemp(prefix='runtime-',dir=base))
        # Control Python deliberately omits venv; use an isolated --target tree.
        wheels=directory/'wheels';wheels.mkdir();requirements=[]
        for item in package['files']:
            parsed=urllib.parse.urlparse(item['url'])
            if parsed.scheme!='https' or parsed.hostname!='files.pythonhosted.org':raise StudioError('Invalid locked wheel host.')
            data=_download(item['url'])
            if hashlib.sha256(data).hexdigest()!=item['sha256']:raise StudioError('RCSB dependency checksum mismatch: '+item['name'])
            name=Path(parsed.path).name
            if not name.endswith('.whl'):raise StudioError('Only prebuilt wheels are supported.')
            (wheels/name).write_bytes(data)
            requirements.append(item['name']+'=='+item['version']+' --hash=sha256:'+item['sha256'])
        req=directory/'requirements.txt';req.write_text('\n'.join(requirements)+'\n')
        python=Path(sys.executable).resolve()
        try:
            subprocess.run([str(python),'-B','-m','pip','install','--no-index','--no-cache-dir','--only-binary=:all:',
                '--find-links',str(wheels),'--require-hashes','--target',str(directory/'site-packages'),'-r',str(req)],check=True,capture_output=True,timeout=180)
        except subprocess.CalledProcessError as exc:raise StudioError('RCSB installation failed: '+exc.stderr.decode()[-2000:]) from exc
        inventory={str(p.relative_to(directory)):file_digest(p) for p in directory.rglob('*')
                   if p.is_file() and not p.is_symlink() and p.suffix not in {'.pyc'} and '__pycache__' not in p.parts and 'wheels' not in p.relative_to(directory).parts}
        atomic_json(directory/'receipt.json',dict(lock_sha256=identity,version=package['rcsb_version'],
            installed_at=utc_now(),control_python=str(python),control_python_sha256=file_digest(python),files=inventory))
        # Publish only after import/protocol initialization works.
        _invoke(directory,{'operation':'tools'})
        atomic_json(base/'current.json',dict(directory=directory.name,version=package['rcsb_version'],receipt_sha256=file_digest(directory/'receipt.json')))
        return status()

def _verified_python():
    installed=status()
    if not installed['installed']:raise StudioError('RCSB is not installed. In Studio → AI, install the optional RCSB structure-discovery tools.')
    directory=Path(installed['directory']);receipt=json.loads((directory/'receipt.json').read_text())
    actual = {str(p.relative_to(directory)) for p in directory.rglob('*')
              if p.is_file() and p.name != 'receipt.json' and p.suffix != '.pyc'
              and '__pycache__' not in p.parts and 'wheels' not in p.relative_to(directory).parts}
    if actual != set(receipt['files']): raise StudioError('RCSB runtime file inventory changed; reinstall the integration.')
    for name,digest in receipt['files'].items():
        p=(directory/name).resolve()
        if directory not in p.parents or not p.is_file() or file_digest(p)!=digest:
            raise StudioError('RCSB runtime changed; reinstall the optional integration.')
    interpreter=Path(receipt['control_python'])
    if not interpreter.is_file() or file_digest(interpreter)!=receipt['control_python_sha256']:
        raise StudioError('The retained RCSB interpreter changed; reinstall the integration.')
    return directory

def _invoke(directory,request):
    python=Path(json.loads((directory/'receipt.json').read_text())['control_python'])
    env={k:v for k,v in os.environ.items() if k in {'PATH','HOME','TMPDIR','LANG','LC_ALL','SSL_CERT_FILE'}}
    env.update(PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',IPROTEINSTUDIO_RCSB_SITE=str(directory/'site-packages'), PYTHONPYCACHEPREFIX='/dev/null')
    command = [str(python), '-B', '-X', 'pycache_prefix=/dev/null', '-c',
        'import sys,runpy;sys.path.insert(0,sys.argv.pop(1));runpy.run_path(sys.argv.pop(1),run_name="__main__")',
        str(directory/'site-packages'), str(BRIDGE/'rcsb_worker.py')]
    # A separate group lets a timeout stop the upstream stdio server as well.
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                                   env=env, start_new_session=True)
        try:
            process.communicate(json.dumps(request).encode(), timeout=50)
        except subprocess.TimeoutExpired as exc:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise StudioError('RCSB request timed out.') from exc
        if process.returncode:
            stderr.seek(0, 2); size = stderr.tell(); stderr.seek(max(0, size-2000))
            raise StudioError('RCSB request failed: '+stderr.read().decode(errors='replace'))
        stdout.seek(0); data = stdout.read(1_800_001)
        if len(data)>1_800_000: raise StudioError('RCSB result is too large; request fewer entries or fields.')
        return json.loads(data)

def tools_list():return dict(schema_version=1,provider='RCSB PDB',version=status().get('version'),**_invoke(_verified_python(),{'operation':'tools'}))

def query(tool_name,arguments):
    if not tool_name.startswith(('rcsb_search_','rcsb_get_','rcsb_find_','rcsb_list_','rcsb_describe_','rcsb_seqcoord_','rcsb_data_')):
        raise StudioError('Only official RCSB discovery, inspection and mapping tools are allowed.')
    value=_invoke(_verified_python(),{'operation':'call','name':tool_name,'arguments':arguments})
    return dict(schema_version=1,provider='RCSB PDB',tool=tool_name,retrieved_at=utc_now(),result=value)

def import_structure(pdb_id,assembly_id):
    # Require explicit biological assembly; never substitute the asymmetric unit.
    if not re.fullmatch('[A-Za-z0-9]{4}',pdb_id) or not re.fullmatch('[1-9][0-9]{0,3}',assembly_id):raise StudioError('Use a four-character PDB accession and explicit positive assembly ID.')
    pdb_id=pdb_id.upper();url=f'https://files.rcsb.org/download/{pdb_id}-assembly{assembly_id}.cif'
    data=_download(url)
    if not data.lstrip().startswith(b'data_'):raise StudioError('RCSB did not return an mmCIF structure.')
    digest=hashlib.sha256(data).hexdigest();directory=runtime_root()/'objects/rcsb'/digest;directory.mkdir(parents=True,exist_ok=True)
    path=directory/f'{pdb_id}-assembly{assembly_id}.cif'
    if path.exists() and file_digest(path)!=digest:raise StudioError('Imported structure checksum mismatch.')
    if not path.exists():path.write_bytes(data)
    receipt=dict(provider='RCSB PDB',pdb_id=pdb_id,assembly_id=assembly_id,url=url,sha256=digest,retrieved_at=utc_now())
    if not (directory/'source.json').exists():atomic_json(directory/'source.json',receipt)
    else:receipt=json.loads((directory/'source.json').read_text())
    return dict(schema_version=1,artifact=import_artifact(str(path)),source=receipt,source_artifact=import_artifact(str(directory/'source.json')),
                next_action='Use target_inspect on the returned artifact to select exact chains/residues; inspect RCSB sequence-coordinate mappings before translating hotspots.')
