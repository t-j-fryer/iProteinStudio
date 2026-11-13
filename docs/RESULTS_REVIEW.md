# Results review

The Overview chooses **ipSAE(min)** when available for protein designs.
Small-molecule designs choose **Boltz combined score**:
`P(bind) + ligand pLDDT/100` (0–2, higher is better). The two components must
belong to the same assessment. If this score is unavailable, choose another
recorded metric in the picker; missing components are never treated as zero.
Protein predictions without ipSAE use another available confidence metric.

Below the score distribution, the cycle chart shows the **median of all scored
candidates in each recorded cycle**. It includes proposals that were not
selected for the next generation. Duplicate files do not add extra weight.
Unoptimized starting structures are excluded. Lines keep score sources and
assessment types separate. The stage/source/framework filters above apply to
both plots. NISE additionally keeps phases separate using its phase selector.
Runs without recorded cycle identity have no cycle plot.

In **Hits**, choose **Saved verdicts** to see the original hit decisions, or
**Custom filters** to define a retrospective selection. Add any available
metric, choose ≥, ≤, > or <, and type the threshold. All rules must pass.
A missing or nonfinite score fails that rule. With no custom rules, all scored
candidates are included; the UI states this explicitly.

Scores are associated with a single cycle or sequence derivative. When that
design has a complex reprediction, its available scores take precedence over
the design structure; binder-alone values supply metrics absent from both.
Use the stage and score-source selectors to review one assessment type or engine
at a time. Original verdicts and raw scientific files are unchanged. Review
settings are remembered per run, separately in public and Beta preferences.

Choose the sort metric and **Highest first** or **Lowest first**. Missing scores
sort last. **Maximum per family** is applied after ranking, so it keeps the best
X designs under the chosen sort order. Zero or blank means unlimited.

**Export Hits CSV…** saves the displayed selection in its current order. Columns
include design name, recorded design sequence, family/design identifiers,
recorded cycle, original saved verdict, selection mode, score sources and all
available scores. Missing values and unrecorded sequences are blank; the UI
warns about missing sequences before export. pLDDT columns use 0–100, pocket
fractions use percent, and distances use Å. Text is quoted and spreadsheet
formula prefixes are escaped. Selecting an export destination does not change
the original results.

Large datasets use25-item pages for families, candidates and hits. Rules, sorting,
family limits and CSV export operate on the entire matching set. Artifact cards
load the chosen structure in one interactive viewer instead of creating a
renderer per card. Overview/Hits calculations and CSV writes run in the
background; superseded filter requests cannot overwrite a newer selection.

Live refresh reuses unchanged checked snapshots. Coordinate/score metadata and
live chunk receipts invalidate the cache; the Refresh button forces a reread.
The scientific job's saved decisions and resume validation are independent of
this display cache.

The selected structure's **External viewer** menu lets you choose an installed
ChimeraX or other compatible viewer application. Studio remembers the app and
hands it the local PDB/CIF through macOS. Installation of a third-party viewer is
optional. Original structures remain in their run directories.

Protein/ligand proximity, burial and exact recorded geometry review are described
in [Spatial review and manuscript-style opening](RESULTS_SPATIAL_REVIEW.md). The
ChimeraX manuscript preset and script export are also available from prediction
results, the Predict pane and reusable prediction-library entries.

## CLI and MCP

Bridge61 exposes `results_review` with the current run ID, optional metric,
`mode` (`all`, `saved`, `custom`), AND `rules` (`metric`, `comparison` from
`>=`, `<=`, `>`, `<`, numeric `threshold`), sort direction and `max_per_family`.
Missing/nonfinite scores fail rules and sort last. The first page returns a
`snapshot_sha256`; supply it on later pages (`offset`, `limit`, maximum100) so
changed results cannot silently change the selection. Source-specific metrics
are retained; optional `predictor` and `role` restrict the assessments. Cycle
medians include all recorded proposals before retrospective thresholds/caps,
separated by predictor, artifact role and context.

`results_review_export` applies the same selection to the whole bounded index,
not only the current page, and creates a ZIP containing `designs.csv` and
`review.json`. The CSV has design name, recorded sequence, stable IDs, cycle,
saved verdict and measured scores; JSON retains metric source and spatial
provenance. Blank sequences/scores remain blank. Text cells are protected against
spreadsheet formula interpretation. Use `export_read` to retrieve the archive.
The existing20,000-candidate bound fails explicitly rather than truncating.
A source scan beyond the bound must be narrowed to a child campaign.

`memory_estimate(plan_id, plan_sha256)` reads the fitted report for a saved plan;
it never starts work or changes admission. Use `studioctl tools --profile run`
for the exact deployed schemas and `studioctl call` for CLI access.
