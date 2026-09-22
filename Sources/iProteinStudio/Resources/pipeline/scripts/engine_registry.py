"""Curated engine capabilities and adapter names; shipped code is the authority."""
import json
from pathlib import Path

_registry=json.loads(Path(__file__).with_suffix('.json').read_text())
if _registry.get('schema_version')!=1:raise ValueError('Unsupported engine registry')
def engines():
    import copy
    return copy.deepcopy(_registry['engines'])

def descriptor(engine):
    try:return dict(engines()[engine])
    except KeyError:raise ValueError('Unknown engine: '+str(engine)) from None

def predictors():return {k for k,v in engines().items() if 'structure' in v['capabilities']}
def scheduling_policy(engine):return descriptor(engine)['schedule']
def make_session(config,classes):
    name=descriptor(config['engine']).get('session')
    if name not in classes:raise ValueError('No validated resident adapter for '+config['engine'])
    return classes[name](config)


def pinned_installation(root,component,default):
    import os
    bindings=json.loads(os.environ.get('IPROTEINSTUDIO_RUNTIME_BINDINGS','{}'))
    if component not in bindings:return Path(default).resolve()
    item=bindings[component];base=Path(item['path'])
    from runtime_package import digest
    if digest(base/'runtime.json')!=item['manifest_sha256']:raise ValueError('Pinned runtime identity changed: '+component)
    return base
