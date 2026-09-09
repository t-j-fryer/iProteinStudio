# Sequence-only search recommendations

Date: 2026-09-04. Analysis only; no scientific runs, runtime changes, production
edits, model downloads, or measured new efficacy results. The coordinating agent
owns the required project/Validation Lab Book entries and indexes.

## Objective and invariants

Seek mean binder P-SEA sheet >=25% and helix <40% across optimized cycles 01–05,
averaged within each of a declared cohort of 10 alpha-cobratoxin trajectories,
then across trajectories. All binders are 90 residues; cycle 00 is excluded.
Preserve Protein Hunter initialization: exactly 45 X residues and the historical
seed-driven X-position selection. No starting binder structures, binder templates,
coordinate restraints, or hand-selected successful starts.

Hold target sequence/MSA, predictor and MPNN seeds, sample count, recycles,
diffusion steps, scheduler, and proposal budget fixed across paired arms. Preserve
the existing target-only template policy. The legacy campaign binder seed 155160,
MPNN seed 300160, predictor seed 42, and one sample are useful reproducibility
anchors, subject to the campaign owner's immutable manifest. Sequence-seed changes
do not produce identical cycle-00 structures; label those contrasts accordingly.

Read AGENTS.md and Validation/AGENTS.md; called MCP workflow_guide(iterative_design).
Any execution must first use system_detect, an immutable reviewed preflight plan,
and job_start through the existing bridge.

## Evidence and mechanism

Prior results are copied from project Lab Book 0090 and Validation Lab Book 0007,
measured in that campaign on Apple M4 Max, 40-core GPU, 64 GB unified memory.
Natural, sustained anti-helix, and sustained beta respectively yielded mean
sheet 12.1%, 17.4%, 15.0%, and mean helix 43.3%, 25.6%, 44.2%. Sustained
anti-helix mostly exchanged helix for coil, with binder pLDDT 60.5 versus 69.9
natural. These data support reducing excessive sequence pressure before simply
increasing beta composition.

The current helper assigns approximately 31.6% of positions to turns in the
completed plans (0090). It then rewards G/D/N/S at *every* planned turn position,
not just one core. At turn strength 0.5 this is +0.55 logit. With the documented
upstream softmax((logits+bias)/T), that contribution alone changes relative odds
against an otherwise unbiased residue by exp(0.55/0.1)=244.69 in later cycles.
At turn strength 0.1 it is exp(0.11/0.1)=3.00. These are analytical conditional
odds multipliers calculated from the code, not residue-frequency measurements.

Anti strength 0.5 contributes -0.60 to A/E/K/L/M/Q: relative odds 0.135 at T=0.3
and 0.00248 at T=0.1. Mixed mode directly adds this to beta face biases. On a
planned endpoint with pattern 0.5, E/K/Q receive +0.35 then -0.60, net -0.25.
At anti 0.1 or 0.2, the same net is +0.23 or +0.11. Lower anti strength preserves
more of the intended polar face while still penalizing these helix-prone residues.

The seed uses exp(bias) without the redesign temperature divisor; anti-helix has
separate historical probability weights and an i-to-i+4 rule. Thus a strength is
neither the same physical intervention across phases nor a fractional suppression.
The helper masks half the sequence after allocating grammar positions. Biasing
positions hidden by X cannot supply the predictor with their amino-acid identities.
This is a limitation to preserve and measure, not a reason to drop or rearrange X.

## Four ranked modifications

1. **Existing knobs: weaken turn enrichment and use mild mixed anti-helix.**
   Retain beta=0.5 and pattern=0.5, reduce turn to 0.1, and test anti=0.1 or 0.2.
   Sustained scope is the primary arm. This tests whether a weaker turn prior
   avoids locking a third of the sequence into a small turn alphabet while mild
   anti control reduces helical alternatives without cancelling E/K/Q enrichment.
   Do not interpret the selected strengths as validated optima. A turn-only
   reduction relative to the existing mixed pilot provides the cleaner first
   mechanistic contrast if that pilot has interpretable results.

2. **Existing knobs: keep redesign temperature at 0.3 throughout.**
   Use --ligand-temp-cycle1 0.30 and --ligand-temp-other 0.30 with the same seed and
   bias strengths as a matched low-temperature arm. This limits amplification of
   every added bias and increases sampling diversity. It also changes the MPNN
   backbone-conditioned distribution, so it is not equivalent to temperature-
   normalized priors. A matched natural T=0.3 control is required if attributing
   an effect specifically to prior/temperature interaction. Never claim a speed
   improvement from this scientific settings contrast.

3. **Conditional code experiment: explicit odds-calibrated redesign priors.**
   If existing knobs fail, version an experiment-only plan in which a prior weight
   w is converted with bias=T*log(w), at the *actual cycle sampling temperature*.
   Use the upstream sampler unchanged. Initially keep the same X mask and seed
   sequence generation and isolate redesign semantics. Cap each complete summed
   per-position prior, not just individual anti/beta terms; otherwise combinations
   can exceed the stated bound. A predeclared 3-fold maximum reward/penalty is a
   candidate test setting, not a scientific default. Resolve mixed-mode conflicts
   by penalizing A/L/M on planned strands while retaining E/K/Q availability on
   polar positions; evaluate that rule separately from odds normalization.

4. **Conditional code experiment: less fragmented strand/turn grammar.**
   Compare existing random 5–8-strand/2–5-turn blocks with a declared sequence-only
   grammar using 8–10-residue strand blocks and 2–3-residue turns. Enumerate valid
   90-residue partitions before sampling; retain an independent deterministic RNG
   for grammar, and preserve historical length/X RNG draws exactly. Make adjacent
   strand face phase choices part of one explicit hairpin-like sequence pattern,
   rather than independent draws; do not call that a specified physical topology.
   Remove the claim that strand endpoints are lateral sheet edges. Avoid uniformly
   forcing both ends of every short strand to be polar: that interrupts the
   alternating pattern and leaves fewer interior positions. Any revised endpoint
   rule needs its own recorded hypothesis, not an anti-aggregation claim.

   Keep turn boosts modest and localized; leave proline optional at a nominated
   turn position and suppress G/P only within planned strands. Neither a proline
   increase nor universal glycine exclusion specifies turn geometry. This grammar
   is the more speculative arm: it supplies no strand pairing, hydrogen-bond
   register, or shape constraint and may still produce helices or disordered coil.

## Bounded first pilot using currently supported controls

All listed arms use mixed mode, seed-and-cycles, beta=0.5, pattern=0.5, 45/90 X,
the existing grammar, and no loopkill. A small pilot diagnoses direction only;
it cannot establish the final cohort objective.

| Arm | Anti | Turn | Cycle 1 T | Cycles 2–5 T | Intended comparison |
|---|---:|---:|---:|---:|---|
| R, reference | 0.25 | 0.50 | 0.30 | 0.10 | Existing mixed-pilot recipe; use its audited result when matched |
| T, weaker turns | 0.25 | 0.10 | 0.30 | 0.10 | Isolate turn pressure versus R |
| M, mild anti | 0.10 | 0.10 | 0.30 | 0.10 | Isolate mixed conflict/anti pressure versus T |
| H, warmer sampling | 0.10 | 0.10 | 0.30 | 0.30 | Isolate sampling temperature versus M |

Suggested initial budget: two paired trajectories per newly run arm, five
optimized cycles each. If the existing mixed pilot's reference shows a confidence
collapse, prioritize M/H over extending R; record that decision before new results.
The optional anti=0.2 interpolation is a follow-up only when warranted by pilot
results. A winner selected from these exploratory pilots must be declared before
its complete ten-trajectory evaluation. Preserve every trajectory and cycle in
the endpoint; no best-of-cycle or post-hoc subset accounting.

For follow-up validation, compare the declared candidate with paired natural and
the best appropriate prior control at equal sample/proposal budgets. If a pilot
trajectory appears promising but most trajectories remain helical/coil, do not
call the ten-trajectory objective achieved. Show trajectory means and uncertainty,
not a pooled-cycle significance claim.

## Practical cautions and auditing

- Turn strength changes enrichment, not the number of grammar turns. Pattern
  strength only executes inside the helper's beta>0 branch: beta=0 disables
  patterning too, so it is not a clean pattern-only control.
- --ligand-temp-cycle1 and --ligand-temp-other are accepted by the MCP planner.
  The shell's global --mpnn-bias-aa-* and --loopkill flags are not in the inspected
  planner allowlist. Do not bypass the bridge to use them. Loopkill also suppresses
  proline globally, including intended turns, and is not recommended here.
- Record full sequence entropy, G/P and S/N/D fractions, charge, hydrophobic
  fractions/runs, and paired sequence identity at each cycle. For cycle 00 report
  composition on the 45 visible residues and X-mask identity separately. These
  diagnose alphabet collapse or weak visible pattern coverage; they do not replace
  P-SEA. Do not introduce rejection filters that silently spend extra proposals.
- Preserve complete-output, sequence-match, finite-coordinate, MPS/fallback and
  confidence audits. Report binder pLDDT and iPTM alongside P-SEA; predeclare
  quality gates through the parent campaign. Sheet fraction alone does not prove
  a stable fold or binding. Independent confirmation, if performed, must not use
  binder templates or restraints.

## Sources, checks, and limits

Inspected local sources: secondary_structure_control.py; nanohunter_run.sh seed,
temperature, loopkill and MPNN call paths; MCP plans.py flag allowlist; the prior
campaign config; project Lab Book 0090; Validation Lab Book 0007. No external
literature claims were added. The conditional-odds arithmetic was executed with
Python math.exp. No helper, predictor, or redesign experiment was run for this
note; no changes proposed here have established the requested >=25%/<40% endpoint.
No app build, scientific performance benchmark, independent fold, wet-lab test,
runtime mutation, or commit was performed.
