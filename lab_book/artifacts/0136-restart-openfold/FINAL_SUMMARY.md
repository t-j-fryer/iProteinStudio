# Completed Bgx design queue

Verified from all 70 campaign manifests and summary CSVs on 2026-09-17.
All three batches targeted α-cobratoxin. Every campaign is now marked completed.
This summary covers the three desktop batches discussed in this conversation.

| Batch | Design setup | Trajectories per engine | Optimization cycles | Optimized cycle outputs, all engines |
|---|---|---:|---:|---:|
| Mini-binders, helix strength 0 (`6ed978fa`) | SolubleMPNN, 65–150 residues; initialization helix suppression disabled | 50 | 5 | 1,750 |
| Mini-binders, helix strength 1 (`06751263`) | SolubleMPNN, 65–120 residues; initialization helix suppression at strength 1 | 50 | 5 | 1,750 |
| Nanobodies (`f45742c3`) | AbMPNN, eight existing VHH scaffolds, all three CDRs redesigned | 50 shared across scaffolds | 5 | 1,750 |

Each batch used seven design predictors: Boltz-2, Protenix Constraint v0.5
(experimental), Protenix v2, Protenix Mini, IntelliFold v2 Flash, IntelliFold v2
Full, and OpenFold-3. Every engine received the full 50-trajectory budget in
each batch, producing 250 optimized cycle outputs plus 50 starting structures.

## Nanobody allocation per engine

| Scaffold | Trajectories | Optimized cycle outputs |
|---|---:|---:|
| Vobarilizumab | 7 | 35 |
| Caplacizumab | 7 | 35 |
| Gefurulimab / TPP-3444 | 6 | 30 |
| Ozoralizumab ALB8 | 6 | 30 |
| Gontivimab | 6 | 30 |
| Isecarosmab | 6 | 30 |
| Sonelokimab | 6 | 30 |
| NbBCII10-FGLA / 3EAK | 6 | 30 |
| Total per engine | 50 | 250 |

## Final accounting

- 70 engine/scaffold campaigns: seven in each minibinder batch and 56 in the nanobody batch.
- 1,050 trajectories, each with a starting structure and five optimized cycles.
- 5,250 optimized run/cycle outputs, including 1,050 final-cycle outputs.
- 1,050 additional cycle-00 starting structures: 6,300 total run/cycle structures.

The six non-OpenFold engines completed 4,500 optimized outputs before recovery.
OpenFold's unsupported scheduler stopped ten campaigns before inference. After
correction, those ten campaigns completed the remaining 750 optimized outputs;
completed work from other engines was not rerun.

These totals count run/cycle records, not unique sequences or confirmed binders.
No independent post-design prediction checks were requested in the saved settings.
This is a completion/setup summary, not a ranking of engines or candidates.
The two minibinder batches also used different length ranges and seeds, so they
are not a matched test of helix suppression alone.
