"""Bounded CPU workers and content-addressed receipts for NISE atom checks."""
import concurrent.futures as futures
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import time

THREAD_ENV = ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS')


def _sysctl(key, fallback):
    try:
        return int(subprocess.check_output(['/usr/sbin/sysctl','-n',key], stderr=subprocess.DEVNULL, timeout=2))
    except (OSError, ValueError, subprocess.SubprocessError):
        return fallback


def worker_count(requested=0):
    # Across-structure processes; each numerical library and KD-tree uses one
    # thread. Leave a performance core for the UI/broker and bound worst-case
    # grid memory alongside resident predictor weights. Overrides cannot exceed
    # the memory/CPU safety bound.
    cpus = _sysctl('hw.perflevel0.physicalcpu', os.cpu_count() or 1)
    memory = _sysctl('hw.memsize', 8 * 1024**3)
    limit = max(1, min(max(1, cpus-1), memory // (4 * 1024**3), 8))
    return min(requested, limit) if requested else limit


def measure_task(task):
    from atom_geometry import measure
    path, settings, manifest = task
    start = time.monotonic()
    result = measure(path, settings, manifest)
    result['geometry_seconds'] = time.monotonic()-start
    return result


class GeometryExecutor:
    def __init__(self, output, settings, manifest):
        from biotin_exit import source_signature
        import numpy, scipy, gemmi
        from rdkit import rdBase
        self.root = Path(output) / 'geometry_receipts'
        self.root.mkdir(parents=True, exist_ok=True)
        self.settings = {k:settings.get(k) for k in ('hotspot_atoms','exposed_atoms','hotspot_distance','exposure_min_fraction')}
        self.settings['exposure_mode'] = settings.get('exposure_mode','sasa')
        self.manifest = manifest
        self.workers = worker_count(settings.get('geometry_workers',0))
        self.pool = None
        self.provenance = dict(code_sha256=source_signature(), numpy=numpy.__version__, scipy=scipy.__version__,
                               gemmi=gemmi.__version__, rdkit=rdBase.rdkitVersion)

    def _pool(self):
        if self.pool is None:
            self.pool = futures.ProcessPoolExecutor(max_workers=self.workers,
                mp_context=multiprocessing.get_context('spawn'))
        return self.pool

    def close(self, cancel=False):
        if self.pool is not None:
            if cancel:
                # Python 3.11 has no public terminate_workers; terminate only
                # children owned by this executor, never prediction processes.
                for process in list((self.pool._processes or {}).values()):
                    process.terminate()
            self.pool.shutdown(wait=True, cancel_futures=True)
            self.pool = None

    def check(self, predictions):
        from runtime import atomic, digest
        results, todo = {}, []
        for name,pred in predictions.items():
            specification = dict(structure_sha256=digest(pred.pdb), settings=self.settings,
                                 manifest=self.manifest, implementation=self.provenance)
            key = hashlib.sha256(json.dumps(specification, sort_keys=True).encode()).hexdigest()
            receipt = self.root / (key+'.json')
            if receipt.exists():
                saved = json.loads(receipt.read_text())
                if saved['input'] != specification:
                    raise RuntimeError('Geometry checkpoint input mismatch')
                payload = saved['result']
                if hashlib.sha256(json.dumps(payload,sort_keys=True,allow_nan=False).encode()).hexdigest() != saved['result_sha256']:
                    raise RuntimeError('Geometry checkpoint result changed')
                results[name] = payload
            else:
                todo.append((name, pred, specification, receipt))
        start = time.monotonic()
        def save(item, result):
            name,pred,specification,receipt = item
            # The worker reads the file; detect any concurrent replacement.
            if digest(pred.pdb) != specification['structure_sha256']:
                raise RuntimeError('Structure changed during geometry evaluation')
            checksum = hashlib.sha256(json.dumps(result,sort_keys=True,allow_nan=False).encode()).hexdigest()
            atomic(receipt, dict(input=specification,result=result,result_sha256=checksum))
            results[name] = result
        try:
            # Spawn inherits these limits before NumPy/SciPy import, including
            # imports made while loading the main module. Restore parent env.
            old = {k:os.environ.get(k) for k in THREAD_ENV}
            try:
                for k in THREAD_ENV: os.environ[k]='1'
                pending = {}; remaining = iter(todo)
                pool = self._pool() if todo else None
                def submit():
                    item = next(remaining, None)
                    if item is None: return False
                    pending[pool.submit(measure_task,(str(item[1].pdb),self.settings,self.manifest))] = item
                    return True
                for _ in range(self.workers):
                    if not submit():break
                while pending:
                    done,_ = futures.wait(pending,return_when=futures.FIRST_COMPLETED)
                    for future in done:
                        save(pending.pop(future),future.result())
                        submit()
            finally:
                for k,v in old.items():
                    if v is None:os.environ.pop(k,None)
                    else:os.environ[k]=v
        except BaseException:
            self.close(cancel=True)
            raise
        atomic(self.root/'latest_batch.json', dict(count=len(predictions), computed=len(todo),
               reused=len(predictions)-len(todo), workers=self.workers, library_threads=1,
               elapsed_seconds=time.monotonic()-start, implementation=self.provenance))
        return results
