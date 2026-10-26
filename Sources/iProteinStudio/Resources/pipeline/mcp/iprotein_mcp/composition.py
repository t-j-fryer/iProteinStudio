"""Compile explicit workflow recipes and engine/scaffold batches to existing plans."""
from __future__ import annotations
import copy,json,secrets
from contextvars import ContextVar
from pathlib import Path
from .common import StudioError,canonical_digest,project_root,validate_slug,validate_schema
from . import plans

PLAN_CONTEXT=ContextVar('studio_plan_context',default=None)
SCHEMAS=Path(__file__).resolve().parents[1]/'schemas'
ROUTES={
    'motif_beta':('motif-beta-v1.json','motif_beta'),
    'rfd4':('rfd4-v1.json','rfd4'),
    'prediction':('prediction-v1.json','prediction'),
    'protein_hunter':('iterative-design-v1.json','iterative_design'),
    'protein_hunter_batch':('iterative-batch-v1.json','iterative_design'),
    'ligand_nise':('nise-v1.json','nise'),
    'rfd3_denovo':('rfd3-v1.json','rfd3_protein_binder'),
    'rfd3_partial':('rfd3-v1.json','rfd3_partial_diffusion'),
    'rfd3_motif':('rfd3-v1.json','rfd3_motif_scaffolding')}

PIPELINE_SCHEMA={'type':'object','additionalProperties':False,'required':['schema_version','route','parameters'],
    'properties':{'schema_version':{'type':'integer','const':2},'route':{'enum':list(ROUTES)},
                  'parameters':{'type':'object'},'name':{'type':'string','minLength':1,'maxLength':120}}}

from .memory import memory_request, requested_policy

def pipeline_catalog():
    routes={}
    for name,(schema,guide) in ROUTES.items():
        routes[name]={'workflow_guide':guide,'parameters_schema':json.loads((SCHEMAS/schema).read_text())}
    return dict(schema_version=2,recipe_schema=PIPELINE_SCHEMA,routes=routes,
        stage_contracts={
            'rfd4':'Joint sequence/structure generation or imported structures → optional fixed/iterative/greedy/beam exploration → configured protein or ligand assessment; native diffusion rollouts are separate.',
            'protein_hunter':'Supported initialization → sequence design/refinement cycles → requested independent checks → optional ligand verification.',
            'rfd3_denovo':'Backbone generation → sequence assignment → configured prediction and assessment; ligand screening selects the explicit native route.',
            'ligand_nise':'Initial generator → proposal/geometry/selection stages → optional final checks.'},
        interpretation='Executable recipes bind complete existing workflow schemas. They do not execute arbitrary graphs; prototype v1 sample recipes must be explicitly rebound to a supported v2 route.')

@memory_request
def recipe_plan(recipe):
    validate_schema(recipe,PIPELINE_SCHEMA,'recipe')
    route=recipe['route'];parameters=copy.deepcopy(recipe['parameters'])
    validate_schema(parameters,json.loads((SCHEMAS/ROUTES[route][0]).read_text()),'recipe.parameters')
    context={'schema_version':2,'recipe':copy.deepcopy(recipe),'recipe_sha256':canonical_digest(recipe)}
    token=PLAN_CONTEXT.set(context)
    try:
        if route=='motif_beta':
            from .motif_beta import plan
            return plan(parameters)
        if route=='rfd4':
            from .rfd4 import plan
            return plan(parameters)
        if route=='prediction':return plans.prediction_plan(parameters)
        if route=='protein_hunter':return plans.iterative_plan(parameters)
        if route=='protein_hunter_batch':return iterative_batch_plan(parameters)
        if route=='ligand_nise':
            from .nise import nise_plan
            return nise_plan(parameters)
        mode={'rfd3_denovo':'deNovo','rfd3_partial':'partialDiffusion','rfd3_motif':'motifScaffolding'}[route]
        supplied=parameters.get('request',{}).get('design_mode',mode)
        if supplied!=mode:raise StudioError('Recipe route and requested RFdiffusion3 mode disagree.')
        return plans.rfd3_plan(parameters,mode)
    finally:PLAN_CONTEXT.reset(token)

def _option(arguments,flag,default=None):
    return arguments[arguments.index(flag)+1] if flag in arguments else default

@memory_request
def iterative_batch_plan(arguments):
    schema=json.loads((SCHEMAS/'iterative-batch-v1.json').read_text())
    validate_schema(arguments,schema)
    project=validate_slug(arguments['project']);workspace=project_root(project)
    name=validate_slug(arguments.get('run_name','batch-'+secrets.token_hex(4)))
    output=workspace/name
    if len(name) > 70: raise StudioError('Batch name must leave room for engine/scaffold suffixes (maximum 70 characters).')
    if output.exists():raise StudioError('Batch output already exists; resume the saved job or choose a new name.')
    base=copy.deepcopy(arguments['common']);base['project']=project
    shared=base['arguments']
    if '--predictor-seed' not in shared:
        shared += ['--predictor-seed',str(secrets.randbits(31))]
    forbidden={'--predictor','--model','--num-runs'}
    if forbidden.intersection(shared):raise StudioError('Batch engines and trajectory allocation supply predictor/model/num-runs; omit those from common arguments.')
    engines=arguments['engines'];scaffolds=arguments.get('scaffolds')
    total=arguments['trajectories_per_engine']
    if scaffolds:
        if _option(shared,'--workflow')!='nanobody':raise StudioError('Scaffold allocation requires the nanobody workflow.')
        if sum(s['trajectories'] for s in scaffolds)!=total:raise StudioError('Scaffold counts must sum to trajectories_per_engine.')
        if len({s['id'] for s in scaffolds})!=len(scaffolds):raise StudioError('Duplicate scaffold IDs.')
        if '--nanobody-cdr-ranges' in shared:raise StudioError('Use scaffold-specific CDR ranges, not shared ranges.')
        for scaffold in scaffolds:
            previous=0
            for span in scaffold['cdr_ranges'].split(','):
                start,end=map(int,span.split(':')[1].split('-'))
                if not previous < start <= end: raise StudioError('Scaffold CDR ranges must be ordered, positive and non-overlapping.')
                previous=end
        if 'template_path' in base:raise StudioError('Use scaffold-specific template_path, not a common template.')
    else:
        if not base.get('template_path'):raise StudioError('A common template_path is required without scaffold allocation.')
        scaffolds=[{'id':'none','trajectories':total,'template_path':base['template_path']}]
    engine_ids=[e['predictor']+(':'+e.get('model','v2-flash') if e['predictor']=='intellifold' else '') for e in engines]
    if len(set(engine_ids))!=len(engine_ids):raise StudioError('Duplicate engine choices.')
    requests=[]
    for engine_index,engine in enumerate(engines):
        if engine['predictor']!='intellifold' and 'model' in engine:raise StudioError('model applies only to IntelliFold.')
        for scaffold_index,scaffold in enumerate(scaffolds):
            request=copy.deepcopy(base)
            request.update(run_name=f'{name}-e{engine_index+1}-s{scaffold_index+1}',template_path=scaffold['template_path'])
            if 'cdr_ranges' in scaffold: request['arguments'] += ['--nanobody-cdr-ranges', scaffold['cdr_ranges']]
            request['arguments'] += ['--predictor',engine['predictor'],'--num-runs',str(scaffold['trajectories'])]
            if engine['predictor']=='intellifold':request['arguments'] += ['--model',engine.get('model','v2-flash')]
            # Exclude the same model family from independent checks, as the GUI does.
            if '--post-predictor' in request['arguments']:
                i=request['arguments'].index('--post-predictor')+1
                family=lambda v: 'intellifold' if v.startswith('intellifold') else 'esmfold2' if v.startswith('esmfold2') else 'boltz' if v.startswith('boltz') else 'protenix' if v.startswith('protenix') else v
                initial = _option(request['arguments'], '--initialization-predictor', engine['predictor'])
                excluded = {family(engine['predictor'])}
                if _option(request['arguments'], '--initialization-method', 'hallucination') == 'hallucination':
                    excluded.add(family(initial))
                choices=[]; seen=set()
                for p in request['arguments'][i].split(','):
                    if family(p) not in excluded and family(p) not in seen:
                        choices.append(p); seen.add(family(p))
                if not choices:raise StudioError('No independent checker remains for '+engine['predictor']+'; choose another checker or explicitly omit checks for the batch.')
                request['arguments'][i]=','.join(choices)
            plans._normalize_iterative_arguments(request['arguments'])
            requests.append((request,engine_ids[engine_index],scaffold))
    # Plan every child before execution, preserving exact shared settings and allocations.
    children=[];provenance=[]
    for request,engine,scaffold in requests:
        plan=plans.iterative_plan(request)
        children.append(dict(plan=plan,engine_id=engine,scaffold_id=scaffold['id'],trajectories=scaffold['trajectories']))
        provenance.extend(plan['provenance'])
    normalized=dict(output=str(output),workflow='iterative_batch',children=children,
        trajectories_per_engine=total,total_trajectories=total*len(engines),
        child_outputs=[c['plan']['normalized_request']['campaign'] for c in children],
        interpretation='Every engine receives the same scaffold allocation. Starting structures are generated independently unless inputs explicitly supply matched starts.')
    return plans._persist('iterative_batch',project,normalized,children[0]['plan']['command_preview'],
        'apple_gpu_exclusive',list({p['path']:p for p in provenance}.values()))
