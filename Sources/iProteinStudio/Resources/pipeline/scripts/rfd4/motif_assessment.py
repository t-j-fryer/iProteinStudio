"""Final untemplated apo/holo predictions; atomic receipts for each prediction."""
import json
import os
from pathlib import Path
import sys
from .contract import atomic, fixed, seal, sha, verify
from .motif_metrics import hit_verdict
from .motif_geometry import operation


class Predictor:
    def __init__(self,config):
        self.config=config;self.session=None;self.session_msa=None;self.root=Path(os.environ['NANOHUNTER_ROOT'])
        for path in (self.root/'rfd3_scripts',self.root/'rfd3_overlay/scripts'):sys.path.insert(0,str(path))

    def predict(self,yp,output):
        cfg=self.config['settings'];predictor=cfg['predictor']
        if predictor.startswith('esmfold2-'):
            from esmfold2_predict import run
            profile={'esmfold2-full-mlx':'full','esmfold2-fast-mlx':'fast','esmfold2-600-mlx':'600'}[predictor]
            self.session=run(self.root,profile,[yp],output,[42],1,session=self.session)
            leaf=output/yp.stem
            verify(leaf/'complete.json')
            return leaf/'pred_min/model_0.cif',leaf/'pred_min/confidence.json'
        from resident_predictor import make_session
        from .predictors import session_config,prediction_files
        session_settings=session_config(self.root,predictor,yp,Path(self.config['output'])/'motif_predictor_session',42)
        # Protenix fixes its MSA policy at model construction. An apo single
        # sequence and an aligned holo partner must not share that policy.
        if self.session is not None and session_settings['engine'].startswith('protenix') and self.session_msa!=session_settings['use_msa']:
            self.close()
        if self.session is None:
            self.session=make_session(session_settings);self.session_msa=session_settings['use_msa']
        self.session.predict(yp.parent,output,1)
        return prediction_files(output,yp.stem)

    def close(self):
        if self.session is not None:
            close=getattr(self.session,'close',None)
            if close:close()
            self.session=None
            import gc
            gc.collect()
            torch=sys.modules.get('torch')
            if torch is not None and torch.backends.mps.is_available():torch.mps.empty_cache()


def execute(config, first=False, predictor=None):
    import yaml
    from .search_engine import sequences
    output=Path(config['output']);cfg=config['settings'];policy=cfg['motif_assessment']
    reference=json.loads(Path(config['motif_reference']).read_text());context=config['motif_context']
    starts=json.loads((output/'generated.json').read_text());starts=starts[:1] if first else starts
    owned=predictor is None;predictor=predictor or Predictor(config);allrows=[];family_receipts=[]
    try:
        for parent in starts:
            if sha(parent['structure'])!=parent['structure_sha256']:raise ValueError('Generated motif structure changed.')
            mapped,mapping_artifacts=operation(Path(os.environ['NANOHUNTER_ROOT']),output/'motif_predictions'/parent['id']/'mapping',parent['native_structure'],'map',reference=reference)
            source_sequences=sequences(parent['structure']);targets=config.get('target_sequences',{})
            if set(source_sequences)!={'A',*targets} or any(source_sequences[c]!=s for c,s in targets.items()):
                raise ValueError('Generated motif/partner chain identities differ from the frozen request.')
            modes={};receipts=[]
            for mode in ('apo','holo'):
                if not policy[mode]:continue
                unit=output/'motif_predictions'/parent['id']/mode;unit.mkdir(parents=True,exist_ok=True)
                identity=dict(parent_sha256=parent['structure_sha256'],native_sha256=sha(parent['native_structure']),reference_sha256=sha(config['motif_reference']),mode=mode,predictor=cfg['predictor'],seed=42,policy=policy)
                fixed(unit/'identity.json',identity);done=unit/'completed.json'
                if done.exists():modes[mode]=verify(done);receipts.append(done);continue
                from .budget import checkpoint
                checkpoint()
                chains={'A':source_sequences['A'],**(targets if mode=='holo' else {})}
                msa='empty' if cfg['predictor'] in ('esmfold2-fast-mlx','esmfold2-600-mlx') else cfg['target_msa']
                document=dict(version=1,sequences=[dict(protein=dict(id=c,sequence=s,msa='empty' if c=='A' else config.get('target_msas',{}).get(c,msa))) for c,s in chains.items()])
                if mode=='holo':
                    from .mixed_target import add_prediction_ligands
                    add_prediction_ligands(document,config)
                inputs=unit/'inputs';inputs.mkdir(exist_ok=True);yp=inputs/(parent['id']+'_'+mode+'.yaml')
                text=yaml.safe_dump(document,sort_keys=False)
                if yp.exists() and yp.read_text()!=text:raise ValueError('Saved motif assessment input changed.')
                yp.write_text(text)
                raw,confidence=predictor.predict(yp,unit/'predictions')
                structure=raw;artifacts=[p for p in (unit/'predictions').rglob('*') if p.is_file()]
                if mode=='holo' and config.get('target_ligands'):
                    from .mixed_target import context_operation
                    checked=context_operation(Path(os.environ['NANOHUNTER_ROOT']),config,raw,unit/'assembly.cif','assessment',predictor=cfg['predictor'])
                    structure=Path(checked['structure']);artifacts += [structure,structure.with_suffix('.atom_map.json'),*checked['operation_artifacts']]
                    assembly=checked['assembly_audit']
                else: assembly=None
                if sequences(structure)!=chains:raise ValueError('Motif assessment changed the supplied protein sequences.')
                measured,geometry_artifacts=operation(Path(os.environ['NANOHUNTER_ROOT']),unit/'geometry',structure,'score',mapped=mapped,context=context,fix_sequence=cfg['motif']['fix_sequence'],holo=mode=='holo')
                result=dict(**measured,mode=mode,structure=str(structure),structure_sha256=sha(structure),confidence=str(confidence),engine=cfg['predictor'],sequence=chains['A'],sequences=chains,assembly_audit=assembly)
                atomic(unit/'metrics.json',result)
                seal(done,result,[unit/'identity.json',yp,raw,confidence,unit/'metrics.json',*artifacts,*mapping_artifacts,*geometry_artifacts])
                modes[mode]=result;receipts.append(done)
            verdict=hit_verdict(modes,policy)
            if verdict is not None and any(r.get('assembly_audit') and not r['assembly_audit']['passed'] for r in modes.values()):verdict=False
            for mode,result in modes.items():
                identifier=parent['id']+'_'+mode;unit=output/'candidates'/identifier
                metrics={k:result[k] for k in ('motif_rmsd_angstrom','partner_aligned_motif_rmsd_angstrom') if k in result}
                row=dict(**result,id=identifier,family=parent['family'],parent_id=parent['id'],cycle=1,metrics=metrics,
                         motif_mapping={a['source_residue']:a['chain']+str(a['position']) for a in mapped},
                         score_role='untemplated_motif_assessment',assessment_mode=mode,hit_filter_passed=verdict,
                         hit_filter_failures=[] if verdict is not False else ['One or more requested apo/holo RMSD or assembly integrity gates failed.'],
                         hit_filter_cutoffs=policy,hit_filter_scope='All requested modes; source motif shape plus optional partner-aligned placement. Computational criteria, not binding or function.')
                fixed(unit/'result.json',row)
                seal(unit/'completed.json',row,[unit/'result.json',*receipts]);family_receipts.append(unit/'completed.json');allrows.append(row)
            atomic(output/'progress.json',dict(stage='motif assessment',completed=len(allrows),total=len(starts)*sum(policy[k] for k in ('apo','holo'))))
        if not first:
            atomic(output/'results.json',allrows)
            seal(output/'motif_assessment_completed.json',dict(assessments=len(allrows)),[output/'results.json',*family_receipts])
        return allrows
    finally:
        if owned:predictor.close()
