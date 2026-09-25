"""Observational, stdlib-only progress for Studio-managed engine processes.

Never inspect tensors, synchronize devices, change arguments, consume randomness,
or turn a host return into a claim that asynchronous GPU work has completed.
Hooks are installed lazily: unavailable engines are never imported for telemetry.
"""
from __future__ import annotations

import functools
import importlib.abc
import os
from pathlib import Path
import sys
import threading
import time

# Module -> (engine, class, method, stage, log every N calls).
# Counts are process-local CALL counts, deliberately not diffusion-step estimates:
# guidance, chunking and batching can call a denoiser more than once per step.
HOOKS = {
    'runner.inference': [
        ('protenix', 'InferenceRunner', '__init__', 'loading', 1),
        ('protenix', 'InferenceRunner', 'predict', 'prediction', 1)],
    'protenix.model.protenix': [('protenix', 'Protenix', '__init__', 'model_initialization', 1)],
    'protenix.model.modules.pairformer': [
        ('protenix', 'TemplateEmbedder', 'forward', 'template_embedding', 1),
        ('protenix', 'MSAModule', 'forward', 'msa', 1),
        ('protenix', 'PairformerStack', 'forward', 'pairformer', 1)],
    'protenix.model.modules.diffusion': [('protenix', 'DiffusionModule', 'forward', 'denoising', 25)],
    'boltz.model.models.boltz2': [('boltz2', 'Boltz2', 'predict_step', 'prediction_batch', 1)],
    'boltz.model.layers.pairformer': [('boltz2', 'PairformerModule', 'forward', 'pairformer', 1)],
    'boltz.model.modules.trunkv2': [('boltz2', 'MSAModule', 'forward', 'msa', 1)],
    'boltz.model.modules.diffusionv2': [
        ('boltz2', 'AtomDiffusion', 'sample', 'diffusion_sampling', 1),
        ('boltz2', 'DiffusionModule', 'forward', 'denoising', 25)],
    'boltz.model.modules.confidencev2': [('boltz2', 'ConfidenceModule', 'forward', 'confidence', 1)],
    'intellifold.openfold.model.model': [
        ('intellifold', 'IntelliFold', 'forward', 'prediction', 1),
        ('intellifold', 'IntelliFold', 'sample_diffusion', 'diffusion_sampling', 1),
        ('intellifold', 'IntelliFold', 'diffusion_edm_forward', 'denoising', 25)],
    'intellifold.openfold.model.backbone': [('intellifold', 'BackboneTrunk', 'iteration', 'recycle', 1)],
    'openfold3.projects.of3_all_atom.model': [
        ('openfold3', 'OpenFold3', 'forward', 'prediction', 1),
        ('openfold3', 'OpenFold3', 'run_trunk', 'trunk', 1)],
    'openfold3.core.model.structure.diffusion_module': [
        ('openfold3', 'SampleDiffusion', 'forward', 'diffusion_sampling', 1),
        ('openfold3', 'DiffusionModule', 'forward', 'denoising', 25)],
    'sampler': [('rfd3', 'Sampler', 'generate', 'backbone_batch', 1)],
    'rfd3_mlx': [('rfd3', 'DiffusionModule', '__call__', 'denoising', 20)],
    'nesso.model.models.nesso1': [('nesso', 'Nesso1', 'predict_step', 'scoring', 1)],
    'nesso.model.layers.pairformer': [('nesso', 'PairformerNoSeqModule', 'forward', 'pairformer', 1)],
    'transformers.models.esm.modeling_esm': [('esm', 'EsmModel', 'forward', 'embedding_batch', 1)],
    'esm.model.esm2': [('esm', 'ESM2', 'forward', 'embedding_batch', 1)],
    'models.net': [('psichic', 'net', 'forward', 'graph_batch', 1)],
    'model_utils': [('mpnn', 'ProteinMPNN', 'sample', 'sequence_sampling', 1)],
    'utils.model': [('lasermpnn', 'LASErMPNN', 'sample', 'sequence_sampling', 1)],
    'utils.model_ligandmpnn': [('lasermpnn', 'LigandMPNN', 'sample', 'sequence_sampling', 1)],
    'antifold.esm.inverse_folding.gvp_transformer': [('antifold', 'GVPTransformerModel', 'forward', 'sequence_scoring', 1)],
}


def emit(engine, event, stage, **fields):
    """One bounded append, including to the job log when stderr is a child log."""
    def clean(value):
        return str(value).replace('|', '/').replace('\n', ' ').replace('\r', ' ')[:160]
    fields = dict(engine=engine, event=event, stage=stage, pid=os.getpid(),
                  utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), **fields)
    line = ('IPROTEINSTUDIO_PROGRESS|' + '|'.join(f'{k}={clean(v)}' for k, v in fields.items()) + '\n').encode()
    try:
        os.write(2, line)
    except OSError:
        pass  # Telemetry cannot turn a successful scientific call into a failure.
    target = os.environ.get('IPROTEINSTUDIO_PROGRESS_LOG')
    if target:
        try:
            dest = os.stat(target)
            source = os.fstat(2)
            if (dest.st_dev, dest.st_ino) == (source.st_dev, source.st_ino):
                return
        except OSError:
            pass
        try:
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(fd, line)
            finally:
                os.close(fd)
        except OSError:
            pass


class Reporter:
    def __init__(self, interval=30):
        self.interval = interval
        self.lock = threading.Lock()
        self.active = {}
        self.counts = {}
        self.serial = 0
        self.last_progress = time.monotonic()
        self.stop = threading.Event()
        self.thread = None

    def enter(self, engine, stage, every):
        now = time.monotonic()
        with self.lock:
            key = (engine, stage)
            count = self.counts.get(key, 0) + 1
            self.counts[key] = count
            self.serial += 1
            token = self.serial
            visible = count == 1 or count % every == 0
            self.active[token] = (engine, stage, count, now, visible)
            self.last_progress = now
            if self.thread is None:
                self.thread = threading.Thread(target=self._heartbeats, daemon=True,
                                               name='studio-progress')
                self.thread.start()
        if visible:
            emit(engine, 'host_enter', stage, call=count, operation=token)
        return token

    def leave(self, token, failed):
        now = time.monotonic()
        with self.lock:
            engine, stage, count, start, visible = self.active.pop(token)
            self.last_progress = now
        if visible or failed:
            emit(engine, 'host_error' if failed else 'host_return', stage,
                 call=count, operation=token, elapsed_s=f'{now-start:.1f}',
                 gpu_completion='not_measured')

    def heartbeat(self):
        now = time.monotonic()
        with self.lock:
            if not self.active:
                return
            engine, stage, count, start, _ = self.active[max(self.active)]
            since = now - self.last_progress
        emit(engine, 'heartbeat', stage, call=count, elapsed_s=f'{now-start:.1f}',
             since_host_progress_s=f'{since:.1f}', compute_progress='unknown')

    def _heartbeats(self):
        while not self.stop.wait(self.interval):
            self.heartbeat()


_reporter = None


def reporter():
    global _reporter
    if _reporter is None:
        _reporter = Reporter()
    return _reporter


def _after_fork():
    global _reporter
    _reporter = None  # Never reuse an inherited locked mutex or vanished thread.


if hasattr(os, 'register_at_fork'):
    os.register_at_fork(after_in_child=_after_fork)


def wrap(owner, method, engine, stage, every=1):
    original = getattr(owner, method, None)
    if original is None or not callable(original):
        return False
    if getattr(original, '_studio_progress', False):
        return True

    @functools.wraps(original)
    def observed(*args, **kwargs):
        log = reporter()
        token = log.enter(engine, stage, every)
        failed = True
        try:
            value = original(*args, **kwargs)
            failed = False
            return value
        finally:
            log.leave(token, failed)

    observed._studio_progress = True
    setattr(owner, method, observed)
    return True


def instrument(module):
    for engine, cls, method, stage, every in HOOKS.get(module.__name__, ()):
        owner = getattr(module, cls, None)
        if owner is None or not wrap(owner, method, engine, stage, every):
            emit(engine, 'hook_unavailable', stage, hook=f'{module.__name__}.{cls}.{method}')


class Loader:
    def __init__(self, original):
        self.original = original

    def create_module(self, spec):
        create = getattr(self.original, 'create_module', None)
        return create(spec) if create else None

    def exec_module(self, module):
        self.original.exec_module(module)
        instrument(module)

    def __getattr__(self, name):
        return getattr(self.original, name)


class Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname not in HOOKS:
            return None
        # Preserve other registered finders (including editable-install finders).
        for finder in tuple(sys.meta_path):
            if finder is self:
                continue
            find = getattr(finder, 'find_spec', None)
            spec = find(fullname, path, target) if find else None
            if spec is not None:
                if spec.loader is not None and hasattr(spec.loader, 'exec_module'):
                    spec.loader = Loader(spec.loader)
                return spec
        return None


def install():
    if any(isinstance(f, Finder) for f in sys.meta_path):
        return
    sys.meta_path.insert(0, Finder())
    for name in HOOKS:
        module = sys.modules.get(name)
        if module is not None:
            instrument(module)


def environment(env, scripts, job_log=None):
    """Opt in only managed subprocesses, using their retained pipeline code."""
    result = dict(env)
    if result.get('IPROTEINSTUDIO_PROGRESS') == '0':
        return result
    bootstrap = Path(scripts) / 'progress_bootstrap'
    if not (bootstrap / 'sitecustomize.py').is_file():
        return result  # Old immutable jobs retain their old logging behaviour.
    result['IPROTEINSTUDIO_PROGRESS'] = '1'
    result['PYTHONUNBUFFERED'] = '1'
    entries = [str(bootstrap), str(Path(scripts))]
    entries += [p for p in result.get('PYTHONPATH', '').split(os.pathsep) if p and p not in entries]
    result['PYTHONPATH'] = os.pathsep.join(entries)
    if job_log is not None:
        result['IPROTEINSTUDIO_PROGRESS_LOG'] = str(job_log)
    return result
