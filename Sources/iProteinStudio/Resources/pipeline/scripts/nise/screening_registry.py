"""Shared curated scoring adapter registry for app, CLI and MCP.

Legacy settings called 'nesso' remain decodable; engine defaults to NESSO.
No arbitrary module names or executable commands from user/catalog input.
"""
import importlib

import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from engine_registry import descriptor as engine_descriptor

def descriptor(engine='nesso'):
    d=engine_descriptor(engine)
    if 'sequence-ligand-screening' not in d['capabilities']:raise ValueError('Not a screening engine: '+str(engine))
    return d

def contract(engine='nesso'):return importlib.import_module(descriptor(engine)['contract'])
def client(engine='nesso'):
    d=descriptor(engine);return getattr(importlib.import_module(d['client']),d['class_name'])

def select(sequences,scores,count,engine='nesso',owners=None,total=None):
    module=contract(engine)
    if owners is not None and set(owners)!=set(sequences):raise ValueError('Screening lineage identities do not match candidates')
    assessed={n:module.placement_score(scores[n]) for n in sequences}
    ordered=sorted((n for n in sequences if assessed[n]['eligible']),key=lambda n:(-assessed[n]['score'],n))
    counts={};chosen=[]
    import re
    for name in ordered:
        if owners is None:
            match=re.fullmatch(r'c\d+_t(\d+)_n\d+_s\d+',name)
            if not match:raise ValueError('Invalid screening candidate identity: '+name)
            group=match[1]
        else:group=owners[name]
        if counts.get(group,0)>=count:continue
        chosen.append(name);counts[group]=counts.get(group,0)+1
    return chosen if total is None else chosen[:total]
