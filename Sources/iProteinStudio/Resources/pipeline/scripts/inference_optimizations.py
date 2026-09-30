"""Scoped runtime improvements qualified in Lab Book 0229/0230.

No package files are edited. Caches have session ownership; model residency is
limited to the model objects registered by that inference session.
"""
import atexit
import random
import types
from pathlib import Path


class ResidentModels:
    def __init__(self):
        from pytorch_lightning.strategies.strategy import Strategy
        self.strategy = Strategy
        self.original = Strategy.teardown
        self.models = []
        self.closed = False
        def teardown(strategy):
            module = strategy.lightning_module
            if not any(module is model for model in self.models) or strategy.optimizers:
                return self.original(strategy)
            had_cpu = 'cpu' in module.__dict__
            prior = module.__dict__.get('cpu')
            module.cpu = lambda: module
            try:
                return self.original(strategy)
            finally:
                if had_cpu:
                    module.cpu = prior
                else:
                    del module.cpu
        self.patch = teardown
        Strategy.teardown = teardown
        atexit.register(self.close)

    def add(self, model):
        if not any(model is existing for existing in self.models):
            self.models.append(model)
        return model

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.strategy.teardown is self.patch:
            self.strategy.teardown = self.original
        for model in self.models:
            model.cpu()
        self.models.clear()
        atexit.unregister(self.close)


class ChemicalCache:
    """Cache only IntelliFold's trusted CCD pickle, never sequence features."""
    def __init__(self):
        import intellifold.data.inference.data_tools as data_tools
        self.module = data_tools
        self.original = data_tools.pickle
        self.cache = {}
        def load(file, *args, **kwargs):
            name = Path(file.name)
            if name.name != 'ccd_v2.pkl':
                return self.original.load(file, *args, **kwargs)
            stat = name.stat()
            key = (str(name.resolve()), stat.st_size, stat.st_mtime_ns)
            if key not in self.cache:
                self.cache.clear()  # bounded to one chemical database
                self.cache[key] = self.original.load(file, *args, **kwargs)
            return self.cache[key]
        self.proxy = types.SimpleNamespace(**vars(self.original))
        self.proxy.load = load
        data_tools.pickle = self.proxy
        atexit.register(self.close)

    def close(self):
        if self.module.pickle is self.proxy:
            self.module.pickle = self.original
        self.cache.clear()
        atexit.unregister(self.close)


class OpenFoldPreparation:
    """Single-query loader avoids spawn overhead and preserves worker-zero RNG.

    Multi-query directory batches retain the upstream worker policy: the paired
    zero-worker equivalence experiment covered one query per resident request.
    """
    def __init__(self, runner_class):
        import numpy as np
        import torch
        from openfold3.core.data.framework.single_datasets.inference import InferenceDataset
        from openfold3.core.data.framework.data_module import worker_init_function_with_data_seed
        self.runner_class = runner_class
        self.dataset = InferenceDataset
        self.original_run = runner_class.run
        self.original_getitem = InferenceDataset.__getitem__
        self.original_getpositions = None
        self.seed = None
        def run(runner, queries):
            self.seed = runner.data_module_args.data_seed if len(queries.queries) == 1 else None
            workers = runner.data_module_args.num_workers
            if self.seed is not None:
                runner.data_module_args.num_workers = 0
            try:
                return self.original_run(runner, queries)
            finally:
                runner.data_module_args.num_workers = workers
                self.seed = None
        def getitem(dataset, index):
            if self.seed is None:
                return self.original_getitem(dataset, index)
            state = (random.getstate(), np.random.get_state(), torch.get_rng_state())
            try:
                worker_init_function_with_data_seed(0, self.seed, rank=0)
                return self.original_getitem(dataset, index)
            finally:
                random.setstate(state[0]); np.random.set_state(state[1]); torch.set_rng_state(state[2])
        runner_class.run = run
        InferenceDataset.__getitem__ = getitem
        # The source-checked conversion preserves atom order and float32 casting.
        from openfold_positions import install
        self.restore_positions = install()

    def close(self):
        self.runner_class.run = self.original_run
        self.dataset.__getitem__ = self.original_getitem
        self.restore_positions()
