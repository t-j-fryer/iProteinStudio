"""Domain-neutral, bounded assessment journal; no candidate generation or jobs.

Each caller-supplied artifact and assessment is preserved atomically. Eligibility
is recorded, never interpreted as an instruction to execute a scientific stage.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


class Journal:
    """max_attempts includes the original artifact, not just subsequent attempts."""
    def __init__(self, root, max_attempts):
        if type(max_attempts) is not int or not 1 <= max_attempts <= 1000:
            raise ValueError('max_attempts must be an integer from 1 to 1000')
        self.root = Path(root)
        self.root.mkdir(parents=True,exist_ok=True)
        self.policy = {'schema':1,'max_attempts':max_attempts}
        with self.locked():
            policy = self.root/'policy.json'
            if policy.exists():
                if json.loads(policy.read_bytes()) != self.policy:
                    raise ValueError('Recorded attempt budget cannot change on resume')
            else:
                temp = self.root/'.policy.part'
                self.write(temp,canonical(self.policy))
                os.replace(temp,policy)

    @contextmanager
    def locked(self):
        with (self.root/'.lock').open('a+b') as handle:
            fcntl.flock(handle,fcntl.LOCK_EX)
            yield

    @staticmethod
    def write(path,data):
        with path.open('wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())

    def read(self):
        if json.loads((self.root/'policy.json').read_bytes()) != self.policy:
            raise ValueError('Journal policy changed')
        records = []
        paths = sorted(self.root.glob('attempt_*'))
        for index,path in enumerate(paths):
            if path.name != f'attempt_{index:06d}' or not path.is_dir() or path.is_symlink():
                raise ValueError('Attempt history has a gap or invalid directory')
            receipt = json.loads((path/'receipt.json').read_bytes())
            for name in ('artifact.bin','assessment.json'):
                if digest((path/name).read_bytes()) != receipt['sha256'][name]:
                    raise ValueError(f'Preserved artifact changed: {path/name}')
            assessment = json.loads((path/'assessment.json').read_bytes())
            self.validate_assessment(assessment)
            if receipt['index'] != index or receipt['policy_sha256'] != digest(canonical(self.policy)):
                raise ValueError('Attempt metadata differs from the recorded policy')
            if records and records[-1]['assessment']['eligible']:
                raise ValueError('Attempt recorded after terminal eligibility')
            records.append({'index':index,'assessment':assessment,'receipt':receipt})
        if len(records) > self.policy['max_attempts']:
            raise ValueError('Attempt history exceeds its budget')
        return records

    @staticmethod
    def validate_assessment(value):
        if not isinstance(value,dict) or type(value.get('eligible')) is not bool:
            raise ValueError('Assessment must explicitly declare boolean eligibility')
        if not isinstance(value.get('reason'),str) or not value['reason'].strip():
            raise ValueError('Assessment needs an explicit reason')
        canonical(value)  # Reject NaN and nonserializable data before writing.

    def decision(self, records):
        count = len(records)
        eligible = bool(records and records[-1]['assessment']['eligible'])
        state = ('eligible' if eligible else 'budget_exhausted'
                 if count == self.policy['max_attempts'] else 'awaiting_assessment')
        return {'state':state,'eligible_for_next_stage':eligible,'recorded_attempts':count,
                'remaining_attempts':self.policy['max_attempts']-count,
                'selected_attempt':count-1 if eligible else None,
                'executes_next_stage':False}

    def status(self):
        with self.locked():
            return self.decision(self.read())

    def record(self, artifact, assessment):
        if not isinstance(artifact,bytes) or not artifact:
            raise ValueError('Provide a nonempty immutable artifact as bytes')
        self.validate_assessment(assessment)
        with self.locked():
            records = self.read()
            if self.decision(records)['state'] != 'awaiting_assessment':
                raise ValueError('Journal is terminal; existing attempts cannot be replaced')
            index = len(records)
            stage = Path(tempfile.mkdtemp(prefix='.staging-',dir=self.root))
            try:
                payloads = {'artifact.bin':artifact,'assessment.json':canonical(assessment)}
                receipt = {'schema':1,'index':index,'policy_sha256':digest(canonical(self.policy)),
                           'sha256':{name:digest(data) for name,data in payloads.items()}}
                for name,data in payloads.items():
                    self.write(stage/name,data)
                self.write(stage/'receipt.json',canonical(receipt))
                os.replace(stage,self.root/f'attempt_{index:06d}')
            finally:
                if stage.exists():
                    shutil.rmtree(stage)
            return self.decision(self.read())
