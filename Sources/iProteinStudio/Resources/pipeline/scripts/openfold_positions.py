"""Read RDKit conformer coordinates in bulk; preserve ordering, crop and RNG.

Qualified against native tensors and five paired complexes in Lab Book 0230.
Only the three validated expressions are changed; unknown upstream source fails
before inference rather than applying a speculative replacement.
"""
import ast
import inspect
import textwrap


def install():
    import numpy as np
    import openfold3.core.data.pipelines.featurization.conformer as conformer
    import openfold3.core.data.framework.single_datasets.inference as inference

    native = conformer.featurize_reference_conformers_of3
    source = textwrap.dedent(inspect.getsource(native))
    replacements = {
        'conf = mol.GetConformer()': 'conf = mol.GetConformer()\n        _all_positions = conf.GetPositions()',
        'coords = conf.GetAtomPosition(atom.GetIdx())': 'coords = _all_positions[atom.GetIdx()]',
        'mol_ref_pos = torch.tensor(mol_ref_pos, dtype=torch.float32)':
            'mol_ref_pos = torch.from_numpy(_np.asarray(mol_ref_pos, dtype=_np.float32))',
    }
    for old, new in replacements.items():
        if source.count(old) != 1:
            raise RuntimeError('The OpenFold conformer implementation differs from the validated runtime. Repair OpenFold in Setup.')
        source = source.replace(old, new)
    namespace = dict(inspect.unwrap(native).__globals__)
    namespace['_np'] = np
    exec(compile(ast.parse(source), '<studio-rdkit-position-array>', 'exec'), namespace)
    optimized = namespace['featurize_reference_conformers_of3']
    prior_inference = inference.featurize_reference_conformers_of3
    conformer.featurize_reference_conformers_of3 = optimized
    inference.featurize_reference_conformers_of3 = optimized

    def undo():
        conformer.featurize_reference_conformers_of3 = native
        inference.featurize_reference_conformers_of3 = prior_inference
    return undo
