# Nanobody scaffolds and trajectory budgets

In **Protein Hunter**, select **Nanobody** and use the **Nanobody scaffolds &
budget** checklist to choose one or more VHH frameworks. The selected CDRs,
target, cycle count and other shared settings apply to every selected scaffold.
Each campaign saves its exact scaffold sequence and resolved CDR positions.

**Total trajectories per engine** is shared among the selected scaffolds.
Every selected design engine receives that same allocation. With 70 trajectories,
seven scaffolds and two engines, each scaffold gets 10 trajectories from each
engine: 140 trajectories overall. Selecting more engines adds work.

**Split trajectories equally** is on by default. If the total does not divide
evenly, the first scaffolds selected receive one extra trajectory. For example,
72 across seven scaffolds gives 11, 11, 10, 10, 10, 10, 10. Adding scaffolds raises
the total only when necessary to give each at least one trajectory.

Turn off equal splitting to edit the trajectory count beside each selected
scaffold. The total updates automatically; it is the sum of those rows. Switching
back to equal splitting redistributes that total. Clearing every scaffold blocks
Start. Existing workspaces retain their previous single scaffold and full budget.

## Saved campaigns and recovery

Studio prepares every engine–scaffold campaign before submitting the batch.
Engines run in checklist order, and scaffolds run in selection order within each
engine. Each pair has its own campaign directory, inputs, immutable workflow
snapshot, results and resume checkpoints. The dashboard follows the active pair.
Completed pairs are skipped on Resume only after their saved outputs are checked.

Each child uses the engine's existing resident-worker or cycle-wave scheduler.
Workers are not shared between separate scaffold campaigns. The batch runs
sequentially under the shared execution lock; choosing more scaffolds does not
load more models concurrently. No new throughput measurement is claimed here.

## 3EAK NbBCII10-FGLA VHH

The eighth available scaffold comes from the supplied RCSB FASTA for 3EAK
(the sequence is shared by chains A and B). At the user's request, the terminal
`RGRHHHHHH` purification tail is removed: the saved VHH has 128 residues rather
than the deposited 137. It is available as a checkbox and is not selected
automatically in existing workspaces.

Its CDR boundaries were transferred by the existing alignment resolver from the
catalog's Caplacizumab scaffold at 77% sequence identity. These are **inferred
boundaries, not independently validated antibody numbering**. This provenance
appears in the catalog, resolver output and
[`3eak_provenance.json`](../Sources/iProteinStudio/Resources/pipeline/examples/nanobody_scaffolds/sources/3eak_provenance.json).
The original FASTA is retained alongside that record with integrity hashes.

No MSA is bundled for 3EAK. With the normal masked-CDR alignment policy, the
pipeline generates and persistently caches a full scaffold alignment on first
use. Failure to obtain that alignment stops the run; it does not silently use a
single-sequence substitute. No new inference campaign or MSA generation was run
as part of this catalog addition.

Workflow updates wait for active jobs to finish. Studio reloads the catalog after
a deferred update, so the new scaffold becomes available without another restart.

See [design engine selection](PROTEIN_HUNTER_ENGINES.md) for batch behavior and
[Lab Book 0119](../lab_book/0119-nanobody-scaffold-budgets.md) for validation.
