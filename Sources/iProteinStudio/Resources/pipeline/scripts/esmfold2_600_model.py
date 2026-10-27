"""ESMFold2Fast-600M architecture using the pinned MLX primitives.

Feature preparation/auxiliary layout derives from Fausto Milletari's MIT MLX
port c26b9af872158d822a8c95589708eedd3b9c0831. The checkpoint-specific recycling and
zero-MSA feature contract follows Synthyra/FastPLMs' Apache-2.0 implementation bundled
in Synthyra/ESMFold2-600 at 38fa0be7397a485afd4a752202447693098f3d50.
Weights/residuals use FP32; the inherited MLX folding trunk computes in BF16.
This is not a claim of CUDA numerical parity.
"""
import copy
import mlx.core as mx
import mlx.nn as nn
from mlx_lm.models import esmfold2 as port

class Experimental600(port.ESMFold2Model):
    def __init__(self, config):
        # Reuse the identical input, diffusion and confidence modules. Remove
        # release-only components before strict loading; none enters forward.
        shared = copy.deepcopy(config)
        shared['lm_encoder'] = {'n_layers': 0}
        shared['parcae'] = {'coda_n_layers': 0}
        super().__init__(shared)
        for name in ('lm_encoder', 'parcae_log_a', 'parcae_log_delta',
                     'parcae_b_cont', 'parcae_input_norm', 'parcae_readout', 'parcae_coda'):
            delattr(self, name)
        self.confidence_head = ExperimentalConfidence(config)
        self.config = port.ESMFold2Config(config)
        self.pair_loop_proj = [nn.LayerNorm(config['d_pair']),
                               nn.Linear(config['d_pair'], config['d_pair'], bias=False)]

    def trunk(
        self, feats, lm_hidden_states=None, z0=None, num_loops=3, msa_max_depth=None
    ):
        """Pinned experimental preprocessing and recycling.

        Returns (z, x_inputs, aux).
        """
        if lm_hidden_states is None:
            lm_hidden_states = self.compute_lm_hidden_states(
                feats["input_ids"],
                asym_id=feats.get("asym_id"),
                residue_index=feats.get("residue_index"),
                mol_type=feats.get("mol_type"),
                token_mask=feats.get("token_attention_mask"),
            )
        tok_mask = feats["token_attention_mask"].astype(mx.float32)
        atm_mask = feats["atom_attention_mask"].astype(mx.float32)
        B, L = feats["res_type"].shape
        n_tokens = L

        res_type_oh = port._one_hot(feats["res_type"], port.NUM_RES_TYPES) * tok_mask[..., None]
        # The 600M checkpoint explicitly disables MSA features,
        # including the query-only profile; this differs from the release port.
        profile = mx.zeros_like(res_type_oh)
        deletion_mean = mx.zeros((B, L))
        ref_element_oh = (
            port._one_hot(feats["ref_element"], port.MAX_ATOMIC_NUMBER) * atm_mask[..., None]
        )
        ref_name_oh = (
            port._one_hot(feats["ref_atom_name_chars"], port.CHAR_VOCAB_SIZE)
            * atm_mask[..., None, None]
        )
        atom_to_token = (
            feats["atom_to_token"] * atm_mask.astype(feats["atom_to_token"].dtype)
        ).astype(mx.int32)

        x_inputs = self.inputs_embedder(
            res_type_oh,
            profile,
            deletion_mean,
            feats["ref_pos"],
            atm_mask,
            feats["ref_space_uid"],
            feats["ref_charge"],
            ref_element_oh,
            ref_name_oh,
            atom_to_token,
            n_tokens,
        )

        relpos = self.rel_pos(
            feats["residue_index"],
            feats["asym_id"],
            feats["sym_id"],
            feats["entity_id"],
            feats["token_index"],
        )
        z_init = self.z_init_1(x_inputs)[:, :, None] + self.z_init_2(x_inputs)[:, None]
        z_init = z_init + relpos + self.token_bonds(feats["token_bonds"])

        z_init = z_init + self.language_model(lm_hidden_states)
        pair_mask = tok_mask[:, :, None] * tok_mask[:, None, :]
        if z0 is not None:
            raise ValueError('ESMFold2Fast-600M does not accept an initial pair state')
        z = mx.zeros_like(z_init)
        # Pinned FastPLMs experimental forward: zero initialization, learned
        # recycling projection, n_loops + 1 passes; no PARCAE or LM encoder.
        for _ in range(num_loops + 1):
            recycled = z
            for layer in self.pair_loop_proj:
                recycled = layer(recycled)
            z = self.folding_trunk(z_init + recycled, mask=pair_mask)
        aux = dict(
            relpos=relpos,
            ref_pos=feats["ref_pos"],
            ref_charge=feats["ref_charge"],
            ref_mask=atm_mask,
            ref_element_oh=ref_element_oh,
            ref_name_oh=ref_name_oh,
            ref_space_uid=feats["ref_space_uid"],
            atom_to_token=atom_to_token,
            tok_mask=tok_mask,
            n_tokens=n_tokens,
        )
        return z, x_inputs, aux


class ExperimentalConfidence(port.ConfidenceHead):
    def __init__(self, config):
        cc=config['confidence_head']
        super().__init__(d_single=config['d_single'],d_pair=config['d_pair'],
                         d_inputs=config['inputs']['d_inputs'],distogram_bins=cc['distogram_bins'],
                         min_dist=cc['min_dist'],max_dist=cc['max_dist'],
                         num_plddt_bins=cc['num_plddt_bins'],num_pae_bins=cc['num_pae_bins'],
                         n_trunk_layers=cc['folding_trunk']['n_layers'])
        for name in ('pae_ln','pde_ln','pde_head','resolved_ln','resolved_weight'):
            delattr(self,name)
        # Upstream carries these four unused learned tensors. Preserve and load
        # them, rather than discarding checkpoint contents during conversion.
        self.s_norm=nn.LayerNorm(config['d_single'])
        self.s_inputs_to_single=nn.Linear(config['inputs']['d_inputs'],config['d_single'],bias=False)
        self.s_input_to_s=nn.Linear(config['inputs']['d_inputs'],config['d_single'],bias=False)

    def __call__(
        self,
        s_inputs,
        z,
        x_pred,
        distogram_atom_idx,
        token_attention_mask,
        atom_to_token,
        atom_attention_mask,
        asym_id,
        mol_type,
        num_diffusion_samples=1,
        relative_position_encoding=None,
        token_bonds_encoding=None,
    ):
        si = self.s_inputs_norm(s_inputs)
        zb = self.z_norm(z)
        if relative_position_encoding is not None:
            zb = zb + relative_position_encoding
        if token_bonds_encoding is not None:
            zb = zb + token_bonds_encoding
        zb = zb + self.s_to_z(si)[:, :, None]
        zb = zb + self.s_to_z_transpose(si)[:, None]
        zb = zb + self.s_to_z_prod_out(
            self.s_to_z_prod_in1(si)[:, :, None, :]
            * self.s_to_z_prod_in2(si)[:, None, :, :]
        )

        rep = lambda t: port._repeat_samples(t, num_diffusion_samples)
        pair = rep(zb)
        rep_idx = rep(distogram_atom_idx).astype(mx.int32)
        atom_to_token = rep(atom_to_token).astype(mx.int32)
        atom_attention_mask = rep(atom_attention_mask)
        mask = rep(token_attention_mask)
        asym_id = rep(asym_id)
        mol_type = rep(mol_type)

        rep_coords = port.gather_token_to_atom(x_pred, rep_idx)  # (Bm, L, 3)
        rep_d = port._cdist(rep_coords)
        dbins = mx.sum((rep_d[..., None] > self.boundaries).astype(mx.int32), axis=-1)
        pair = pair + self.dist_bin_pairwise_embed(dbins)

        pair_mask = mask[:, :, None].astype(mx.float32) * mask[:, None, :].astype(
            mx.float32
        )
        pair = pair + self.folding_trunk(pair, mask=pair_mask)
        single = self.row_attention_pooling(pair, mask)

        atom_mask_f = atom_attention_mask.astype(mx.float32)
        s_at_atoms = port.gather_token_to_atom(single, atom_to_token)
        s_at = self.plddt_ln(s_at_atoms)
        intra = mx.minimum(
            port._intra_token_idx(atom_to_token), self.plddt_weight.shape[0] - 1
        )
        B, A = atom_to_token.shape
        w = mx.take(self.plddt_weight, intra.reshape(-1), axis=0).reshape(
            B, A, self.plddt_weight.shape[1], self.plddt_weight.shape[2]
        )
        plddt_logits = mx.sum(s_at[..., :, None] * w, axis=-2)  # (B, A, nbins)
        plddt_per_atom = port._categorical_mean(plddt_logits, 0.0, 1.0)  # (B, A)

        L = single.shape[1]
        oh = (
            atom_to_token.astype(mx.int32)[:, :, None] == mx.arange(L)[None, None, :]
        ).astype(mx.float32)
        plddt_sum = mx.sum(oh * (plddt_per_atom * atom_mask_f)[..., None], axis=1)
        count = mx.sum(oh * atom_mask_f[..., None], axis=1)
        plddt = plddt_sum / mx.maximum(count, 1e-6)
        complex_plddt = mx.sum(plddt_per_atom * atom_mask_f, axis=-1) / (
            mx.sum(atom_mask_f, axis=-1) + port._EPS
        )
        plddt_ca = mx.take_along_axis(plddt_per_atom, rep_idx, axis=1)

        # Interface-weighted pLDDT: ligands count double, polymer tokens count
        # only where they sit within 8 A of another chain.
        is_ligand = (mol_type == port._MOL_TYPE_NONPOLYMER).astype(mx.float32)
        inter_chain = (asym_id[:, :, None] != asym_id[:, None, :]).astype(mx.float32)
        interface = mx.max(
            (rep_d < 8).astype(mx.float32) * inter_chain * (1.0 - is_ligand)[..., None],
            axis=-1,
        )
        iplddt_w = mx.where(is_ligand > 0, mx.full(interface.shape, 2.0), interface)
        atom_w = (
            atom_mask_f
            * port.gather_token_to_atom(iplddt_w[..., None], atom_to_token)[..., 0]
        )
        complex_iplddt = mx.sum(plddt_per_atom * atom_w, axis=-1) / (
            mx.sum(atom_w, axis=-1) + port._EPS
        )

        pae_logits = self.pae_head(pair)
        pae = port._categorical_mean(pae_logits, 0.0, 32.0)

        n_bins = pae_logits.shape[-1]
        bw = 32.0 / n_bins
        bin_centers = (mx.arange(n_bins, dtype=mx.float32) + 0.5) * bw
        mask_f = mask.astype(mx.float32)
        N_res = mx.sum(mask_f, axis=-1, keepdims=True)
        d0 = 1.24 * (mx.maximum(N_res, 19) - 15) ** (1.0 / 3.0) - 1.8
        tm_per_bin = 1.0 / (1.0 + (bin_centers / d0) ** 2)  # (B, n_bins)
        tm_expected = mx.sum(
            mx.softmax(pae_logits, axis=-1) * tm_per_bin[:, None, None, :], axis=-1
        )
        pm2 = mask_f[:, :, None] * mask_f[:, None, :]
        ptm_row = mx.sum(tm_expected * pm2, axis=-1) / (mx.sum(pm2, axis=-1) + port._EPS)
        ptm = mx.max(ptm_row, axis=-1)
        iptm_row = mx.sum(tm_expected * inter_chain * pm2, axis=-1) / (
            mx.sum(inter_chain * pm2, axis=-1) + port._EPS
        )
        iptm = mx.max(iptm_row, axis=-1)

        # Experimental upstream uses pairwise chain averages, not the release
        # head's maximum-over-rows aggregation.
        n_chains = int(mx.max(asym_id).item()) + 1
        chain = (asym_id[..., None] == mx.arange(n_chains)).astype(mx.float32) * mask_f[..., None]
        totals = mx.einsum('bij,bic,bjd->bcd', tm_expected, chain, chain)
        counts = mx.sum(chain, axis=1)
        pair_chains_iptm = totals / (counts[:, :, None] * counts[:, None, :] + port._EPS)

        return {
            "plddt": plddt,
            "plddt_per_atom": plddt_per_atom,
            "plddt_ca": plddt_ca,
            "complex_plddt": complex_plddt,
            "complex_iplddt": complex_iplddt,
            "plddt_logits": plddt_logits,
            "pae_logits": pae_logits,
            "pae": pae,
            "ptm": ptm,
            "iptm": iptm,
            "pair_chains_iptm": pair_chains_iptm,
        }
