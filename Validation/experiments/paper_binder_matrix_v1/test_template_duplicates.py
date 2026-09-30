"""Exercise the real upstream CPU layer with duplicate and distinct templates."""
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

import torch
from protenix.model.modules.pairformer import TemplateEmbedder
from template_duplicates import install

torch.set_num_threads(1)
torch.manual_seed(42)
layer = TemplateEmbedder(n_blocks=1, c=8, c_z=16).eval()
for parameter in layer.parameters():
    torch.nn.init.uniform_(parameter, -.3, .3)
n = 7
base = dict(template_aatype=torch.zeros(4, n, dtype=torch.long),
            template_distogram=torch.zeros(4, n, n, 39),
            template_pseudo_beta_mask=torch.zeros(4, n, n),
            template_unit_vector=torch.zeros(4, n, n, 3),
            template_backbone_frame_mask=torch.zeros(4, n, n),
            asym_id=torch.tensor([0, 0, 0, 1, 1, 1, 1]))
z = torch.randn(n, n, 16)
model = SimpleNamespace(template_embedder=layer,
                        get_pairformer_output=lambda input_feature_dict, z: layer(input_feature_dict, z))
for mixed in (False, True):
    if mixed:
        base['template_aatype'][2, :] = 5
    with torch.no_grad():
        expected = model.get_pairformer_output(base, z)
        assert expected.abs().sum() > 0, 'Empty templates still have a learned contribution'
        with tempfile.TemporaryDirectory() as directory:
            undo = install(model, Path(directory))
            observed = model.get_pairformer_output(base, z)
            observed2 = model.get_pairformer_output(base, z + .1)
            undo()
            assert torch.equal(expected, observed), (expected-observed).abs().max()
            assert torch.equal(observed2, model.get_pairformer_output(base, z + .1))
            stats = json.loads((Path(directory) / 'template_duplicates.json').read_text())
            assert stats['native_single_calls'] == (4 if mixed else 2), stats
            assert stats['reused_single_calls'] == (4 if mixed else 6), stats
            print('Exact native template layer; mixed templates:', mixed, stats)
