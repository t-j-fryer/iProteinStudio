"""The RFD4 gate/layout Metal kernel must equal the eager path bit for bit.

Lab Book 0825 replaced the per-output gather with a threadgroup-tiled transpose.
Arithmetic and its order are unchanged, so every output must be byte-identical to
the eager chunk/sigmoid/mask/permute the adapter replaces. Shapes deliberately
include sizes whose position count is not a multiple of the 32-wide tile, and
batches above one, because those exercise the kernel's bounds checks.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Sources/iProteinStudio/Resources/pipeline/scripts'))

try:
    import torch
    HAVE_MPS = torch.backends.mps.is_available()
except Exception:  # pragma: no cover - torch absent in some test environments
    torch = None
    HAVE_MPS = False


@unittest.skipUnless(HAVE_MPS, 'the RFD4 Metal kernel needs an Apple MPS device')
class GateLayoutKernelTests(unittest.TestCase):
    C = 256

    @classmethod
    def setUpClass(cls):
        from rfd4 import triangle_metal
        cls.mod = triangle_metal
        cls.shader = torch.mps.compile_shader(triangle_metal.METAL)

    def reference(self, packed, mask):
        """The eager statement in `grouped()` that the kernel stands in for."""
        payload, gate = packed.chunk(2, dim=-1)
        a, b = (payload * gate.sigmoid() * mask[..., None]).chunk(2, dim=-1)
        return a.permute(0, 3, 1, 2).contiguous(), b.permute(0, 3, 1, 2).contiguous()

    def run_kernel(self, packed, mask, n, batch):
        tile = self.mod.TILE
        a = torch.empty((batch, self.C, n, n), device='mps', dtype=torch.bfloat16)
        b = torch.empty_like(a)
        spatial = n * n
        self.shader.gate_layout(packed.contiguous(), mask.contiguous(), a, b, n, self.C,
                                threads=(-(-spatial // tile) * tile, -(-self.C // tile) * tile, batch),
                                group_size=(tile, tile, 1))
        torch.mps.synchronize()
        return a, b

    def test_matches_eager_bitwise_across_shapes_batches_and_masks(self):
        torch.manual_seed(0)
        for n, batch in [(16, 1), (64, 1), (65, 1), (97, 1), (120, 1), (128, 2), (64, 4)]:
            with self.subTest(n=n, batch=batch):
                packed = torch.randn(batch, n, n, 4 * self.C, device='mps', dtype=torch.bfloat16)
                mask = torch.rand(batch, n, n, device='mps') > 0.25
                got_a, got_b = self.run_kernel(packed, mask, n, batch)
                want_a, want_b = self.reference(packed, mask)
                self.assertTrue(torch.equal(got_a, want_a), f'left differs at n={n} batch={batch}')
                self.assertTrue(torch.equal(got_b, want_b), f'right differs at n={n} batch={batch}')

    def test_all_false_and_all_true_masks(self):
        torch.manual_seed(1)
        n, batch = 48, 1
        packed = torch.randn(batch, n, n, 4 * self.C, device='mps', dtype=torch.bfloat16)
        for value in (False, True):
            with self.subTest(mask=value):
                mask = torch.full((batch, n, n), value, device='mps', dtype=torch.bool)
                got_a, got_b = self.run_kernel(packed, mask, n, batch)
                want_a, want_b = self.reference(packed, mask)
                self.assertTrue(torch.equal(got_a, want_a))
                self.assertTrue(torch.equal(got_b, want_b))
                if not value:
                    self.assertEqual(float(got_a.abs().sum()), 0.0)

    def test_adapter_still_requires_bf16_and_boolean_mask(self):
        from types import SimpleNamespace
        pair_dim = 384
        module = SimpleNamespace(linear_a_p=SimpleNamespace(out_features=self.C),
                                 layer_norm_in=lambda z: z)
        weight = torch.zeros(4 * self.C, pair_dim, device='mps', dtype=torch.float32)
        pairs = torch.zeros(1, 4, 4, pair_dim, device='mps', dtype=torch.float32)
        mask = torch.ones(1, 4, 4, device='mps', dtype=torch.bool)
        with self.assertRaisesRegex(ValueError, 'BF16'):  # fp32 activations
            self.mod.grouped(module, pairs, mask, packed=weight, shader=self.shader)
        with self.assertRaisesRegex(ValueError, 'BF16'):  # non-boolean mask
            self.mod.grouped(module, pairs.bfloat16(), mask.float(),
                             packed=weight.bfloat16(), shader=self.shader)


if __name__ == '__main__':
    unittest.main()
