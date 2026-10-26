"""Explicit atom correspondence and root-anchored Studio-AME beta metrics.

Named-atom RMSDs are conservative: no guessed symmetry reassignment. All fits
are single rigid, proper rotations; a ligand is never fitted to itself.
"""
import json
from pathlib import Path
import numpy as np
from .contract import atomic, digest, verify, PROFILE

AA3 = 'ALA ARG ASN ASP CYS GLN GLU GLY HIS ILE LEU LYS MET PHE PRO SER THR TRP TYR VAL'.split()
AA1 = 'ARNDCQEGHILKMFPSTWYV'
LETTERS = dict(zip(AA3, AA1))


def heavy(residue):
    return {name: atom for name, atom in residue['atoms'].items() if atom['element'].upper() not in {'H', 'D'}}


def read(path, *, selected_keys=None):
    """Reject multiple models, alternative conformers and duplicate atom IDs."""
    import gemmi
    st = gemmi.read_structure(str(path))
    if len(st) != 1:
        raise ValueError('Exactly one structural model is required.')
    residues = {}
    for chain in st[0]:
        for res in chain:
            key = f'{chain.name}:{res.seqid.num}:{res.seqid.icode.strip()}'
            if selected_keys is not None and key not in selected_keys:
                continue
            if key in residues:
                raise ValueError('Ambiguous residue identity: ' + key)
            atoms = {}
            for atom in res:
                if atom.element.is_hydrogen:
                    continue
                if atom.has_altloc() or atom.name in atoms or atom.occ <= 0:
                    raise ValueError('Choose one observed conformer explicitly: ' + key)
                xyz = [atom.pos.x, atom.pos.y, atom.pos.z]
                if not np.isfinite(xyz).all():
                    raise ValueError('Nonfinite coordinate: ' + key)
                atoms[atom.name] = dict(xyz=xyz, element=atom.element.name.upper(), b=atom.b_iso)
            residues[key] = dict(component=res.name, atoms=atoms)
    return residues


def source_key(r):
    return f"{r['chain']}:{r['residue']}:{r['insertion_code']}"


def mapped_key(label):
    import re
    match = re.fullmatch(r'([A-Za-z0-9])(-?\d+)', label)
    if not match:
        raise ValueError('Invalid generator residue mapping: ' + label)
    return f'{match[1]}:{int(match[2])}:'


def coords(residues, keys):
    try:
        return np.array([residues[r]['atoms'][a]['xyz'] for r, a in keys], dtype=float)
    except KeyError as exc:
        raise ValueError('Missing required residue or atom: ' + str(exc)) from exc


def fit(mobile, reference):
    if mobile.shape != reference.shape or len(mobile) < 3:
        raise ValueError('A rigid alignment requires at least three corresponding atoms.')
    p, q = mobile - mobile.mean(0), reference - reference.mean(0)
    if min(np.linalg.matrix_rank(p, tol=1e-6), np.linalg.matrix_rank(q, tol=1e-6)) < 2:
        raise ValueError('Degenerate alignment: atoms are collinear or coincident.')
    u, _, vt = np.linalg.svd(p.T @ q)
    sign = np.eye(3); sign[-1, -1] = np.linalg.det(u @ vt)
    rotation = u @ sign @ vt
    return rotation, reference.mean(0) - mobile.mean(0) @ rotation


def rmsd(p, q):
    return float(np.sqrt(np.mean(np.sum((p - q) ** 2, axis=-1))))


def fitted_rmsd(p, q):
    r, t = fit(p, q)
    return rmsd(p @ r + t, q)


def freeze_root(bundle, pdb, metadata, output):
    bundle, pdb, output = Path(bundle), Path(pdb), Path(output)
    cfg = verify(bundle)['request']
    c = json.loads((bundle / 'case.json').read_text())
    root = read(pdb)
    protein_keys = [k for k, v in root.items() if v['component'] in LETTERS]
    if len(protein_keys) != cfg['length'] or protein_keys != [f'A:{i}:' for i in range(1, cfg['length'] + 1)]:
        raise ValueError('Root must contain exactly the requested length, numbered A1..A(length).')
    mapping = metadata['diffused_index_map']
    if set(mapping) != {r['source_selector'] for r in c['protein_motif']} or len(set(mapping.values())) != len(mapping):
        raise ValueError('Generator insertion map is incomplete or non-bijective.')
    motif, selected, source_xyz = [], [], []
    identities = {}
    for res in c['protein_motif']:
        key = mapped_key(mapping[res['source_selector']])
        if root[key]['component'] != res['component']:
            raise ValueError('Generator changed a catalytic residue identity.')
        identities[key] = res['component']
        expected = set(heavy(res))
        if set(root[key]['atoms']) != expected:
            raise ValueError('Generated motif has missing or extra heavy atoms: ' + key)
        motif += [(key, a) for a in sorted(expected)]
        if set(metadata['motif_fixed_atoms'][res['source_selector']]) != set(res['conditioning_atoms']):
            raise ValueError('Generator changed the requested atomic motif mask.')
        for atom in res['conditioning_atoms']:
            selected.append((key, atom)); source_xyz.append(res['atoms'][atom]['xyz_angstrom'])
    instance_map = metadata.get('ligand_instance_map', [])
    ligands = []
    for res in c['ligands']:
        matches = [m for m in instance_map if (m['source_chain'], m['source_residue'], m['component']) ==
                   (res['chain'], res['residue'], res['component'])]
        if len(matches) != 1:
            raise ValueError('Missing or ambiguous ligand instance export mapping.')
        m = matches[0]; key = f"{m['output_chain']}:{m['output_residue']}:"
        if key not in root or root[key]['component'] != res['component'] or set(root[key]['atoms']) != set(heavy(res)):
            raise ValueError('Generated ligand identity/atom set differs from benchmark: ' + key)
        for a in heavy(res):
            if root[key]['atoms'][a]['element'] != res['atoms'][a]['element'].upper():
                raise ValueError('Generated ligand element changed: ' + key)
        ligands.append(dict(key=key, component=res['component'], atoms=sorted(heavy(res)), source=source_key(res)))
    if len(set(l['key'] for l in ligands)) != len(ligands):
        raise ValueError('Ligand instances collapsed during export.')
    if set(root) != set(protein_keys) | {l['key'] for l in ligands}:
        raise ValueError('Root has unexpected molecular entities.')
    lxyz = coords(root, [(l['key'], a) for l in ligands for a in l['atoms']])
    pocket = [k for k in protein_keys if len(lxyz) and np.min(np.linalg.norm(
        coords(root, [(k, a) for a in root[k]['atoms']])[:, None] - lxyz[None], axis=-1)) < 8.0]
    pocket_atoms = [(k, 'CA') for k in pocket]
    if ligands:
        fit(coords(root, pocket_atoms), coords(root, pocket_atoms))
    result = dict(schema=1, profile=PROFILE, bundle_sha256=digest(bundle / 'bundle.json'),
                  root_sha256=digest(pdb), atoms=root, motif_atoms=motif,
                  selected_atoms=selected, source_xyz=source_xyz, identities=identities,
                  source_to_query={k: int(mapped_key(v).split(':')[1]) for k, v in mapping.items()},
                  motif_correspondence=[dict(source_residue=r['source_selector'],
                      query_chain='A', query_position=int(mapped_key(mapping[r['source_selector']]).split(':')[1]),
                      component=r['component'], atoms=r['conditioning_atoms']) for r in c['protein_motif']],
                  ligands=ligands, backbone_atoms=[(k, 'CA') for k in protein_keys],
                  pocket_atoms=pocket_atoms, source_tolerance=cfg['source_tolerance'],
                  definitions=dict(motif='single global least-squares fit of all named motif heavy atoms',
                      original_input_motif='single global fit of exactly the selected input atoms across all mapped residues',
                      backbone='C-alpha least-squares fit over complete scaffold',
                      pocket='C-alpha fit of root residues with any heavy atom <8 A from any ligand',
                      symmetry='strict source atom names; no symmetry remapping',
                      confidence='explicit protein mean pLDDT, 0-100'))
    coords(root, result['backbone_atoms'])
    result['source_insertion_rmsd'] = fitted_rmsd(coords(root, selected), np.array(source_xyz))
    if output.exists() and json.loads(output.read_text()) != result:
        raise ValueError('Cannot change a frozen root reference.')
    atomic(output, result)
    return result


def input_motif_report(reference, structure):
    """Score only mapped selected atoms, independent of predictor/ligand output."""
    ref = json.loads(Path(reference).read_text())
    if ref.get('profile') != PROFILE:
        raise ValueError('Regenerate the frozen motif reference for the current scoring profile.')
    pred = read(structure, selected_keys=set(ref['identities']))
    for key, component in ref['identities'].items():
        if key not in pred or pred[key]['component'] != component:
            raise ValueError('Missing or mutated mapped motif residue: ' + key)
    p, q = coords(pred, ref['selected_atoms']), np.asarray(ref['source_xyz'])
    rot, shift = fit(p, q)
    squared = np.sum((p @ rot + shift - q) ** 2, axis=1)
    per_residue = []
    for residue in ref['motif_correspondence']:
        key = f"{residue['query_chain']}:{residue['query_position']}:"
        idx = [i for i, (r, _) in enumerate(ref['selected_atoms']) if r == key]
        if not idx:
            raise ValueError('Incomplete motif atom correspondence: ' + key)
        per_residue.append({**residue, 'rmsd': float(np.sqrt(squared[idx].mean()))})
    return dict(reference_sha256=digest(reference), structure_sha256=digest(structure),
                rmsd=float(np.sqrt(squared.mean())), atom_count=len(p), residues=per_residue,
                alignment='one global fit of selected original-input motif atoms; no whole-scaffold fit or per-residue refit')


def evaluate(reference, prediction, protein_plddt, *, guided=False):
    if guided:
        raise ValueError('Guided predictions are proposal structures, never ranking evidence.')
    if type(protein_plddt) not in (float, int) or not np.isfinite(protein_plddt) or not 0 <= protein_plddt <= 100:
        raise ValueError('Supply explicit protein mean pLDDT on a 0-100 scale.')
    ref = json.loads(Path(reference).read_text())
    root, pred = ref['atoms'], read(prediction)
    if set(pred) != set(root):
        raise ValueError('Missing or unexpected protein/ligand instances in prediction.')
    for key, component in ref['identities'].items():
        if pred[key]['component'] != component:
            raise ValueError('Catalytic residue identity changed: ' + key)
    source_report = input_motif_report(reference, prediction)
    source = source_report['rmsd']
    motif = fitted_rmsd(coords(pred, ref['motif_atoms']), coords(root, ref['motif_atoms']))
    backbone = fitted_rmsd(coords(pred, ref['backbone_atoms']), coords(root, ref['backbone_atoms']))
    ligand_scores = []
    if ref['ligands']:
        rot, shift = fit(coords(pred, ref['pocket_atoms']), coords(root, ref['pocket_atoms']))
        for ligand in ref['ligands']:
            key = ligand['key']
            if (pred[key]['component'] != ligand['component'] or set(pred[key]['atoms']) != set(ligand['atoms'])
                    or any(pred[key]['atoms'][a]['element'] != root[key]['atoms'][a]['element'] for a in ligand['atoms'])):
                raise ValueError('Ligand identity or heavy atom set changed: ' + key)
            keys = [(key, a) for a in ligand['atoms']]
            p, q = coords(pred, keys) @ rot + shift, coords(root, keys)
            ligand_scores.append(dict(key=key, centroid=float(np.linalg.norm(p.mean(0) - q.mean(0))),
                                      pose_rmsd=rmsd(p, q)))
    worst = max((l['centroid'] for l in ligand_scores), default=None)
    paper_terms = [motif / 2.5] + ([worst / 3.0] if worst is not None else [])
    terms = [source / 2.5] + ([worst / 3.0] if worst is not None else [])
    fold = backbone < 2.0 and protein_plddt > 80.0
    source_pass = source <= ref['source_tolerance']
    sequence = ''.join(LETTERS[pred[k]['component']] for k, _ in ref['backbone_atoms'])
    return dict(schema=1, profile=PROFILE, reference_sha256=digest(reference), prediction_sha256=digest(prediction),
                guided=False, sequence=sequence, protein_plddt=float(protein_plddt),
                backbone_rmsd=backbone, motif_rmsd=motif, source_rmsd=source,
                input_motif=source_report, motif_correspondence=ref['motif_correspondence'],
                ranking_motif_reference='original_input_selected_atoms',
                ligands=ligand_scores, worst_ligand_centroid=worst, fold_pass=fold,
                source_pass=source_pass, eligible=fold and source_pass,
                paper_like_pass=fold and max(paper_terms) < 1, guarded_pass=fold and source_pass and max(paper_terms) < 1,
                objective=max(terms), tie_break=sum(terms),
                status='computational geometry only; chemistry/clash and independent-family checks still required')
