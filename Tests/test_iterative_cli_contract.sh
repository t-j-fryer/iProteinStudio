#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNNER="${REPO_ROOT}/Sources/iProteinStudio/Resources/pipeline/nanohunter_run.sh"
SELECTOR="${REPO_ROOT}/Sources/iProteinStudio/Resources/pipeline/scripts/select_post_tasks.py"
FIXTURE_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/iproteinstudio-cli-contract.XXXXXX")"
trap 'rm -rf "${FIXTURE_ROOT}"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
expect_text() {
  local text="$1" pattern="$2" message="$3"
  printf '%s\n' "${text}" | rg -q -- "${pattern}" || fail "${message}: ${text}"
}
make_executable() {
  local path="$1"
  mkdir -p "$(dirname "${path}")"
  printf '#!/bin/sh\nexit 0\n' > "${path}"
  chmod +x "${path}"
}

set +e
setup_error="$(NANOHUNTER_ROOT="${FIXTURE_ROOT}" \
  bash "${REPO_ROOT}/Sources/iProteinStudio/Resources/pipeline/setup_pipeline.sh" \
  --with-alphafold3 2>&1)"
setup_status=$?
set -e
[[ "${setup_status}" -ne 0 ]] || fail "retired AlphaFold 3 setup flag unexpectedly passed"
expect_text "${setup_error}" 'retired after Metal quality-control failures' \
  "retired setup flag had no actionable explanation"

mkdir -p \
  "${FIXTURE_ROOT}/src/LigandMPNN/model_params" \
  "${FIXTURE_ROOT}/src/IntelliFold" \
  "${FIXTURE_ROOT}/scripts"
make_executable "${FIXTURE_ROOT}/venvs/Test_boltz/bin/python"
make_executable "${FIXTURE_ROOT}/venvs/Test_ligandmpnn/bin/python"
make_executable "${FIXTURE_ROOT}/venvs/Test_intellifold/bin/python"
make_executable "${FIXTURE_ROOT}/venvs/Test_protenix_constraint/bin/python"
touch \
  "${FIXTURE_ROOT}/src/LigandMPNN/run.py" \
  "${FIXTURE_ROOT}/src/LigandMPNN/model_params/solublempnn_v_48_020.pt" \
  "${FIXTURE_ROOT}/src/LigandMPNN/model_params/abmpnn.pt" \
  "${FIXTURE_ROOT}/src/IntelliFold/run_intellifold.py"
cp "${SELECTOR}" "${FIXTURE_ROOT}/scripts/select_post_tasks.py"
cp "${REPO_ROOT}/Sources/iProteinStudio/Resources/pipeline/scripts/find_target_msa.py" \
  "${FIXTURE_ROOT}/scripts/find_target_msa.py"
cp "${REPO_ROOT}/Sources/iProteinStudio/Resources/pipeline/scripts/intellifold_predict.py" \
  "${FIXTURE_ROOT}/scripts/intellifold_predict.py"
cp "${REPO_ROOT}/Sources/iProteinStudio/Resources/pipeline/scripts/protenix_predict.py" \
  "${FIXTURE_ROOT}/scripts/protenix_predict.py"
cp "${REPO_ROOT}/Sources/iProteinStudio/Resources/pipeline/scripts/resident_predictor.py" \
  "${FIXTURE_ROOT}/scripts/resident_predictor.py"
mkdir -p "${FIXTURE_ROOT}/models/protenix_constraint/checkpoint"
touch "${FIXTURE_ROOT}/models/protenix_constraint/checkpoint/protenix_base_constraint_v0.5.0.pt"
printf '{}\n' > "${FIXTURE_ROOT}/models/protenix_constraint/install_receipt.json"
mkdir -p "${FIXTURE_ROOT}/msa_cache"

cat > "${FIXTURE_ROOT}/protein_hotspot.yaml" <<'YAML'
nanohunter:
  target_epitope_residues: [B34, B35]
  boltz_contact_mode: auto
sequences:
  - protein:
      id: A
      sequence: GGGGGGGG
      msa: empty
  - protein:
      id: B
      sequence: MKTIIALSYIFCLVFADYKDDDDK
      msa: empty
version: 1
YAML

cat > "${FIXTURE_ROOT}/msa_cache/exact_target.a3m" <<'A3M'
>query
MKTIIALSYIFCLVFADYKDDDDK
>homologue
MKTIIALSYIFCLVFADYKDDDDK
A3M

cat > "${FIXTURE_ROOT}/nanobody_hotspot.yaml" <<'YAML'
nanohunter:
  target_epitope_residues: [B34, B35]
  boltz_contact_mode: auto
sequences:
  - protein:
      id: A
      sequence: EVQLVESGGGLVQAGGSLRLSCAASGFTFSSYAMSWVRQAPGKGLEWVSAISGSGGSTYYADSVKGRFTISRDNAKNTVYLQMNSLKPEDTAVYYCAAAGGGYWGQGTQVTVSS
      msa: empty
  - protein:
      id: B
      sequence: MKTIIALSYIFCLVFADYKDDDDK
      msa: empty
version: 1
YAML

cat > "${FIXTURE_ROOT}/protein_plain.yaml" <<'YAML'
sequences:
  - protein:
      id: A
      sequence: GGGGGGGG
      msa: empty
  - protein:
      id: B
      sequence: MKTIIALSYIFCLVFADYKDDDDK
      msa: empty
version: 1
YAML

common=(
  --workflow protein
  --sequence-designer solublempnn
  --target-msa-mode off
  --max-parallel 1
  --throughput-profile off
  --check-config
)

output="$(NANOHUNTER_ROOT="${FIXTURE_ROOT}" NANOHUNTER_VENV_PREFIX=Test \
  bash "${RUNNER}" "${common[@]}" --predictor boltz \
  --template-yaml "${FIXTURE_ROOT}/protein_hotspot.yaml" \
  --post-predictor none --post-mode none)"
expect_text "${output}" 'contact_mode=pocket' "protein hotspots did not resolve to a generic pocket"
expect_text "${output}" 'intellifold_model=unused' "irrelevant IntelliFold model was reported as active"
expect_text "${output}" 'post=none' "empty checker list was not explicit"

output="$(NANOHUNTER_ROOT="${FIXTURE_ROOT}" NANOHUNTER_VENV_PREFIX=Test \
  bash "${RUNNER}" "${common[@]}" --predictor boltz \
  --template-yaml "${FIXTURE_ROOT}/protein_plain.yaml" \
  --predictor-seed 73 --predictor-samples 1 \
  --post-predictor none --post-mode none)"
expect_text "${output}" 'predictor_seed=73' "predictor seed was not recorded"
expect_text "${output}" 'predictor_samples=1' "predictor sample count was not recorded"

output="$(NANOHUNTER_ROOT="${FIXTURE_ROOT}" NANOHUNTER_VENV_PREFIX=Test \
  bash "${RUNNER}" "${common[@]}" --predictor boltz \
  --template-yaml "${FIXTURE_ROOT}/protein_plain.yaml" \
  --design-scheduler resident --wave-batch-size all \
  --post-predictor none --post-mode none)"
expect_text "${output}" 'scheduler=resident' "resident scheduler was not accepted as a distinct mode"

resident_launcher="$(sed -n '/start_resident_predictor()/,/stop_resident_predictor()/p' "${RUNNER}")"
expect_text "${resident_launcher}" 'if \[\[ "\$\{PREDICTOR\}" == "intellifold" \]\]' \
  "resident launcher lost the IntelliFold-only thread guard"
expect_text "${resident_launcher}" 'resident_environment=\("PYTORCH_ENABLE_MPS_FALLBACK=0"\)' \
  "resident launcher no longer rejects silent MPS fallback"

set +e
output="$(NANOHUNTER_ROOT="${FIXTURE_ROOT}" NANOHUNTER_VENV_PREFIX=Test \
  bash "${RUNNER}" --workflow protein --sequence-designer solublempnn \
  --target-msa-mode off --max-parallel 1 --throughput-profile off \
  --skip-predictor-calibration --num-runs 1 --num-opt-cycles 0 \
  --run-name bucket_contract --out-root "${FIXTURE_ROOT}/output" \
  --predictor intellifold --model v2-flash \
  --template-yaml "${FIXTURE_ROOT}/protein_plain.yaml" \
  --random-binder --binder-min-len 65 --binder-max-len 150 \
  --intellifold-buckets length-aware \
  --post-predictor none --post-mode none 2>&1)"
set -e
expect_text "${output}" 'IntelliFold=96,128,160,174' \
  "length-aware IntelliFold buckets did not cover the exact 89-174 token regime"

set +e
error="$(NANOHUNTER_ROOT="${FIXTURE_ROOT}" NANOHUNTER_VENV_PREFIX=Test \
  bash "${RUNNER}" "${common[@]}" --predictor boltz \
  --template-yaml "${FIXTURE_ROOT}/protein_plain.yaml" \
  --predictor-samples 0 --post-predictor none --post-mode none 2>&1)"
status=$?
set -e
[[ "${status}" -ne 0 ]] || fail "zero predictor samples unexpectedly passed"
expect_text "${error}" 'positive integer' "invalid predictor sample failure was not actionable"

# The cycle-wave validator and executor must agree on Protenix support. This
# source-level contract prevents the advertised mode from silently losing its
# adapter branch again; the real MPS execution is recorded in the Lab Book.
expect_text "$(sed -n '/run_cycle_wave_predictor_batch()/,/record_cycle_wave_predictions()/p' "${RUNNER}")" \
  'protenix-v2|protenix-mini|protenix-constraint-v0.5' \
  "cycle-wave executor lost its Protenix branch"
expect_text "$(sed -n '/run_cycle_wave_predictor_batch()/,/record_cycle_wave_predictions()/p' "${RUNNER}")" \
  '--inputs "\$\{input_dir\}"' "cycle-wave Protenix did not use directory input"

SETUP="${REPO_ROOT}/Sources/iProteinStudio/Resources/pipeline/setup_pipeline.sh"
ZERO_SUBSTRUCTURE_PATCH="${REPO_ROOT}/Sources/iProteinStudio/Resources/pipeline/patches/protenix_constraint_zero_substructure.patch"
[[ -s "${ZERO_SUBSTRUCTURE_PATCH}" ]] \
  || fail "Protenix Constraint zero-substructure patch is missing"
expect_text "$(cat "${ZERO_SUBSTRUCTURE_PATCH}")" 'torch.count_nonzero\(x\)' \
  "constraint patch lost its absent-feature guard"
expect_text "$(cat "${ZERO_SUBSTRUCTURE_PATCH}")" 'self.transformer\(x\)' \
  "constraint patch no longer preserves the checkpoint-defined learned baseline"
expect_text "$(cat "${SETUP}")" 'PROTENIX_CONSTRAINT_ZERO_SUBSTRUCTURE_PATCH' \
  "installer does not apply the constraint memory patch"
expect_text "$(cat "${SETUP}")" 'zero_substructure_patch_sha256' \
  "constraint install detection does not fingerprint the memory patch"
expect_text "$(cat "${REPO_ROOT}/Sources/iProteinStudio/Resources/pipeline/scripts/protenix_predict.py")" \
  'checkpoint-equivalent-single-token-broadcast' \
  "constraint launch does not reject an outdated engine runtime"

output="$(NANOHUNTER_ROOT="${FIXTURE_ROOT}" NANOHUNTER_VENV_PREFIX=Test \
  bash "${RUNNER}" "${common[@]}" --predictor protenix-constraint-v0.5 \
  --template-yaml "${FIXTURE_ROOT}/protein_hotspot.yaml" \
  --post-predictor none --post-mode none)"
expect_text "${output}" 'predictor=protenix-constraint-v0.5' \
  "constraint design engine was not accepted with target hotspots"

set +e
error="$(NANOHUNTER_ROOT="${FIXTURE_ROOT}" NANOHUNTER_VENV_PREFIX=Test \
  bash "${RUNNER}" "${common[@]}" --predictor boltz \
  --template-yaml "${FIXTURE_ROOT}/protein_plain.yaml" \
  --post-predictor protenix-constraint-v0.5 --post-mode final 2>&1)"
status=$?
set -e
[[ "${status}" -ne 0 ]] || fail "guided constraint checkpoint was accepted as a post-predictor"
expect_text "${error}" 'guided design engine, not an independent post-predictor' \
  "constraint post-check rejection was not actionable"

output="$(python3 "${FIXTURE_ROOT}/scripts/find_target_msa.py" \
  --sequence MKTIIALSYIFCLVFADYKDDDDK --roots "${FIXTURE_ROOT}/msa_cache")"
expected_msa="$(cd "${FIXTURE_ROOT}/msa_cache" && pwd -P)/exact_target.a3m"
[[ "${output}" == "${expected_msa}" ]] \
  || fail "iterative design cache lookup did not return the exact target MSA: ${output}"
[[ -z "$(python3 "${FIXTURE_ROOT}/scripts/find_target_msa.py" \
  --sequence ACDEFGHIK --roots "${FIXTURE_ROOT}/msa_cache")" ]] \
  || fail "iterative design cache lookup accepted a mismatched MSA"

output="$(NANOHUNTER_ROOT="${FIXTURE_ROOT}" NANOHUNTER_VENV_PREFIX=Test \
  bash "${RUNNER}" --workflow nanobody --predictor boltz \
  --sequence-designer abmpnn --scaffold-from-template --nanobody-no-scaffold-msa \
  --target-msa-mode off --max-parallel 1 --throughput-profile off --check-config \
  --template-yaml "${FIXTURE_ROOT}/nanobody_hotspot.yaml" \
  --post-predictor none --post-mode none)"
expect_text "${output}" 'contact_mode=pocket\+cdr3' "nanobody hotspots lost their CDR3-specific contact"

output="$(NANOHUNTER_ROOT="${FIXTURE_ROOT}" NANOHUNTER_VENV_PREFIX=Test \
  bash "${RUNNER}" "${common[@]}" --predictor boltz \
  --template-yaml "${FIXTURE_ROOT}/protein_plain.yaml" \
  --post-predictor none --post-mode none --post-iptm-threshold 0.66 2>/dev/null)"
expect_text "${output}" 'hit_threshold=0.66' "legacy no-checker manifest lost its visible hit threshold"

set +e
error="$(NANOHUNTER_ROOT="${FIXTURE_ROOT}" NANOHUNTER_VENV_PREFIX=Test \
  bash "${RUNNER}" "${common[@]}" --predictor intellifold \
  --template-yaml "${FIXTURE_ROOT}/protein_hotspot.yaml" \
  --post-predictor none --post-mode none 2>&1)"
status=$?
set -e
[[ "${status}" -ne 0 ]] || fail "non-Boltz hotspot request unexpectedly passed"
expect_text "${error}" 'require Boltz or Protenix Constraint' "unsupported hotspot failure was not actionable"

set +e
error="$(NANOHUNTER_ROOT="${FIXTURE_ROOT}" NANOHUNTER_VENV_PREFIX=Test \
  bash "${RUNNER}" "${common[@]}" --predictor boltz \
  --template-yaml "${FIXTURE_ROOT}/protein_plain.yaml" \
  --post-predictor alphafold3 --post-mode final 2>&1)"
status=$?
set -e
[[ "${status}" -ne 0 ]] || fail "retired AlphaFold 3 post-check unexpectedly passed"
expect_text "${error}" 'Retired predictor' "AlphaFold 3 retirement failure was not actionable"

set +e
error="$(NANOHUNTER_ROOT="${FIXTURE_ROOT}" NANOHUNTER_VENV_PREFIX=Test \
  bash "${RUNNER}" "${common[@]}" --predictor intellifold-jax \
  --template-yaml "${FIXTURE_ROOT}/protein_plain.yaml" \
  --post-predictor none --post-mode none 2>&1)"
status=$?
set -e
[[ "${status}" -ne 0 ]] || fail "retired IntelliFold JAX design predictor unexpectedly passed"
expect_text "${error}" 'Retired predictor' "IntelliFold JAX retirement failure was not actionable"

output="$(NANOHUNTER_ROOT="${FIXTURE_ROOT}" NANOHUNTER_VENV_PREFIX=Test \
  bash "${RUNNER}" "${common[@]}" --predictor boltz \
  --template-yaml "${FIXTURE_ROOT}/protein_plain.yaml" \
  --post-predictor intellifold --post-mode final-iptm --model v2)"
expect_text "${output}" 'post=intellifold' "IntelliFold post-check was not routed"
expect_text "${output}" 'post_mode=final-iptm' "final hit-gated checking mode was not accepted"
expect_text "${output}" 'intellifold_model=v2' "selected IntelliFold architecture was not active"

set +e
error="$(NANOHUNTER_ROOT="${FIXTURE_ROOT}" NANOHUNTER_VENV_PREFIX=Test \
  bash "${RUNNER}" "${common[@]}" --predictor boltz \
  --template-yaml "${FIXTURE_ROOT}/protein_plain.yaml" \
  --post-predictor boltz --post-mode final 2>&1)"
status=$?
set -e
[[ "${status}" -ne 0 ]] || fail "self-checking predictor unexpectedly passed"
expect_text "${error}" 'must be independent' "self-check failure was not actionable"

cat > "${FIXTURE_ROOT}/summary.csv" <<'CSV'
run,cycle,iptm,complex_plddt,binder_sequence,structure_path,confidence_json
1,0,0.60,0.8,SEED1,a,b
1,1,0.90,0.8,EARLY1,a,b
1,5,0.75,0.8,FINAL1,a,b
2,0,0.55,0.8,SEED2,a,b
2,1,0.95,0.8,EARLY2,a,b
2,5,0.65,0.8,FINAL2,a,b
CSV
python3 "${SELECTOR}" --summary "${FIXTURE_ROOT}/summary.csv" \
  --mode final-iptm --threshold 0.70 --include-cycle00 0 \
  --output "${FIXTURE_ROOT}/tasks.tsv" >/dev/null
[[ "$(wc -l < "${FIXTURE_ROOT}/tasks.tsv" | tr -d ' ')" == "1" ]] \
  || fail "final-iptm selected an intermediate cycle or a below-threshold final"
expect_text "$(cat "${FIXTURE_ROOT}/tasks.tsv")" $'1\t5\tFINAL1' "wrong final post-prediction task selected"

python3 "${SELECTOR}" --summary "${FIXTURE_ROOT}/summary.csv" \
  --mode all --threshold 0.70 --include-cycle00 1 \
  --output "${FIXTURE_ROOT}/all_tasks.tsv" >/dev/null
[[ "$(wc -l < "${FIXTURE_ROOT}/all_tasks.tsv" | tr -d ' ')" == "6" ]] \
  || fail "all-cycle checking did not retain every available checkpoint"

echo "PASS iterative CLI contract"
