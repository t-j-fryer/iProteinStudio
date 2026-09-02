#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RESULTS="$ROOT/Sources/iProteinStudio/Views/RunResultsView.swift"
MODEL="$ROOT/Sources/iProteinStudio/Models/RunResult.swift"
RFD3="$ROOT/Sources/iProteinStudio/Views/RFD3/RFD3View.swift"
GENERATOR="$ROOT/Sources/iProteinStudio/Resources/rfd3_overlay/scripts/generate_backbones.py"
BINS="$ROOT/Sources/iProteinStudio/Resources/rfd3_overlay/scripts/run_backbone_bins.py"

grep -q 'import Charts' "$RESULTS"
grep -q 'case overview = "Overview"' "$RESULTS"
grep -q 'MetricDistributionChart' "$RESULTS"
grep -q 'effectiveDistributionMetric' "$RESULTS"
grep -q 'DistributionStatistic' "$RESULTS"
grep -q 'Browse Live Results' "$RFD3"
grep -q 'liveRFD3Backbones' "$MODEL"
grep -q 'liveRFD3Predictions' "$MODEL"
grep -q 'Motif correspondence' "$RESULTS"
grep -q 'motifPredictionRMSD' "$MODEL"
grep -q -- '--motif-atoms-json' "$GENERATOR"
grep -q -- '--motif-atoms-json' "$BINS"

echo "RFdiffusion3 live results and motif-analysis UI contract: PASS"
