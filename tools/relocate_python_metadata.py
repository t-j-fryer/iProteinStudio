"""Remove installation-machine paths from standalone CPython metadata."""
import ast,json,pprint,re
from pathlib import Path

def relocate(python):
    python=Path(python);changed=[];removed=[]
    for path in python.glob('lib/python*/_sysconfigdata_*.py'):
        tree=ast.parse(path.read_text());values=None
        for node in tree.body:
            if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='build_time_vars' for t in node.targets):values=ast.literal_eval(node.value)
        if values is None:raise ValueError('Unknown CPython sysconfig format')
        prefixes={values[k] for k in ('prefix','exec_prefix') if isinstance(values.get(k),str) and values[k].startswith('/')}
        for key,value in values.items():
            if isinstance(value,str):
                for prefix in sorted(prefixes,key=len,reverse=True):value=value.replace(prefix,'__STUDIO_PYTHON_PREFIX__')
                values[key]=value
        path.write_text('# Relocatable standalone CPython installation metadata.\nimport sys as _studio_sys\nbuild_time_vars = '+pprint.pformat(values,sort_dicts=True)+'\nfor _key, _value in tuple(build_time_vars.items()):\n    if isinstance(_value, str):\n        build_time_vars[_key] = _value.replace("__STUDIO_PYTHON_PREFIX__", _studio_sys.base_prefix)\ndel _key, _value, _studio_sys\n')
        changed.append(path)
        for config in python.glob('bin/python*-config'):
            if config.is_symlink():continue
            text=config.read_text()
            for prefix in prefixes:text=text.replace(prefix,'${prefix}')
            text=re.sub(r'^prefix=.*$', 'prefix="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"',text,flags=re.M)
            config.write_text(text);changed.append(config)
        for pc in python.glob('lib/pkgconfig/*.pc'):
            if pc.is_symlink():continue
            text=pc.read_text()
            for prefix in prefixes:text=text.replace(prefix,'${prefix}')
            text=re.sub(r'^prefix=.*$', 'prefix=${pcfiledir}/../..',text,flags=re.M);pc.write_text(text);changed.append(pc)
    for path in python.glob('lib/python*/site-packages/*.dist-info/direct_url.json'):
        data=json.loads(path.read_text())
        if data.get('url','').startswith('file:'):path.unlink();removed.append(path)
    return changed,removed
