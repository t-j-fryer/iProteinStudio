"""RFD4 uses the established resident adapters and their engine environments."""
import os
from pathlib import Path
from .contract import predictor_identity


def runtime_spec(root, predictor):
    root=Path(root); identity=predictor_identity(predictor)
    venv=root/'venvs'/('NanoHunter_'+identity['runtime'])
    env=dict(os.environ, PATH=str(venv/'bin')+os.pathsep+os.environ.get('PATH',''), VIRTUAL_ENV=str(venv))
    if identity['runtime']=='intellifold':
        env.update(KMP_USE_SHM='0', PYTORCH_ENABLE_MPS_FALLBACK='0',
                   OMP_NUM_THREADS=env.get('NANOHUNTER_INTELLIFOLD_OMP_NUM_THREADS','1'),
                   VECLIB_MAXIMUM_THREADS=env.get('NANOHUNTER_INTELLIFOLD_VECLIB_MAXIMUM_THREADS','1'))
    elif identity['runtime'].startswith('protenix'): env.pop('PYTORCH_ENABLE_MPS_FALLBACK',None)
    elif identity['runtime'] in ('esmfold2','openfold3_mlx'):env['PYTORCH_ENABLE_MPS_FALLBACK']='0'
    return venv/'bin/python', env


def search_runtime_spec(root, settings):
    python, env = runtime_spec(root, settings['predictor'])
    if settings['task'] == 'ligand' and settings['predictor'] != 'boltz':
        # Chemistry/export lives in the pinned RFD4 environment. ESMClient
        # still launches the resident model in its own pinned ESMFold2 runtime.
        venv = Path(root) / 'venvs/NanoHunter_rfd4'
        python = venv / 'bin/python'
        env.update(PATH=str(venv / 'bin') + os.pathsep + os.environ.get('PATH', ''),
                   VIRTUAL_ENV=str(venv))
    return python, env


def session_config(root, predictor, inputs, work, seed):
    import yaml
    identity=predictor_identity(predictor)
    msas=[item['protein'].get('msa','empty') for item in yaml.safe_load(Path(inputs).read_text())['sequences'] if 'protein' in item]
    args=[]
    if identity['engine']=='boltz':args=['--seed',str(seed),'--diffusion_samples','1']
    elif identity['engine']=='intellifold':args=['--seed',str(seed),'--num_diffusion_samples','1','--model',identity['model'],'--precision','no','--num_workers','0']
    return dict(root=str(root),engine=identity['engine'],model=identity['model'],engine_args=args,
                seed=str(seed),samples=1,use_msa=any(m!='empty' for m in msas),use_potentials=False,
                work_dir=str(work))


def prediction_files(predictions, identifier):
    predictions=Path(predictions)
    leaf=predictions/identifier/'pred_min'
    if (leaf/'model_0.cif').is_file() and (leaf/'confidence.json').is_file():
        return leaf/'model_0.cif', leaf/'confidence.json'
    structures=list(predictions.rglob('*_model_0.cif'))+list(predictions.rglob('*_model_0.pdb'))
    confidences=list(predictions.rglob('confidence_*_model_0.json'))
    if not structures and not confidences:
        structures=list(predictions.rglob(identifier+'_seed-*_sample-0.cif'))
        confidences=list(predictions.rglob(identifier+'_seed-*_sample-0_summary_confidences.json'))
    if len(structures)!=1 or len(confidences)!=1:raise ValueError('Predictor output cardinality mismatch.')
    return structures[0],confidences[0]
