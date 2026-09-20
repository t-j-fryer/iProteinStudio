"""Experimental direct upstream parsing for the fixed sequence+SMILES contract.

The same upstream parser, dump methods and cloned CCD entries are used. Random
conformer generation remains upstream: output equivalence must therefore be
measured before this can be considered for production.
"""
def install(engine):
    import nesso.main as main
    from nesso.data.yaml_input import parse_yaml
    from nesso.data.types import Manifest
    if engine.ccd_cache is None:raise RuntimeError('CCD cache required')
    counts={'calls':0,'parser':'upstream parse_yaml, in owning process'}
    def preprocess(yaml_paths,mol_dir,ccd_pkl,structures_dir,records_dir,num_workers=1):
        if len(yaml_paths)!=1 or num_workers!=1 or ccd_pkl.resolve()!=engine.ccd_cache.path:
            raise RuntimeError('Experimental direct parser requires one Studio sequence+SMILES request')
        structures_dir.mkdir(parents=True,exist_ok=True);records_dir.mkdir(parents=True,exist_ok=True)
        struct,rec,_,_=parse_yaml(yaml_paths[0],mol_dir,ccd_dict=engine.ccd_cache.get())
        struct.dump(structures_dir/f'{rec.id}.npz');rec.dump(records_dir/f'{rec.id}.json')
        counts['calls']+=1
        return Manifest([rec]),[]
    main.preprocess_yamls=preprocess
    return counts
