"""Explicit per-atom geometry requirements on predicted complexes.

Uses RDKit's FreeSASA implementation, heavy atoms, element-specific RDKit van
 der Waals radii, a 1.4 A solvent probe, and the Shrake-Rupley algorithm.
"""
import math


def measure(path, settings, manifest):
    from ligand_atoms import audit_atoms
    audit_atoms(path, manifest)
    import gemmi
    import numpy as np
    from rdkit import Chem
    from rdkit.Chem import rdFreeSASA
    model = gemmi.read_structure(str(path))[0]
    atoms = [(c.name, a.name.strip(), a.element.atomic_number, [a.pos.x, a.pos.y, a.pos.z])
             for c in model for r in c for a in r if a.element.name not in ('H', 'D') and r.name not in ('HOH', 'WAT')]
    if any(z <= 0 or not all(math.isfinite(x) for x in xyz) for _, _, z, xyz in atoms):
        raise ValueError('Cannot measure exposure with unknown elements or non-finite coordinates.')
    ligand = [i for i, a in enumerate(atoms) if a[0] == 'B']
    protein = np.array([a[3] for a in atoms if a[0] == 'A'])
    if not len(protein):
        raise ValueError('Cannot measure ligand contacts without protein chain A.')
    by_name = {atoms[i][1]: i for i in ligand}
    contacts = {name: float(np.linalg.norm(protein - np.array(atoms[by_name[name]][3]), axis=1).min())
                for name in settings.get('hotspot_atoms', [])}

    def sasa(indices):
        mol = Chem.RWMol()
        conformer = Chem.Conformer(len(indices))
        radii = []
        for j, i in enumerate(indices):
            _, _, z, xyz = atoms[i]
            mol.AddAtom(Chem.Atom(z)); conformer.SetAtomPosition(j, xyz)
            radii.append(Chem.GetPeriodicTable().GetRvdw(z))
        mol.AddConformer(conformer)
        options = rdFreeSASA.SASAOpts(rdFreeSASA.ShrakeRupley, rdFreeSASA.Protor, 1.4)
        rdFreeSASA.CalcSASA(mol, radii, opts=options)
        values = [float(a.GetProp('SASA')) for a in mol.GetAtoms()]
        if any(not math.isfinite(v) or v < 0 for v in values):
            raise ValueError('Solvent accessibility calculation returned invalid areas.')
        return dict(zip(indices, values))

    exposure = {}
    if settings.get('exposed_atoms'):
        complex_sasa, free_sasa = sasa(range(len(atoms))), sasa(ligand)
        for name in settings['exposed_atoms']:
            index = by_name[name]
            free, bound = free_sasa[index], complex_sasa[index]
            # An internally inaccessible ligand atom cannot satisfy an exposure request.
            fraction = min(1.0, bound / free) if free > 0.1 else 0.0
            exposure[name] = dict(complex_sasa_a2=bound, isolated_ligand_sasa_a2=free,
                                  retained_fraction=fraction)
    failures = [f'{name}: no protein contact within {settings["hotspot_distance"]:g} Å'
                for name, distance in contacts.items() if distance > settings['hotspot_distance']]
    failures += [f'{name}: retains less than {settings["exposure_min_fraction"]:.0%} of unbound accessibility'
                 for name, row in exposure.items() if row['retained_fraction'] < settings['exposure_min_fraction']]
    return dict(passed=not failures, failures=failures, hotspot_distance_a=contacts, exposure=exposure,
                protocol='rdkit-freesasa-shrake-rupley-heavy-v1', probe_radius_a=1.4)
