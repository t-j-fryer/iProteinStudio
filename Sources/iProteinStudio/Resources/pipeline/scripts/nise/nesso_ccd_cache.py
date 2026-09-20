"""Session-owned standard-amino-acid cache with independent mutable molecules."""
from pathlib import Path

class StandardAACache:
    def __init__(self, path, loader, clone):
        self.path = Path(path).resolve()
        self.loader = loader
        self.clone = clone
        self.identity = None
        self.molecules = None
        self.loads = 0
        self.requests = 0

    def get(self):
        stat = self.path.stat()
        identity = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
        if self.identity is not None and identity != self.identity:
            raise RuntimeError('NESSO CCD changed during the resident session; restart with a new plan')
        if self.molecules is None:
            self.molecules = self.loader(self.path)
            self.identity = identity
            self.loads += 1
        self.requests += 1
        return {name: None if molecule is None else self.clone(molecule)
                for name, molecule in self.molecules.items()}

    def receipt(self):
        return dict(policy='session-standard-aa-clones-v1', disk_loads=self.loads, requests=self.requests)
