"""Family-local fixed, sequential, greedy and beam search with durable ancestry.

Selection semantics follow Validation/experiments/rfd4_chain_b_budget_v1:
rank the current generation family-wide, stable ID tie-break, no elitism or
silent pruning. Every evaluated proposal remains a result, including losers.
"""
import json
import math
from pathlib import Path
from .contract import atomic, fixed, prediction_budget, select, seal, sha, verify


def execute(config, starts, engine, output, finalize=True):
    cfg = config['settings']
    output = Path(output)
    allrows = []
    policy = cfg['search']
    width = cfg['beam_width'] if policy == 'beam' else 1
    cycles = cfg['cycles'] if policy in ('iterative', 'greedy', 'beam') else 1
    proposals = 1 if policy in ('native', 'iterative') else cfg['proposals']
    # Same bounded wave policy as the qualified campaigns. Model and CPU worker
    # persist while each wave advances through its generations.
    for offset in range(0, len(starts), 25):
        group = starts[offset:offset+25]
        active = {r['family']: [r] for r in group}
        for cycle in range(1, cycles+1):
            for root in group:
                rows = []
                parents = [root] if policy == 'fixed' else active[root['family']]
                for parent_index, parent in enumerate(parents):
                    for proposal_index in range(proposals):
                        number = parent_index * proposals + proposal_index
                        identifier = f"{root['family']}_c{cycle:03d}_p{number:03d}"
                        proposal = dict(id=identifier, family=root['family'], cycle=cycle,
                                        parent_id=parent['id'], parent_structure_sha256=parent['structure_sha256'],
                                        sequence_seed=(root['seed'] * 100000 + cycle * 1000 + number) % (2**31),
                                        predictor_seed=42, policy=policy)
                        unit = output / 'candidates' / identifier
                        fixed(unit / 'proposal.json', proposal)
                        done = unit / 'completed.json'
                        if done.exists():
                            result = verify(done)
                            if result['proposal'] != proposal: raise ValueError('Saved candidate ancestry changed.')
                        else:
                            from .budget import checkpoint
                            checkpoint()
                            if sha(parent['structure']) != parent['structure_sha256']:
                                raise ValueError('The selected parent structure changed.')
                            result, artifacts = engine.evaluate(proposal, parent, unit, native=policy == 'native')
                            if not math.isfinite(result['score']): raise ValueError('Nonfinite candidate score.')
                            result = {**result, **proposal, 'proposal': proposal}
                            atomic(unit / 'result.json', result)
                            seal(done, result, [unit / 'proposal.json', unit / 'result.json', *artifacts], relative_root=output)
                        rows.append(result)
                        allrows.append(result)
                        atomic(output / 'progress.json', dict(stage='search', family=root['family'], cycle=cycle,
                                                             completed=len(allrows), total=prediction_budget(cfg)))
                chosen = select(rows, width if policy == 'beam' else 1)
                decision = dict(family=root['family'], cycle=cycle, metric='pbind + ligand_plddt/100' if cfg['task'] == 'ligand' else 'ipsae_min',
                                candidates=[r['id'] for r in rows], selected=[r['id'] for r in chosen],
                                policy=policy, elitism=False)
                fixed(output / 'decisions' / root['family'] / f'cycle_{cycle:03d}.json', decision)
                active[root['family']] = chosen
                print('DESIGN_SEARCH', root['family'], cycle, len(rows), flush=True)
    if finalize:
        if len(allrows) != prediction_budget(cfg): raise ValueError('Search ended with an incomplete candidate budget.')
        atomic(output / 'results.json', allrows)
        seal(output / 'search_completed.json', dict(predictions=len(allrows), families=len(starts)),
             [output / 'results.json'] + list((output / 'candidates').glob('*/completed.json'))
             + list((output / 'decisions').glob('*/*.json')))
    return allrows
