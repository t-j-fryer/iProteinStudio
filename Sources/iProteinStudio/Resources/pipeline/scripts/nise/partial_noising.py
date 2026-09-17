"""Experimental ligand-local sequence masking, not coordinate diffusion.

Masked scores only choose an intermediate backbone. Only complete, re-designed
and re-folded amino-acid sequences may enter the trajectory beam or best outputs.
"""
import copy
from dataclasses import asdict
import hashlib
import math
from pathlib import Path
import random
import re

import numpy as np
from runtime import atomic, digest


def pocket_positions(pdb, sequence, radius):
    """Sequence indices (zero-based), selected by any binder/ligand heavy atoms."""
    import gemmi
    structure = gemmi.read_structure(str(pdb))
    if len(structure) != 1:
        raise ValueError('Partial noising requires one predicted model')
    protein = structure[0].find_chain('A'); ligand = structure[0].find_chain('B')
    if protein is None or ligand is None:
        raise ValueError('Partial noising requires binder A and ligand B')
    residues = [r for r in protein if r.find_atom('CA', '*')]
    observed = ''.join(gemmi.find_tabulated_residue(r.name).one_letter_code.upper() for r in residues)
    if not re.fullmatch('[ACDEFGHIKLMNPQRSTVWY]+', sequence) or sequence != observed:
        raise ValueError('Partial-noising parent must match its complete amino-acid sequence')
    def heavy(residues):
        xyz = np.array([[a.pos.x, a.pos.y, a.pos.z] for r in residues for a in r if not a.element.is_hydrogen])
        if not len(xyz) or not np.isfinite(xyz).all():
            raise ValueError('Missing or invalid heavy-atom coordinates for partial noising')
        return xyz
    lig = heavy(ligand)
    positions = [i for i, residue in enumerate(residues)
                 if np.min(np.sum((heavy([residue])[:, None, :] - lig[None, :, :]) ** 2, axis=-1)) <= radius ** 2]
    return positions, [str(r.seqid) for r in residues]


def mask_proposals(backend, parent, directory, args, cycle, tid):
    directory = Path(directory)
    spec = dict(parent=parent.name, pdb_sha256=digest(parent.pdb), sequence=parent.sequence,
                radius=args.noise_radius, percent=args.noise_percent, count=args.noise_predictions,
                seed=args.seed, cycle=cycle, trajectory=tid, protocol='ligand-heavy-atom-x-mask-v1')
    receipt = directory / 'masks.json'
    saved = backend.journal.load(receipt, spec)
    if saved is not None:
        return saved
    positions, labels = pocket_positions(parent.pdb, parent.sequence, args.noise_radius)
    proposals = []
    count = min(len(positions), max(1, int(math.floor(len(positions) * args.noise_percent / 100 + .5))))
    base_seed = int.from_bytes(hashlib.sha256(f'{args.seed}:{cycle}:{tid}:mask'.encode()).digest()[:4], 'big') % 2147483648
    for i in range(args.noise_predictions if positions else 0):
        seed = (base_seed + i) % 2147483648
        selected = sorted(random.Random(seed).sample(positions, count))
        sequence = list(parent.sequence)
        for index in selected:
            sequence[index] = 'X'
        proposals.append(dict(name=f'c{cycle:02d}_t{tid}_mask_s{i}', sequence=''.join(sequence), seed=seed,
                              masked_positions=[i + 1 for i in selected], masked_residue_ids=[labels[i] for i in selected]))
    result = dict(eligible_positions=[i + 1 for i in positions], eligible_residue_ids=[labels[i] for i in positions],
                  masked_count=count if positions else 0, proposals=proposals,
                  status='ready' if positions else 'no_residues_in_radius')
    backend.journal.save(receipt, spec, result)
    return result


def repair_input(backend, source, destination):
    """Keep the original prediction immutable; repair only chain-A UNK labels."""
    destination = Path(destination)
    receipt = destination.with_suffix('.json')
    spec = dict(source_sha256=digest(source), protocol='binder-unk-to-ala-for-inverse-folding-v1')
    if backend.journal.load(receipt, spec) is None:
        lines = []
        for line in Path(source).read_text().splitlines(keepends=True):
            if line.startswith(('ATOM  ', 'HETATM')) and line[21:22] == 'A' and line[17:20] == 'UNK':
                line = line[:17] + 'ALA' + line[20:]
            lines.append(line)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp = destination.with_suffix('.pdb.part'); temp.write_text(''.join(lines)); temp.replace(destination)
        backend.journal.save(receipt, spec, str(destination), [destination])
    return str(destination)


def run_branch(trajectories, out, smiles, args, cycle, lig_thresh, writer):
    # Import lazily: the main search uses this module only for enabled cycles.
    import nise_run as search
    backend = args.backend
    directory = Path(out) / f'cycle{cycle:02d}' / 'partial_noising'
    parents = {t['tid']: sorted(t['current'], key=lambda n: (-n.score, n.name))[0] for t in trajectories}
    sequences, refs, owners, seeds, records = {}, {}, {}, {}, {}
    for tid, parent in parents.items():
        record = mask_proposals(backend, parent, directory / f'T{tid}', args, cycle, tid)
        records[str(tid)] = dict(parent=asdict(parent), masks=record, selected_backbone=None, advanced=[])
        if not record['proposals']:
            search.log(f'  cycle {cycle} T{tid}: no residues in noising radius; reserved branch places stay empty')
        for proposal in record['proposals']:
            name = proposal['name']; sequences[name] = proposal['sequence']; refs[name] = parent.pdb
            owners[name] = tid; seeds[name] = proposal['seed']
    masked_args = copy.copy(args)
    masked_args.prediction_seeds = seeds
    masked_args.skip_nesso = True
    masked_args.candidate_branch = 'masked-backbone'
    predictions = search.fold_and_score(sequences, smiles, directory / 'masked' / 'fold', masked_args)
    candidates = search.evaluate_candidates(predictions, sequences, refs, masked_args, cycle, args.nise_sc_ca, lig_thresh)
    candidates = search.select_scores(candidates, predictions, masked_args, directory / 'masked' / 'fold', owners, per_group=1)
    sequences, refs, repair_owners = {}, {}, {}
    for tid, parent in parents.items():
        passing = sorted([n for n in candidates if owners[n.name] == tid], key=lambda n: (-n.score, n.name))
        if not passing:
            records[str(tid)]['status'] = 'no_passing_masked_backbone'
            continue
        winner = passing[0]; records[str(tid)]['selected_backbone'] = asdict(winner)
        repaired = repair_input(backend, winner.pdb, directory / f'T{tid}' / 'repair_input.pdb')
        designed = search.design_sequences(args.designer, repaired, directory / 'repair' / 'design' / f'T{tid}',
            args.noise_mpnn_seqs, smiles, args, seq_temp=args.seq_temp, fs_temp=args.bindingsite_temp,
            seed=args.seed + cycle * 1000 + tid, constrain_ss=(args.designer == 'lasermpnn'))
        for i, sequence in enumerate(designed):
            if not re.fullmatch('[ACDEFGHIKLMNPQRSTVWY]+', sequence) or len(sequence) != len(parent.sequence):
                raise ValueError('Noising repair requires a complete, length-matched MPNN sequence')
            # Reserved parent index outside the supported regular beam (max 64).
            name = f'c{cycle:02d}_t{tid}_n999_s{i}'
            sequences[name] = sequence; refs[name] = winner.pdb; repair_owners[name] = tid
    repaired_args = copy.copy(args); repaired_args.candidate_branch = 'partial-noising-repair'
    predictions = search.fold_and_score(sequences, smiles, directory / 'repair' / 'fold', repaired_args)
    candidates = search.evaluate_candidates(predictions, sequences, refs, repaired_args, cycle, args.nise_sc_ca, lig_thresh)
    candidates = search.select_scores(candidates, predictions, repaired_args, directory / 'repair' / 'fold',
                                      repair_owners, per_group=args.noise_advance)
    by_tid = {}
    for tid, parent in parents.items():
        pool = sorted([n for n in candidates if repair_owners[n.name] == tid], key=lambda n: (-n.score, n.name))
        for node in pool:
            node.traj, node.origin = tid, parent.origin
            backend.record_candidate(node, True, predictions[node.name])
            search.write_trajectory_row(writer, 'nise', node, True)
        by_tid[tid] = pool
        records[str(tid)]['advanced'] = [n.name for n in pool[:args.noise_advance]]
        records[str(tid)]['status'] = 'selected' if pool else records[str(tid)].get('status', 'no_passing_repair')
        search.log(f'  cycle {cycle} T{tid}: partial noising {records[str(tid)]["status"]}; {len(pool[:args.noise_advance])} reserved places filled')
    atomic(directory / 'selection.json', dict(cycle=cycle, trajectories=records,
        reserved_places=args.noise_advance, masked_backbones_are_finalists=False,
        empty_branch_policy='leave_reserved_places_empty', scoring='Boltz ligand pLDDT/100 + P(bind)'))
    return by_tid
