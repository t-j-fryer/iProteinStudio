"""Check whether ligand inversion was accompanied by protein Cα inversion."""
import argparse
import json
import os
import pickle
from pathlib import Path
import numpy as np
import gemmi


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--audit", type=Path, required=True)
    p.add_argument("--root", type=Path, default=os.environ.get("NANOHUNTER_ROOT"))
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.root is None:
        p.error("Set NANOHUNTER_ROOT or pass --root")
    # This managed CCD component is fingerprinted by the replay plan.
    molecule = pickle.loads((args.root / "models/boltz2/mols/ALA.pkl").read_bytes())
    coords = {a.GetProp("name"): np.array(molecule.GetConformer().GetAtomPosition(a.GetIdx()))
              for a in molecule.GetAtoms()}
    expected = float(np.linalg.det([coords[n] - coords["CA"] for n in ("N", "C", "CB")]))
    if abs(expected) < .1:
        raise ValueError("Invalid reference tetrahedron")
    output = []
    for row in json.loads(args.audit.read_text())["raw_metrics"]:
        count, wrong, planar = 0, [], []
        for residue in gemmi.read_structure(row["path"])[0].find_chain("A"):
            atoms = {a.name.strip(): np.array([a.pos.x, a.pos.y, a.pos.z]) for a in residue}
            if {"N", "C", "CA", "CB"} <= atoms.keys():
                determinant = float(np.linalg.det([atoms[n] - atoms["CA"] for n in ("N", "C", "CB")]))
                count += 1
                if determinant * expected < 0:
                    wrong.append(str(residue.seqid))
                if abs(determinant) < .1:
                    planar.append(str(residue.seqid))
        output.append(dict(arm=row["arm"], id=row["id"], assessable_CA_centers=count,
                           opposite_CA_handedness=wrong, near_planar_CA=planar))
    result = dict(method="Signed N-CA,C-CA,CB-CA volume vs plan-fingerprinted canonical L-ALA CCD; glycine and UNK/absent CB excluded",
                  reference_determinant=expected, results=output)
    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
