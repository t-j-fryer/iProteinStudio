# Natural secondary-structure references for cycle-00 screening

2026-09-05. Primary-source research and proposed analysis only. No natural
distribution was measured, coordinates downloaded, inference launched, runtime
changed, or threshold validated. Project and Validation Lab Book entries/indexes
are owned by the coordinating agent. Repository and Validation instructions read.

## Recommendation

Use natural-protein helix/sheet/coil distributions as descriptive context for a
loose initialization screen, not as a universal biological acceptance rule.
Calibrate any decision against the actual 90-residue, 50% X workflow and later
optimized outcomes. The immediate priority is reliable cycle-00 annotation and
retrospective measurement of whether poor-looking starts recover. Do not require
cycle 00 to meet the final optimized-cycle sheet/helix objective.

## What the primary sources establish

- **There is no single natural secondary-structure composition.** CATH classifies
  domains into mainly alpha, mainly beta, alpha/beta, and few-secondary-structure
  classes. Class is a coarse compositional description, not a test of stability
  or a universal quantitative binning rule. Keep these classes visible when
  describing a reference distribution; do not force their proportions to match a
  selected design goal. [CATH authors' classification resource](https://cathdb.info/wiki/doku/?id=glossary%3Aclass),
  [CATH primary database paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC1751535/).

- **PDB structures are a selected sample.** Large-scale experimental analysis found
  predicted backbone disorder and exposed-side-chain entropy negatively associated
  with successful structure determination. Consequently, an experimental-structure
  cohort is conditional on tractability, not a census of all natural proteins.
  Solubility, crystallization success, and native stability should not be treated
  as interchangeable labels. [Price et al., 2009](https://pmc.ncbi.nlm.nih.gov/articles/PMC2746436/).

- **Length alone does not make a suitable reference.** SCOPe's small-protein class
  includes folds with disulfide or metal coordination, such as knottins and zinc
  fingers. These deserve separate annotation when the intended binder has no
  such support. A short domain cut from a large protein is also different from a
  demonstrated independently folded short chain. These are reference-selection
  implications, not measured size-dependent composition laws.
  [SCOPe small-protein classification](https://scop.berkeley.edu/sunid=56992).

- **Coil and intrinsic disorder are different annotations.** P-SEA recognizes
  secondary structure from Cα geometry; DSSP uses hydrogen-bond and geometric
  criteria. A residue outside recognized helix/sheet can be an ordered turn or
  loop. Neither method measures the ensemble of conformations defining intrinsic
  disorder. [Original P-SEA study](https://doi.org/10.1093/bioinformatics/13.3.291),
  [original DSSP study](https://doi.org/10.1002/bip.360221211).

- **Low pLDDT is evidence of uncertainty, with a demonstrated disorder association
  in natural-protein AlphaFold studies.** The human-proteome study defines pLDDT
  as a prediction of local coordinate agreement and separately evaluates it as a
  disorder predictor; it discusses regions that fold only in complex. A community
  benchmark also notes the influence of X-ray-based disorder labels and training.
  These results do not make every low-confidence residue disordered, nor establish
  Boltz calibration on partially unknown synthetic inputs.
  [Tunyasuvunakool et al., 2021](https://www.nature.com/articles/s41586-021-03828-1),
  [Akdel et al., 2022](https://www.nature.com/articles/s41594-022-00849-w).

- **Disorder needs an appropriate evidence source.** DisProt records experimental
  disorder evidence and experimental context, including condition-dependent
  structural states. It can supply a separate disorder reference; a PDB-unresolved
  segment alone is not an equivalent annotation. Filter its evidence types and
  conditions explicitly. [DisProt 2026 primary resource paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC12807702/).

## A bounded, defensible reference cohort

Proposed analysis choices below are not published natural thresholds.

1. Freeze a release/date and create a metadata manifest before fetching coordinates.
   Start with natural soluble protein chains of 70–110 residues, and separately
   analyze complete contiguous domains in that length range. Repeat the descriptive
   summary for 80–100 residues as a length sensitivity check. Exclude arbitrary
   90-residue windows from larger folds. Do not call a domain independently folded
   merely because a classification database supplies its boundary.
2. Remove close sequence redundancy with a declared rule, for example a 30%
   identity cutoff supported by PISCES, and retain one prespecified representative
   per cluster. Show a family-weighted sensitivity summary so abundant folds do
   not silently dominate. PISCES supports identity, structural quality, chain-length
   and method criteria. [PISCES authors' methods paper](https://academic.oup.com/nar/article/33/suppl_2/W94/2505533).
3. Record experimental method, coordinate completeness, natural sequence mapping,
   construct boundaries/tags, oligomeric context, membrane annotation, covalent
   disulfides and bound cofactors. Absence of membrane annotation is not proof of
   solubility. Exclude designed proteins from the natural set. Keep uncertainty in
   annotations visible; stratify disulfide/cofactor/obligate-complex examples rather
   than silently mixing them with unsupported monomeric folds.
4. Use all eligible representatives up to a declared small cap, e.g. 300; if more
   qualify, sample reproducibly before observing their composition. Download only
   listed coordinates. Preserve missing-coordinate fractions separately; a complete-
   coordinate primary set is useful for comparability but must be labelled as
   selected for completeness. NMR ensemble models are repeated observations of
   one protein, not independent proteins. No full-PDB or AlphaFoldDB download is
   needed. If the eligible sample is small, report it rather than widening filters
   silently or presenting unstable tail estimates as thresholds.

## Distribution and assignment strategy

Use the same pinned Biotite P-SEA version and preprocessing for natural coordinates
and Studio outputs. Biotite explicitly warns that its implementation can differ
from the original P-SEA software. A literature DSSP histogram therefore cannot be
used directly as a P-SEA cutoff. [Biotite implementation documentation](https://www.biotite-python.org/latest/apidoc/biotite.structure.annotate_sse.html).

For each chain/domain, record the joint H/E/C fractions, longest contiguous coil
segment, terminal versus internal coil segments, and assignment coverage. Show a
ternary scatter and empirical cumulative distributions, with optional 10-percentage-
point display bins; these bins are visualization choices, not natural fold classes
or acceptance boundaries. Weight proteins/clusters equally. Sparse bins need counts
and uncertainty; do not interpret the commonest bin as the optimum binder.

An optional DSSP sensitivity analysis should retain its raw states and document a
three-state mapping, such as H/G/I to helix, E/B to sheet, T/S/blank to other. Treat
other version-specific states explicitly. Compare the same residues and report
agreement and per-protein composition differences. Never translate missing atoms,
unassigned states or sequence gaps into coil. Do not splice noncontiguous residues
into an artificial continuous chain when measuring longest coil segments.

## Limits of 50% X input and a loose screen

Exactly 45 unknown residues in a 90-residue input leave half its amino-acid identity
unspecified. P-SEA can describe a produced Cα trace, but that is not an experimental
natural protein or a fully specified designed sequence. No inspected source
establishes natural-protein disorder or confidence calibration for this Boltz input
regime. This is an applicability limit, not a claim that the model cannot process X.
Official Boltz documentation describes confidence outputs, not a validated 50% X
disorder screen. [Boltz authors' prediction documentation](https://github.com/jwohlwend/boltz/blob/main/docs/prediction.md).

In particular, Biotite returns an empty annotation for a non-amino-acid residue or
one missing Cα. Check explicitly whether UNK residues receive valid labels in the
installed analysis. Require the requested 90 Cα positions and separately account
for all 90 assignments. A technical normalization used solely for geometry-based
annotation must be documented and leave immutable raw coordinates and requested
sequence unchanged; never relabel unknown residues as coil or silently exclude
them from the denominator.

Recommended decision sequence:

1. Audit cycle-00 geometry, sequence identity, X positions, assignment completeness,
   and chain-specific confidence. Normalize confidence units explicitly; do not
   substitute complex mean confidence for binder confidence or compare experimental
   B factors with pLDDT.
2. Describe coil extent and low-confidence extent separately. A long low-confidence
   coil segment is a candidate initialization concern; high coil alone is not proof
   of an unusable start. A confidently predicted long helix can also be unsuitable
   for the intended design endpoint, so a coil ceiling alone is incomplete.
3. First score proposed screens retrospectively on all available trajectories.
   Tabulate rejected starts that subsequently produced acceptable optimized outputs,
   retained starts that failed, and proposal cost. Evaluate by trajectory, excluding
   cycle 00 from optimized endpoints. A natural upper-tail reference can nominate
   a soft flag, but its rejection boundary requires workflow-specific calibration.
4. Freeze one provisional rule before a prospective pilot. Preserve 50% X and the
   seed policy; record every rejected candidate, retry seed and attempt budget.
   A repair/resampling arm changes proposal cost and initialization distribution:
   compare it with a control under the same declared budget. Retain a subset of
   flagged starts without repair to estimate false rejection. Do not hide failed
   attempts or promote a filter solely because selected starts look more natural.

No numerical natural helix/sheet/coil threshold is justified by this research alone.
No reference-cohort extraction, P-SEA/DSSP comparison, screen validation, confidence
calibration, independent fold or wet-lab validation was performed for this note.
