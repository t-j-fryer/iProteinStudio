"""Release-time exclusion of learned payloads, including binary .pth checkpoints."""
from pathlib import Path

# Exact upstream chemical/reference tables, not learned parameters.
STATIC_TABLES = {
    'new_ideal_coords.pt', 'new_ideal_bond_lengths.pt', 'new_ideal_bond_angles.pt',
    'rotamer_alignment.pt', 'ideal_aa_coords_prot.pt', 'ligandmpnn_training_pdb_codes.pt',
    'ligandmpnn_validation_pdb_codes.pt', 'ligandmpnn_test_sm_pdb_codes.pt',
}

def model_payload(name):
    path = Path(name)
    if path.suffix == '.pth':
        # Python path loaders live directly in site-packages. Nested .pth files
        # include TorchMetrics LPIPS learned weights and must not be shipped.
        return path.parent.name != 'site-packages'
    if path.suffix == '.pt' and path.name in STATIC_TABLES and path.parent.name == 'files' and path.parent.parent.name == 'LASErMPNN':
        return False
    return path.suffix in {'.pt', '.ckpt', '.safetensors', '.bin'} or path.name.endswith('.pth.tar')

def require_weight_free(record):
    found = [name for name in record['files'] if model_payload(name)]
    if found:
        raise ValueError('Learned model payloads must be downloaded separately: ' + ', '.join(found[:10]))
