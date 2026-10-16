"""Bounded CPU proposal preparation, with safe overlap for independent Boltz units.

Two CPU samplers prepare the next eight parents while Boltz folds the current
chunk. Selection still occurs once over the complete stage. Sequence-scoring
shortlists retain their global barrier; stream-RNG backends retain one request.
"""
from concurrent.futures import ThreadPoolExecutor


def run(items, design, fold, *, overlap=False, screen=None, chunk_size=8):
    sequences, references, owners, predictions = {}, {}, {}, {}
    if not items:
        return sequences, references, owners, predictions
    chunks = [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]
    executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='nise-cpu')
    pending = []
    def submit(chunk):
        return [(item, executor.submit(design, item)) for item in chunk]
    try:
        pending = submit(chunks[0])
        for index in range(len(chunks)):
            current = {}
            for item, future in pending:
                values = future.result()
                if len(values) != len(item['names']):
                    raise RuntimeError('Proposal count differs from the recorded parent request')
                for name, sequence in zip(item['names'], values):
                    if name in sequences: raise ValueError('Duplicate proposal identity: ' + name)
                    current[name] = sequences[name] = sequence
                    references[name] = item['pdb']; owners[name] = item['owner']
            # Only one bounded chunk can run ahead. Seeds are per parent, never
            # based on completion order, thread identity or chunk membership.
            pending = submit(chunks[index + 1]) if index + 1 < len(chunks) else []
            if overlap and screen is None:
                predictions.update(fold(current))
        if screen is not None:
            sequences = screen(sequences, owners)
        if not overlap or screen is not None:
            predictions = fold(sequences)
        return sequences, references, owners, predictions
    finally:
        for _, future in pending: future.cancel()
        executor.shutdown(wait=True, cancel_futures=True)
