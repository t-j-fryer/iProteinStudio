#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${PROTEINHUNTER_ROOT:-${IPROTEINHUNTER_ROOT:-${NANOHUNTER_ROOT:-$SCRIPT_DIR}}}"

# One implementation serves both the original iProteinHunter protein-binder
# workflow and NanoHunter fixed-scaffold nanobody design.  Resolve the workflow
# before assigning defaults so `--workflow protein` receives protein-safe
# defaults without requiring a compatibility wrapper.
WORKFLOW="${PROTEINHUNTER_WORKFLOW_DEFAULT:-${NANOHUNTER_WORKFLOW_DEFAULT:-nanobody}}"
_workflow_args=("$@")
for ((_workflow_i = 0; _workflow_i < ${#_workflow_args[@]}; _workflow_i++)); do
  case "${_workflow_args[_workflow_i]}" in
    --workflow|--design-mode)
      ((_workflow_i + 1 < ${#_workflow_args[@]})) || {
        echo "ERROR: ${_workflow_args[_workflow_i]} requires protein or nanobody." >&2
        exit 2
      }
      WORKFLOW="${_workflow_args[_workflow_i + 1]}"
      ;;
    --workflow=*|--design-mode=*)
      WORKFLOW="${_workflow_args[_workflow_i]#*=}"
      ;;
  esac
done
unset _workflow_args _workflow_i
WORKFLOW="$(printf '%s' "${WORKFLOW}" | tr '[:upper:]' '[:lower:]' | tr '_' '-')"
case "${WORKFLOW}" in
  protein|protein-binder|binder|iproteinhunter) WORKFLOW="protein" ;;
  nanobody|vhh|nanohunter) WORKFLOW="nanobody" ;;
  *)
    echo "ERROR: --workflow must be protein or nanobody (got: ${WORKFLOW})." >&2
    exit 2
    ;;
esac

if [[ "${WORKFLOW}" == "nanobody" ]]; then
  DEFAULT_TEMPLATE_YAML="${REPO_ROOT}/examples/NanoHunter_nanobody.yaml"
  DEFAULT_POST_PREDICTOR="intellifold"
  DEFAULT_SCAFFOLD_FROM_TEMPLATE=1
  DEFAULT_SEQUENCE_DESIGNER="antifold"
  DEFAULT_NANOBODY_SEED_MODE="cdr-random"
  DEFAULT_NANOBODY_SEED_PERCENT_X=50
  DEFAULT_NANOBODY_SCAFFOLD_MSA_MODE="masked-cdr"
else
  DEFAULT_TEMPLATE_YAML="${REPO_ROOT}/examples/aCbx_bind.yaml"
  DEFAULT_POST_PREDICTOR="none"
  DEFAULT_SCAFFOLD_FROM_TEMPLATE=0
  DEFAULT_SEQUENCE_DESIGNER="auto"
  DEFAULT_NANOBODY_SEED_MODE="native"
  DEFAULT_NANOBODY_SEED_PERCENT_X=0
  DEFAULT_NANOBODY_SCAFFOLD_MSA_MODE="off"
fi

APP_NAME="${PROTEINHUNTER_APP_NAME:-${IPROTEINHUNTER_APP_NAME:-${NANOHUNTER_APP_NAME:-NanoHunter + iProteinHunter}}}"
RUNNER_DISPLAY_NAME="${RUNNER_DISPLAY_NAME:-$(basename "$0")}"
VENV_PREFIX="${PROTEINHUNTER_VENV_PREFIX:-${IPROTEINHUNTER_VENV_PREFIX:-${NANOHUNTER_VENV_PREFIX:-NanoHunter}}}"

BOLTZ_VENV="${REPO_ROOT}/venvs/${VENV_PREFIX}_boltz"
LIGAND_VENV="${REPO_ROOT}/venvs/${VENV_PREFIX}_ligandmpnn"
ANTIFOLD_VENV="${REPO_ROOT}/venvs/${VENV_PREFIX}_antifold"
INTELLIFOLD_VENV="${REPO_ROOT}/venvs/${VENV_PREFIX}_intellifold"
PROTENIX_VENV="${REPO_ROOT}/venvs/${VENV_PREFIX}_protenix"
PROTENIX_CONSTRAINT_VENV="${REPO_ROOT}/venvs/${VENV_PREFIX}_protenix_constraint"
OPENFOLD_VENV="${REPO_ROOT}/venvs/${VENV_PREFIX}_openfold3_mlx"

BOLTZ_CLI="boltz"
INTELLIFOLD_CLI="intellifold"
OPENFOLD_CLI="run_openfold"
INTELLIFOLD_CACHE_DIR="${INTELLIFOLD_CACHE:-${REPO_ROOT}/models/intellifold}"
PROTENIX_MODEL_DIR="${PROTENIX_ROOT_DIR:-${REPO_ROOT}/models/protenix}"
PROTENIX_CONSTRAINT_MODEL_DIR="${REPO_ROOT}/models/protenix_constraint"
PROTENIX_ADAPTER="${REPO_ROOT}/scripts/protenix_predict.py"
RESIDENT_PREDICTOR="${REPO_ROOT}/scripts/resident_predictor.py"
OPENFOLD_CACHE_DIR="${OPENFOLD_CACHE:-${REPO_ROOT}/models/openfold3}"
OPENFOLD_CHECKPOINT_PATH="${OPENFOLD_CACHE_DIR}/of3_ft3_v1.pt"
BOLTZ_CACHE="${BOLTZ_CACHE:-${REPO_ROOT}/models/boltz2}"
NUMBA_CACHE_DIR="${NUMBA_CACHE_DIR:-${REPO_ROOT}/numba_cache}"
export BOLTZ_CACHE NUMBA_CACHE_DIR
mkdir -p "${NUMBA_CACHE_DIR}"
OPENFOLD_A3M_QUERY_REWRITER="${REPO_ROOT}/scripts/rewrite_a3m_query.py"
POST_TASK_SELECTOR="${REPO_ROOT}/scripts/select_post_tasks.py"
IPSAE_SCORER="${REPO_ROOT}/scripts/ipsae_score.py"

LIGANDMPNN_REPO="${REPO_ROOT}/src/LigandMPNN"
LIGANDMPNN_RUN="python run.py"
LIGANDMPNN_CHECKPOINT_PROTEIN="${LIGANDMPNN_REPO}/model_params/proteinmpnn_v_48_020.pt"
LIGANDMPNN_CHECKPOINT_SOLUBLE="${LIGANDMPNN_REPO}/model_params/solublempnn_v_48_020.pt"
LIGANDMPNN_CHECKPOINT_LIGAND="${LIGANDMPNN_REPO}/model_params/ligandmpnn_v_32_010_25.pt"
# AbMPNN: antibody-fine-tuned ProteinMPNN (Zenodo 10.5281/zenodo.8164693), runs on the
# ProteinMPNN architecture, so it loads via --model_type protein_mpnn.
LIGANDMPNN_CHECKPOINT_ABMPNN="${LIGANDMPNN_REPO}/model_params/abmpnn.pt"
# LASErMPNN: ligand-aware inverse folder (Fry, Slaw & Polizzi, Nature 2026).
# Only wired in for small-molecule minibinder design (--workflow protein + ligand).
# torch_cluster/torch_scatter kernels are CPU-only, so LASErMPNN runs on CPU on
# Apple Silicon (MPS is unsupported); inference is fast enough that this is fine.
LASERMPNN_VENV="${REPO_ROOT}/venvs/${VENV_PREFIX}_lasermpnn"
LASERMPNN_REPO="${REPO_ROOT}/src/LASErMPNN"
LASERMPNN_WEIGHTS="${LASERMPNN_REPO}/model_weights/laser_weights_0p1A_nothing_heldout.pt"
LASERMPNN_PREPARE="${REPO_ROOT}/scripts/lasermpnn_prepare_input.py"
LASERMPNN_SEEDED_RUNNER="${REPO_ROOT}/scripts/run_lasermpnn_seeded.py"
LASERMPNN_DEVICE="${LASERMPNN_DEVICE:-cpu}"
LASERMPNN_NUM_SEQ="${LASERMPNN_NUM_SEQ:-1}"
LASERMPNN_SEQ_TEMP="${LASERMPNN_SEQ_TEMP:-0.1}"
LASERMPNN_FS_TEMP="${LASERMPNN_FS_TEMP:-1.0}"
LASERMPNN_SEED="${LASERMPNN_SEED:-0}"
LASERMPNN_LIGAND_SMILES=""
LASERMPNN_EXTRA_FLAGS=()
ANTIFOLD_REPO="${REPO_ROOT}/src/AntiFold"
ANTIFOLD_RUN="python antifold/main.py"
ANTIFOLD_EXACT_SAMPLER="${REPO_ROOT}/scripts/sample_antifold_positions.py"
INTELLIFOLD_REPO="${REPO_ROOT}/src/IntelliFold"
INTELLIFOLD_UPSTREAM_RUNNER="${INTELLIFOLD_REPO}/run_intellifold.py"
INTELLIFOLD_RUNNER="${REPO_ROOT}/scripts/intellifold_predict.py"
# IntelliFold's CPU-side BLAS/OpenMP work contends with MPS command submission
# when every process uses all performance cores. Paired M4 Max benchmarks found
# one thread faster with byte-identical structures; users can override either.
INTELLIFOLD_OMP_NUM_THREADS="${NANOHUNTER_INTELLIFOLD_OMP_NUM_THREADS:-1}"
INTELLIFOLD_VECLIB_MAXIMUM_THREADS="${NANOHUNTER_INTELLIFOLD_VECLIB_MAXIMUM_THREADS:-1}"
# IntelliFold's PyTorch/MPS runner historically padded to hard-coded
# 256-residue intervals. ``auto`` requests the exact campaign maximum; use
# ``default`` to retain the upstream 256,512,... list.
INTELLIFOLD_BUCKETS="${NANOHUNTER_INTELLIFOLD_BUCKETS:-auto}"

TEMPLATE_YAML="${PROTEINHUNTER_TEMPLATE_DEFAULT:-${NANOHUNTER_TEMPLATE_DEFAULT:-${DEFAULT_TEMPLATE_YAML}}}"
NANOHUNTER_CONFIG_JSON="${PROTEINHUNTER_CONFIG_JSON:-${NANOHUNTER_CONFIG_JSON:-}}"
BASE_RUN_ROOT="${REPO_ROOT}/output"

RUN_NAME="test_run"
PREDICTOR="${NANOHUNTER_PREDICTOR_DEFAULT:-boltz}"
POST_PREDICTOR="${NANOHUNTER_POST_PREDICTOR_DEFAULT:-${DEFAULT_POST_PREDICTOR}}"
POST_MODE="all"
POST_IPTM_THRESHOLD="0.70"
POST_IPTM_THRESHOLD_SET=0
POST_INCLUDE_CYCLE00=0

N_RUNS=3
N_CYCLES=5
PREDICTOR_SEED="${NANOHUNTER_PREDICTOR_SEED_DEFAULT:-42}"
PREDICTOR_SAMPLES="${NANOHUNTER_PREDICTOR_SAMPLES_DEFAULT:-auto}"
CPU_ONLY=0

NO_PARALLEL=0
MAX_PARALLEL_USER="auto"
CALIBRATE_ONLY=0
SKIP_PREDICTOR_CALIBRATION=0
CHECK_CONFIG_ONLY=0
# Reuse completed per-cycle predictions in an existing --run-name output tree
# instead of recomputing them. Safe to pass on a fresh run (it is a no-op).
RESUME=0
DESIGN_SCHEDULER="${NANOHUNTER_DESIGN_SCHEDULER_DEFAULT:-run}"
WAVE_BATCH_SIZE="${NANOHUNTER_WAVE_BATCH_SIZE_DEFAULT:-all}"
WAVE_BATCH_SIZE_USER_SET=0
MPNN_WAVE_MAX_PARALLEL="${NANOHUNTER_MPNN_WAVE_MAX_PARALLEL_DEFAULT:-2}"
THROUGHPUT_PROFILE="${NANOHUNTER_THROUGHPUT_PROFILE:-auto}"
MPS_AWARE=1
MPS_MAX_PARALLEL="${NANOHUNTER_MPS_MAX_PARALLEL_DEFAULT:-auto}"
MPS_MEM_FRACTION="${NANOHUNTER_MPS_MEM_FRACTION_DEFAULT:-0.65}"
MPS_MEMORY_RESERVE_GB="${NANOHUNTER_MPS_MEMORY_RESERVE_GB_DEFAULT:-8}"
MPS_CPU_CAP="${NANOHUNTER_MPS_CPU_CAP_DEFAULT:-12}"
MEM_BUDGET_GB="auto"
MEM_SAFETY="${NANOHUNTER_MEM_SAFETY_DEFAULT:-0.80}"
# Basis for the auto memory budget: "available" (free+inactive+speculative, the
# safe default that leaves other apps untouched) or "total" (a fraction of total
# physical RAM, capped by the safe budget — uses more RAM for design and lets
# other apps swap/compress).
MEM_BASIS="${NANOHUNTER_MEM_BASIS_DEFAULT:-available}"

BINDER_MIN_LEN=65
BINDER_MAX_LEN=150
BINDER_PERCENT_X=50
BINDER_RANDOM_SEED="${NANOHUNTER_BINDER_RANDOM_SEED:-}"
SCAFFOLD_FROM_TEMPLATE="${NANOHUNTER_SCAFFOLD_FROM_TEMPLATE_DEFAULT:-${DEFAULT_SCAFFOLD_FROM_TEMPLATE}}"
INITIAL_STRUCTURE=""
INITIAL_CONFIDENCE_JSON=""

MOTIF_SCAFFOLDING=0
MOTIF_POSITIONS=""
MOTIF_FIXED_POSITIONS=""
MOTIF_SOURCE_SEQ=""
MOTIF_GAP_BETWEEN=8
MOTIF_HELPER="${REPO_ROOT}/motif_scaffolding_helper.py"

PARTIAL_REDESIGN=0
PARTIAL_REDESIGN_RANGES=""
PARTIAL_BINDER_SEQ=""
PARTIAL_REDESIGNED_RESIDUES=""
PARTIAL_BINDER_LEN=0

HELIX_KILL=0
NEGATIVE_HELIX_CONSTANT="0.5"
LOOP_KILL="0"
UNK_PATCH_MODE="auto"

LIGAND_TEMP_DEFAULT="0.10"
LIGAND_TEMP_CYCLE01="0.30"
LIGAND_BIAS_AA_DEFAULT=""
LIGAND_BIAS_AA_CYCLE01=""
LIGANDMPNN_SEED=111
SEQUENCE_DESIGNER="${SEQUENCE_DESIGNER_DEFAULT:-${DEFAULT_SEQUENCE_DESIGNER}}"
SEQUENCE_DESIGNER_LABEL="auto"
ANTIFOLD_REGIONS="${NANOHUNTER_CDRS_DEFAULT:-CDR3}"
ANTIFOLD_NANOBODY_CHAIN="${NANOHUNTER_CHAIN_DEFAULT:-A}"
ANTIFOLD_ANTIGEN_CHAIN="${NANOHUNTER_ANTIGEN_CHAIN_DEFAULT:-auto}"
ANTIFOLD_NUM_SEQ_PER_TARGET=1
ANTIFOLD_BATCH_SIZE=1
ANTIFOLD_NUM_THREADS=0
ANTIFOLD_SEED=42
ANTIFOLD_LIMIT_VARIATION=0
NANOBODY_SEED_MODE="${NANOHUNTER_SEED_MODE_DEFAULT:-${DEFAULT_NANOBODY_SEED_MODE}}"
NANOBODY_SEED_CDRS="${NANOHUNTER_SEED_CDRS_DEFAULT:-auto}"
NANOBODY_SEED_CDR_RANGES="auto"
NANOBODY_SEED_PERCENT_X="${NANOHUNTER_SEED_PERCENT_X_DEFAULT:-${DEFAULT_NANOBODY_SEED_PERCENT_X}}"
NANOBODY_SEED_MAX_ATTEMPTS=500
NANOBODY_ALLOW_CDR_CYS=0
NANOBODY_CHARGE_MIN="-4"
NANOBODY_CHARGE_MAX="4"
NANOBODY_HYDRO_MAX="0.45"
NANOBODY_USE_SOFT_FILTERS=1
TARGET_MSA_MODE="${NANOHUNTER_TARGET_MSA_MODE_DEFAULT:-auto}"
TARGET_MSA_GENERATOR="${NANOHUNTER_TARGET_MSA_GENERATOR_DEFAULT:-auto}"
TARGET_MSA_PATH_OVERRIDE="${NANOHUNTER_TARGET_MSA_PATH_DEFAULT:-}"
TARGET_MSA_REQUIRED="${NANOHUNTER_TARGET_MSA_REQUIRED_DEFAULT:-0}"
TARGET_MSA_SHARED_CACHE_DIR="${NANOHUNTER_TARGET_MSA_CACHE_DIR_DEFAULT:-${REPO_ROOT}/msa_cache}"
TARGET_MSA_SEARCH_ROOTS="${NANOHUNTER_TARGET_MSA_SEARCH_ROOTS:-${TARGET_MSA_SHARED_CACHE_DIR}:${REPO_ROOT}/examples_data:${REPO_ROOT}/projects:${REPO_ROOT}/output}"
NANOBODY_SCAFFOLD_MSA_MODE="${NANOHUNTER_SCAFFOLD_MSA_MODE_DEFAULT:-${DEFAULT_NANOBODY_SCAFFOLD_MSA_MODE}}"
NANOBODY_SCAFFOLD_MSA_SOURCE="${NANOHUNTER_SCAFFOLD_MSA_SOURCE_DEFAULT:-}"
NANOBODY_SCAFFOLD_MSA_CACHE_DIR="${NANOHUNTER_SCAFFOLD_MSA_CACHE_DIR_DEFAULT:-${REPO_ROOT}/examples/nanobody_scaffolds/msas}"
NANOBODY_SCAFFOLD_MSA_LEGACY_CACHE_DIR="${REPO_ROOT}/output/nanobody_scaffold_msas"
NANOBODY_SCAFFOLD_MSA_MASK_CDRS="${NANOHUNTER_SCAFFOLD_MSA_MASK_CDRS_DEFAULT:-auto}"
NANOBODY_SCAFFOLD_MSA_MAX_SEQS="${NANOHUNTER_SCAFFOLD_MSA_MAX_SEQS_DEFAULT:-256}"
NANOBODY_SCAFFOLD_MSA_MASK_CHAR="${NANOHUNTER_SCAFFOLD_MSA_MASK_CHAR_DEFAULT:--}"
NANOBODY_SCAFFOLD_MSA_BASE_A3M=""
TARGET_EPITOPE_RESIDUES="${NANOHUNTER_TARGET_EPITOPE_RESIDUES_DEFAULT:-}"
BOLTZ_CONTACT_DISTANCE="${NANOHUNTER_BOLTZ_CONTACT_DISTANCE_DEFAULT:-6}"
BOLTZ_CONTACT_FORCE=1
BOLTZ_CONTACT_MODE="${NANOHUNTER_BOLTZ_CONTACT_MODE_DEFAULT:-auto}"
NANOBODY_SEED_PERCENT_X_SET=0
TARGET_EPITOPE_RESIDUES_SET=0
BOLTZ_CONTACT_DISTANCE_SET=0
BOLTZ_CONTACT_FORCE_SET=0
BOLTZ_CONTACT_MODE_SET=0
TARGET_MSA_MODE_SET=0
TARGET_MSA_GENERATOR_SET=0
TARGET_MSA_PATH_OVERRIDE_SET=0
TARGET_MSA_REQUIRED_SET=0
NANOBODY_SCAFFOLD_MSA_MODE_SET=0
NANOBODY_SCAFFOLD_MSA_SOURCE_SET=0
NANOBODY_SCAFFOLD_MSA_CACHE_DIR_SET=0
NANOBODY_SCAFFOLD_MSA_MASK_CDRS_SET=0
NANOBODY_SCAFFOLD_MSA_MAX_SEQS_SET=0
INTELLIFOLD_MODEL="${NANOHUNTER_INTELLIFOLD_MODEL_DEFAULT:-v2-flash}"
BOLTZ_USE_POTENTIALS_MODE="auto"
BOLTZ_USE_POTENTIALS_DEFAULT=0

IPTM_THRESHOLD="0.80"
IPTM_THRESHOLD_SET=0

PEAK_RSS_MB=0
PEAK_FOOTPRINT_MB=0
PEAK_SYS_DELTA_MB=0
PEAK_EFFECTIVE_MB=0
MONITOR_PEAK_RSS_MB=0
MONITOR_PEAK_FOOTPRINT_MB=0
MONITOR_PEAK_SYS_DELTA_MB=0
MONITOR_PEAK_EFFECTIVE_MB=0

BOLTZ_EXTRA_FLAGS_DEFAULT=(
  "--accelerator" "gpu"
  "--devices" "1"
  "--num_workers" "0"
  "--use_msa_server"
  "--msa_server_url" "https://api.colabfold.com"
  "--msa_pairing_strategy" "greedy"
  "--override"
)

INTELLIFOLD_EXTRA_FLAGS_DEFAULT=(
  "--cache" "${INTELLIFOLD_CACHE_DIR}"
  "--precision" "no"
  "--num_workers" "0"
  "--seed" "42"
  "--num_diffusion_samples" "1"
  "--override"
  "--use_msa_server"
  "--msa_pairing_strategy" "greedy"
)

OPENFOLD_EXTRA_FLAGS_DEFAULT=(
  "--num_diffusion_samples" "1"
  "--num_model_seeds" "1"
)

LIGANDMPNN_EXTRA_FLAGS_DEFAULT=(
  "--chains_to_design" "A"
)

LIGANDMPNN_MODEL_FLAGS=()
LIGANDMPNN_MODEL_LABEL="auto"

BOLTZ_EXTRA_CLI_STRING=""
INTELLIFOLD_EXTRA_CLI_STRING=""
OPENFOLD_EXTRA_CLI_STRING=""
LIGAND_EXTRA_CLI_STRING=""
ANTIFOLD_EXTRA_CLI_STRING=""

usage() {
  cat <<EOF2
Usage: ${RUNNER_DISPLAY_NAME} [options]

Core:
  --workflow MODE                  protein | nanobody (default: ${WORKFLOW})
                                   protein: generic binders, motifs, partial redesign, ligands
                                   nanobody: fixed VHH scaffold with exact CDR-only redesign
  --predictor TOOL                 boltz | protenix-constraint-v0.5 | protenix-v2 | protenix-mini | intellifold | openfold-3-mlx
  --sequence-designer TOOL         auto | proteinmpnn | solublempnn | ligandmpnn | lasermpnn | abmpnn | antifold
                                   (lasermpnn: small-molecule minibinders only; --workflow protein + ligand; CPU-only)
                                   default: ${SEQUENCE_DESIGNER}
  --post-predictor LIST            none | TOOL[,TOOL] (default: ${POST_PREDICTOR})
  --post-mode MODE                 none | all | iptm | final | final-iptm (default: ${POST_MODE})
  --post-iptm-threshold T          default: ${POST_IPTM_THRESHOLD}
  --post-include-cycle00           include cycle_00 in post stage
  --run-name NAME                  default: ${RUN_NAME}
  --num-runs N                     default: ${N_RUNS}
  --num-opt-cycles N               optimization cycles after cycle_00 (default: ${N_CYCLES})
  --num-cycles N                   alias of --num-opt-cycles
  --predictor-seed N               structure-predictor seed (default: ${PREDICTOR_SEED})
  --predictor-samples N|auto       diffusion samples per input; auto preserves engine defaults
  --model NAME                     IntelliFold model when used (default: ${INTELLIFOLD_MODEL})
  --template-yaml PATH             default: ${TEMPLATE_YAML}
  --config-json PATH               optional workflow settings JSON; CLI flags override it
  --nanohunter-config-json PATH    backward-compatible alias
  --input-json PATH                alias of --nanohunter-config-json
  --out-root PATH                  default: ${BASE_RUN_ROOT}

Binder:
  --binder-min-len N               default: ${BINDER_MIN_LEN}
  --binder-max-len N               default: ${BINDER_MAX_LEN}
  --binder-percent-x P             default: ${BINDER_PERCENT_X}
                                   (OpenFold-3 uses A/N/G/H/F/S/Y spikes at this rate;
                                   Boltz and IntelliFold use X)
  --binder-random-seed N           deterministic cycle_00 base seed; run_index is added
  --scaffold-from-template         seed cycle_00 from template chain A instead of random length
  --random-binder                  seed cycle_00 with the random binder mode
  --initial-structure PATH         import an archived cycle_00 CIF/PDB instead of re-predicting it
  --initial-confidence-json PATH   optional confidence JSON paired with --initial-structure
  --motif-scaffolding              enable motif scaffolding mode (Boltz design only)
  --motif-positions STR            motifs as JSON or ranges like "31-45,63-106" (1-based ranges)
  --motif-source-seq STR           source sequence used to extract motif residues
  --motif-fixed-positions STR      optional 1-based original positions to fix (comma-separated)
  --gap-between-motifs N           minimum internal gap between motifs (default: ${MOTIF_GAP_BETWEEN})
  --partial-redesign               keep binder fixed except selected redesign ranges
  --partial-redesign-ranges STR    comma-separated 1-based ranges, e.g. "25-50,70-75"

Design controls:
  --helix-kill
  --negative-helix-constant X      0..1 helix-kill strength (default: ${NEGATIVE_HELIX_CONSTANT})
  --loopkill X                     0..1 loop-kill strength (default: ${LOOP_KILL})
  --unk-patch-mode MODE            auto | ala | ala_gly | ala_gly_ser
  --ligand-temp-cycle1 T           default: ${LIGAND_TEMP_CYCLE01}
  --ligand-temp-cycle01 T          alias of --ligand-temp-cycle1
  --ligand-temp-other T            default: ${LIGAND_TEMP_DEFAULT}
  --ligand-temp T                  alias of --ligand-temp-other
  --mpnn-bias-aa-cycle1 STR        passed to LigandMPNN --bias_AA for cycle_00->01 redesign
  --mpnn-bias-aa-other STR         passed to LigandMPNN --bias_AA for later redesign cycles
  --nanobody-cdrs STR              CDR regions to redesign, e.g. "CDR3" or "CDR1 CDR2 CDR3".
                                   Restricts AntiFold sampling AND the MPNN designers
                                   (proteinmpnn/solublempnn/ligandmpnn/abmpnn) to these CDRs.
                                   default: ${ANTIFOLD_REGIONS}
  --nanobody-seed-mode MODE        native | cdr-random (default: ${NANOBODY_SEED_MODE})
  --nanobody-native-seed           alias for --nanobody-seed-mode native
  --nanobody-randomize-seed        alias for --nanobody-seed-mode cdr-random
  --nanobody-seed-cdrs STR         CDRs randomized in cycle_00; auto follows --nanobody-cdrs
                                   default: ${NANOBODY_SEED_CDRS}
  --nanobody-cdr-ranges STR        explicit CDR ranges for detection/seed/contacts,
                                   e.g. CDR1:26-33,CDR2:51-57,CDR3:97-110 (else auto-detected)
  --nanobody-seed-cdr-ranges STR   alias of --nanobody-cdr-ranges
  --nanobody-seed-percent-x P      percent of randomized seed CDR residues emitted as X (default: ${NANOBODY_SEED_PERCENT_X})
  --nanobody-cdr3-percent-x P      alias of --nanobody-seed-percent-x
  --nanobody-seed-max-attempts N   constrained cycle_00 sampling attempts (default: ${NANOBODY_SEED_MAX_ATTEMPTS})
  --nanobody-allow-cdr-cys         allow cysteine in randomized CDR seed residues
  --nanobody-charge-min X          soft lower net-charge bound for randomized CDRs (default: ${NANOBODY_CHARGE_MIN})
  --nanobody-charge-max X          soft upper net-charge bound for randomized CDRs (default: ${NANOBODY_CHARGE_MAX})
  --nanobody-hydrophobic-max X     soft hydrophobic-fraction cap for randomized CDRs (default: ${NANOBODY_HYDRO_MAX})
  --nanobody-hard-filters-only     keep hard developability filters but ignore charge/hydrophobic soft filters
  --target-msa-mode MODE           auto | off (default: ${TARGET_MSA_MODE})
                                   auto generates one target MSA during calibration and reuses it
  --target-msa-generator TOOL      auto | boltz | protenix | intellifold | openfold (default: ${TARGET_MSA_GENERATOR})
                                   auto follows the selected structural predictor's native MSA path
  --target-msa-path PATH            explicit reusable target A3M or NPZ; overrides template MSA
  --require-target-msa              fail if native target MSA generation does not produce a real MSA
  --nanobody-scaffold-msa MODE     off | masked-cdr | single (default: ${NANOBODY_SCAFFOLD_MSA_MODE})
  --nanobody-scaffold-msa-source PATH
                                   optional precomputed scaffold A3M to mask/reuse
  --nanobody-scaffold-msa-cache-dir PATH
                                   directory with <scaffold_id>/full_msa.a3m caches
  --nanobody-scaffold-msa-mask-cdrs STR
                                   CDRs masked in scaffold MSA homolog rows; auto follows designed CDRs
  --nanobody-scaffold-msa-max-seqs N
                                   max scaffold MSA rows to write per prediction (default: ${NANOBODY_SCAFFOLD_MSA_MAX_SEQS})
  --nanobody-chain ID              nanobody chain in predicted structures (default: ${ANTIFOLD_NANOBODY_CHAIN})
  --nanobody-antigen-chain ID      antigen chain for AntiFold, or auto|none (default: ${ANTIFOLD_ANTIGEN_CHAIN})
  --antifold-temp-cycle1 T         alias of --ligand-temp-cycle1 for AntiFold
  --antifold-temp-other T          alias of --ligand-temp-other for AntiFold
  --antifold-temp T                alias of --antifold-temp-other
  --antifold-limit-variation       reduce exact-position AntiFold sample variation
  --antifold-seed N                base AntiFold seed; run/cycle offsets are added
  --mpnn-seed N                    base ProteinMPNN-family seed; run/cycle offsets are added
  --lasermpnn-seed N               base LASErMPNN seed; run/cycle offsets are added
  --target-epitope-residues STR    target residues for Boltz or Protenix Constraint, e.g. "B6,B8,B9"
  --boltz-contact-distance X       max CDR3/epitope contact distance in Angstrom (default: ${BOLTZ_CONTACT_DISTANCE})
  --boltz-epitope-distance X       alias of --boltz-contact-distance
  --boltz-contact-mode MODE        auto | none | pocket | cdr3 | pocket+cdr3 (default: ${BOLTZ_CONTACT_MODE})
  --boltz-no-contact-force         set Boltz contact/pocket force to false
  --boltz-use-potentials           force Boltz design to use potentials
  --boltz-no-potentials            force Boltz design to not use potentials

Filtering:
  --iptm-threshold T               default: ${IPTM_THRESHOLD}

Parallelism:
  --no-parallel
  --max-parallel N|auto            default: ${MAX_PARALLEL_USER}
  --calibrate-only                 calibrate memory and exit before design runs
  --resume                         reuse completed cycle predictions in an existing --run-name tree
  --check-config                   validate routing, inputs, envs, and checkpoints; do not predict
  --skip-predictor-calibration     requires an explicit --max-parallel value
  --design-scheduler MODE          run | cycle-wave | resident (default: ${DESIGN_SCHEDULER})
  --wave-batch-size N|all          predictor inputs per model load in cycle-wave mode
  --wave-mpnn-max-parallel N       concurrent MPNN redesigns between waves (default: ${MPNN_WAVE_MAX_PARALLEL})
  --throughput-profile PATH|auto|off
                                   use a per-device calibrated process/batch recommendation
  --mps-aware                      default on
  --no-mps-aware
  --mps-max-parallel N|auto        compatibility knob
  --mps-mem-fraction F             compatibility knob
  --mps-memory-reserve-gb X         memory kept free before auto parallelism (default: ${MPS_MEMORY_RESERVE_GB})
  --mps-cpu-cap N                  compatibility knob
  --mem-budget-gb X|auto           compatibility knob
  --mem-safety S                   compatibility knob

Hardware:
  --cpu-only                       force CPU where supported

Extra flags passthrough:
  --intellifold-buckets MODE       auto | length-aware | default | comma-separated token sizes
  --boltz-extra "ARGS"
  --intellifold-extra "ARGS"
  --openfold-extra "ARGS"
  --ligand-extra "ARGS"
  --antifold-extra "ARGS"

  -h, --help
EOF2
}

norm_predictor() {
  local raw
  raw="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
  case "${raw}" in
    boltz) echo "boltz" ;;
    intellifold) echo "intellifold" ;;
    protenix-v2|protenixv2|protenix_v2) echo "protenix-v2" ;;
    protenix-mini|protenixmini|protenix_mini) echo "protenix-mini" ;;
    protenix-constraint-v0.5|protenix-constraint|protenix_constraint_v0_5|protenix_constraint) echo "protenix-constraint-v0.5" ;;
    openfold-3-mlx|openfold3|openfold|of3) echo "openfold-3-mlx" ;;
    alphafold3|alphafold-3|af3|intellifold-jax|intellifold_jax)
      echo "Retired predictor: $1 (Metal quality-control failure)." >&2
      return 2 ;;
    none|"") echo "none" ;;
    *) return 1 ;;
  esac
}

norm_sequence_designer() {
  local raw
  raw="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | tr '_' '-')"
  case "${raw}" in
    auto|"") echo "auto" ;;
    proteinmpnn|protein-mpnn) echo "proteinmpnn" ;;
    solublempnn|soluble-mpnn) echo "solublempnn" ;;
    ligandmpnn|ligand-mpnn|mpnn) echo "ligandmpnn" ;;
    lasermpnn|laser-mpnn|laser) echo "lasermpnn" ;;
    abmpnn|ab-mpnn) echo "abmpnn" ;;
    antifold|anti-fold) echo "antifold" ;;
    *) return 1 ;;
  esac
}

sequence_designer_uses_ligandmpnn() {
  case "${SEQUENCE_DESIGNER}" in
    auto|proteinmpnn|solublempnn|ligandmpnn|abmpnn) return 0 ;;
    *) return 1 ;;
  esac
}

# Extract the first ligand SMILES from a Boltz-style template YAML. Returns an
# empty string if the only ligand is specified by CCD code (no SMILES), which
# LASErMPNN's SMILES-based protonation cannot use.
extract_ligand_smiles_from_yaml() {
  python3 - "$1" <<'PY'
import sys, re
path = sys.argv[1]
in_ligand = False
indent = None
smiles = ""
for raw in open(path):
    line = raw.rstrip("\n")
    stripped = line.strip()
    if re.match(r"-\s*ligand\s*:", stripped):
        in_ligand = True
        indent = len(line) - len(line.lstrip())
        continue
    if in_ligand:
        cur_indent = len(line) - len(line.lstrip())
        # A new top-level list item at or below the ligand indent ends the block.
        if stripped.startswith("- ") and cur_indent <= indent:
            in_ligand = False
        else:
            m = re.match(r"smiles\s*:\s*(.+)$", stripped)
            if m:
                smiles = m.group(1).strip().strip("'\"")
                break
print(smiles)
PY
}

normalize_antifold_regions() {
  local raw normalized tok lower
  raw="$(printf '%s' "$1" | tr ',' ' ')"
  normalized=()
  for tok in ${raw}; do
    lower="$(printf '%s' "${tok}" | tr '[:upper:]' '[:lower:]')"
    case "${lower}" in
      cdr1|cdrh1) normalized+=("CDR1") ;;
      cdr2|cdrh2) normalized+=("CDR2") ;;
      cdr3|cdrh3) normalized+=("CDR3") ;;
      cdrh) normalized+=("CDRH") ;;
      all) normalized+=("all") ;;
      allh) normalized+=("allH") ;;
      *) return 1 ;;
    esac
  done
  [[ "${#normalized[@]}" -gt 0 ]] || return 1
  printf '%s\n' "${normalized[*]}"
}

normalize_nanobody_seed_mode() {
  local raw
  raw="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | tr '_' '-')"
  case "${raw}" in
    native|copy|exact|template) echo "native" ;;
    cdr-random|random|random-cdr|randomize|randomized) echo "cdr-random" ;;
    *) return 1 ;;
  esac
}

load_nanohunter_input_settings() {
  local input_path="$1"
  python3 - "$input_path" <<'PY'
import json
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.exists():
    raise SystemExit(0)

text = path.read_text()
settings = {}


def normalize_value(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (list, tuple)):
        return ",".join(str(x) for x in value)
    return str(value).strip().strip("'\"")


def emit(mapping):
    aliases = {
        "target_epitope_residues": "target_epitope_residues",
        "epitope_residues": "target_epitope_residues",
        "boltz_contact_distance": "boltz_contact_distance",
        "boltz_epitope_distance": "boltz_contact_distance",
        "boltz_contact_mode": "boltz_contact_mode",
        "boltz_contact_force": "boltz_contact_force",
        "nanobody_seed_percent_x": "nanobody_seed_percent_x",
        "nanobody_cdr3_percent_x": "nanobody_seed_percent_x",
        "target_msa_mode": "target_msa_mode",
        "target_msa_generator": "target_msa_generator",
        "target_msa_path": "target_msa_path",
        "target_msa_required": "target_msa_required",
        "nanobody_scaffold_msa": "nanobody_scaffold_msa",
        "nanobody_scaffold_msa_mode": "nanobody_scaffold_msa",
        "nanobody_scaffold_msa_source": "nanobody_scaffold_msa_source",
        "nanobody_scaffold_msa_path": "nanobody_scaffold_msa_source",
        "nanobody_scaffold_msa_cache_dir": "nanobody_scaffold_msa_cache_dir",
        "nanobody_scaffold_msa_mask_cdrs": "nanobody_scaffold_msa_mask_cdrs",
        "nanobody_scaffold_msa_max_seqs": "nanobody_scaffold_msa_max_seqs",
    }
    for key, value in mapping.items():
        norm_key = aliases.get(str(key).strip())
        if not norm_key:
            continue
        norm_value = normalize_value(value)
        if norm_value:
            settings[norm_key] = norm_value


try:
    data = json.loads(text)
except Exception:
    data = None
if isinstance(data, dict):
    for section_name in ("nanohunter", "nano_hunter", "NanoHunter"):
        section = data.get(section_name)
        if isinstance(section, dict):
            emit(section)
    emit(data)

if not settings:
    lines = text.splitlines()
    in_block = False
    pending_list_key = None
    block = {}
    for raw in lines:
        if re.match(r"^\S", raw):
            key = raw.split(":", 1)[0].strip() if ":" in raw else ""
            if key in {"nanohunter", "nano_hunter", "NanoHunter"}:
                in_block = True
                pending_list_key = None
                continue
            if in_block:
                break
        if not in_block:
            continue
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if pending_list_key and stripped.startswith("- "):
            block.setdefault(pending_list_key, [])
            block[pending_list_key].append(stripped[2:].strip().strip("'\""))
            continue
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()
        pending_list_key = None
        if value == "":
            pending_list_key = key
            block[key] = []
            continue
        if value.startswith("[") and value.endswith("]"):
            value = [v.strip().strip("'\"") for v in value[1:-1].split(",") if v.strip()]
        block[key] = value
    emit(block)

for key in sorted(settings):
    print(f"{key}\t{settings[key]}")
PY
}

safe_predictor_name() {
  local p
  p="$(norm_predictor "$1")" || return 1
  case "$p" in
    boltz) echo "boltz" ;;
    intellifold) echo "intellifold" ;;
    protenix-v2) echo "protenix_v2" ;;
    protenix-mini) echo "protenix_mini" ;;
    protenix-constraint-v0.5) echo "protenix_constraint_v0_5" ;;
    openfold-3-mlx) echo "openfold3" ;;
    none) echo "none" ;;
    *) return 1 ;;
  esac
}

post_predictors_count() {
  if declare -p POST_PREDICTORS >/dev/null 2>&1; then
    echo "${#POST_PREDICTORS[@]}"
  else
    echo "0"
  fi
}

die() { echo "ERROR: $*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --workflow|--design-mode) WORKFLOW="$2"; shift 2 ;;
    --workflow=*|--design-mode=*) WORKFLOW="${1#*=}"; shift 1 ;;
    --predictor) PREDICTOR="$2"; shift 2 ;;
    --sequence-designer|--seq-designer) SEQUENCE_DESIGNER="$2"; shift 2 ;;
    --post-predictor) POST_PREDICTOR="$2"; shift 2 ;;
    --post-mode) POST_MODE="$2"; shift 2 ;;
    --post-iptm-threshold) POST_IPTM_THRESHOLD="$2"; POST_IPTM_THRESHOLD_SET=1; shift 2 ;;
    --post-include-cycle00) POST_INCLUDE_CYCLE00=1; shift 1 ;;

    --run-name) RUN_NAME="$2"; shift 2 ;;
    --num-runs) N_RUNS="$2"; shift 2 ;;
    --num-opt-cycles|--num-cycles) N_CYCLES="$2"; shift 2 ;;
    --predictor-seed) PREDICTOR_SEED="$2"; shift 2 ;;
    --predictor-samples) PREDICTOR_SAMPLES="$2"; shift 2 ;;
    --model) INTELLIFOLD_MODEL="$2"; shift 2 ;;
    --template-yaml) TEMPLATE_YAML="$2"; shift 2 ;;
    --config-json|--nanohunter-config-json|--input-json) NANOHUNTER_CONFIG_JSON="$2"; shift 2 ;;
    --out-root) BASE_RUN_ROOT="$2"; shift 2 ;;

    --binder-min-len) BINDER_MIN_LEN="$2"; shift 2 ;;
    --binder-max-len) BINDER_MAX_LEN="$2"; shift 2 ;;
    --binder-percent-x) BINDER_PERCENT_X="$2"; shift 2 ;;
    --binder-random-seed) BINDER_RANDOM_SEED="$2"; shift 2 ;;
    --scaffold-from-template) SCAFFOLD_FROM_TEMPLATE=1; shift 1 ;;
    --random-binder) SCAFFOLD_FROM_TEMPLATE=0; shift 1 ;;
    --initial-structure) INITIAL_STRUCTURE="$2"; shift 2 ;;
    --initial-confidence-json) INITIAL_CONFIDENCE_JSON="$2"; shift 2 ;;
    --motif-scaffolding) MOTIF_SCAFFOLDING=1; shift 1 ;;
    --motif-positions) MOTIF_POSITIONS="$2"; shift 2 ;;
    --motif-source-seq) MOTIF_SOURCE_SEQ="$2"; shift 2 ;;
    --motif-fixed-positions) MOTIF_FIXED_POSITIONS="$2"; shift 2 ;;
    --gap-between-motifs) MOTIF_GAP_BETWEEN="$2"; shift 2 ;;
    --partial-redesign) PARTIAL_REDESIGN=1; shift 1 ;;
    --partial-redesign-ranges) PARTIAL_REDESIGN_RANGES="$2"; shift 2 ;;

    --helix-kill) HELIX_KILL=1; shift 1 ;;
    --negative-helix-constant) NEGATIVE_HELIX_CONSTANT="$2"; shift 2 ;;
    --loopkill) LOOP_KILL="$2"; shift 2 ;;
    --unk-patch-mode) UNK_PATCH_MODE="$2"; shift 2 ;;

    --ligand-temp-cycle1|--ligand-temp-cycle01) LIGAND_TEMP_CYCLE01="$2"; shift 2 ;;
    --ligand-temp-other|--ligand-temp) LIGAND_TEMP_DEFAULT="$2"; shift 2 ;;
    --mpnn-bias-aa-cycle1) LIGAND_BIAS_AA_CYCLE01="$2"; shift 2 ;;
    --mpnn-bias-aa-other) LIGAND_BIAS_AA_DEFAULT="$2"; shift 2 ;;
    --nanobody-cdrs|--cdrs|--antifold-regions) ANTIFOLD_REGIONS="$2"; shift 2 ;;
    --nanobody-seed-mode) NANOBODY_SEED_MODE="$2"; shift 2 ;;
    --nanobody-native-seed) NANOBODY_SEED_MODE="native"; shift 1 ;;
    --nanobody-randomize-seed) NANOBODY_SEED_MODE="cdr-random"; shift 1 ;;
    --nanobody-seed-cdrs) NANOBODY_SEED_CDRS="$2"; shift 2 ;;
    --nanobody-cdr-ranges|--nanobody-seed-cdr-ranges) NANOBODY_SEED_CDR_RANGES="$2"; shift 2 ;;
    --nanobody-seed-percent-x|--nanobody-cdr3-percent-x) NANOBODY_SEED_PERCENT_X="$2"; NANOBODY_SEED_PERCENT_X_SET=1; shift 2 ;;
    --nanobody-seed-max-attempts) NANOBODY_SEED_MAX_ATTEMPTS="$2"; shift 2 ;;
    --nanobody-allow-cdr-cys) NANOBODY_ALLOW_CDR_CYS=1; shift 1 ;;
    --nanobody-charge-min) NANOBODY_CHARGE_MIN="$2"; shift 2 ;;
    --nanobody-charge-max) NANOBODY_CHARGE_MAX="$2"; shift 2 ;;
    --nanobody-hydrophobic-max) NANOBODY_HYDRO_MAX="$2"; shift 2 ;;
    --nanobody-hard-filters-only|--no-nanobody-soft-filter|--no-nanobody-soft-filters) NANOBODY_USE_SOFT_FILTERS=0; shift 1 ;;
    --target-msa-mode) TARGET_MSA_MODE="$2"; TARGET_MSA_MODE_SET=1; shift 2 ;;
    --target-msa-generator) TARGET_MSA_GENERATOR="$2"; TARGET_MSA_GENERATOR_SET=1; shift 2 ;;
    --target-msa-path) TARGET_MSA_PATH_OVERRIDE="$2"; TARGET_MSA_PATH_OVERRIDE_SET=1; shift 2 ;;
    --require-target-msa) TARGET_MSA_REQUIRED=1; TARGET_MSA_REQUIRED_SET=1; shift 1 ;;
    --nanobody-scaffold-msa|--nanobody-scaffold-msa-mode) NANOBODY_SCAFFOLD_MSA_MODE="$2"; NANOBODY_SCAFFOLD_MSA_MODE_SET=1; shift 2 ;;
    --nanobody-no-scaffold-msa) NANOBODY_SCAFFOLD_MSA_MODE="off"; NANOBODY_SCAFFOLD_MSA_MODE_SET=1; shift 1 ;;
    --nanobody-scaffold-msa-source|--nanobody-scaffold-msa-path) NANOBODY_SCAFFOLD_MSA_SOURCE="$2"; NANOBODY_SCAFFOLD_MSA_SOURCE_SET=1; shift 2 ;;
    --nanobody-scaffold-msa-cache-dir) NANOBODY_SCAFFOLD_MSA_CACHE_DIR="$2"; NANOBODY_SCAFFOLD_MSA_CACHE_DIR_SET=1; shift 2 ;;
    --nanobody-scaffold-msa-mask-cdrs) NANOBODY_SCAFFOLD_MSA_MASK_CDRS="$2"; NANOBODY_SCAFFOLD_MSA_MASK_CDRS_SET=1; shift 2 ;;
    --nanobody-scaffold-msa-max-seqs) NANOBODY_SCAFFOLD_MSA_MAX_SEQS="$2"; NANOBODY_SCAFFOLD_MSA_MAX_SEQS_SET=1; shift 2 ;;
    --nanobody-chain) ANTIFOLD_NANOBODY_CHAIN="$2"; shift 2 ;;
    --nanobody-antigen-chain) ANTIFOLD_ANTIGEN_CHAIN="$2"; shift 2 ;;
    --antifold-temp-cycle1|--antifold-temp-cycle01) LIGAND_TEMP_CYCLE01="$2"; shift 2 ;;
    --antifold-temp-other|--antifold-temp) LIGAND_TEMP_DEFAULT="$2"; shift 2 ;;
    --antifold-limit-variation) ANTIFOLD_LIMIT_VARIATION=1; shift 1 ;;
    --antifold-seed) ANTIFOLD_SEED="$2"; shift 2 ;;
    --mpnn-seed|--ligandmpnn-seed) LIGANDMPNN_SEED="$2"; shift 2 ;;
    --lasermpnn-seed) LASERMPNN_SEED="$2"; shift 2 ;;
    --antifold-num-seq-per-target) ANTIFOLD_NUM_SEQ_PER_TARGET="$2"; shift 2 ;;
    --antifold-batch-size) ANTIFOLD_BATCH_SIZE="$2"; shift 2 ;;
    --antifold-num-threads) ANTIFOLD_NUM_THREADS="$2"; shift 2 ;;
    --target-epitope-residues|--epitope-residues) TARGET_EPITOPE_RESIDUES="$2"; TARGET_EPITOPE_RESIDUES_SET=1; shift 2 ;;
    --boltz-contact-distance|--boltz-epitope-distance) BOLTZ_CONTACT_DISTANCE="$2"; BOLTZ_CONTACT_DISTANCE_SET=1; shift 2 ;;
    --boltz-contact-mode) BOLTZ_CONTACT_MODE="$2"; BOLTZ_CONTACT_MODE_SET=1; shift 2 ;;
    --boltz-no-contact-force) BOLTZ_CONTACT_FORCE=0; BOLTZ_CONTACT_FORCE_SET=1; shift 1 ;;
    --boltz-use-potentials) BOLTZ_USE_POTENTIALS_MODE="on"; shift 1 ;;
    --boltz-no-potentials) BOLTZ_USE_POTENTIALS_MODE="off"; shift 1 ;;

    --iptm-threshold) IPTM_THRESHOLD="$2"; IPTM_THRESHOLD_SET=1; shift 2 ;;

    --no-parallel) NO_PARALLEL=1; shift 1 ;;
    --max-parallel) MAX_PARALLEL_USER="$2"; shift 2 ;;
    --calibrate-only) CALIBRATE_ONLY=1; shift 1 ;;
    --resume) RESUME=1; shift 1 ;;
    --check-config) CHECK_CONFIG_ONLY=1; shift 1 ;;
    --skip-predictor-calibration) SKIP_PREDICTOR_CALIBRATION=1; shift 1 ;;
    --design-scheduler|--scheduler) DESIGN_SCHEDULER="$2"; shift 2 ;;
    --wave-batch-size) WAVE_BATCH_SIZE="$2"; WAVE_BATCH_SIZE_USER_SET=1; shift 2 ;;
    --wave-mpnn-max-parallel) MPNN_WAVE_MAX_PARALLEL="$2"; shift 2 ;;
    --throughput-profile) THROUGHPUT_PROFILE="$2"; shift 2 ;;
    --mps-aware) MPS_AWARE=1; shift 1 ;;
    --no-mps-aware) MPS_AWARE=0; shift 1 ;;
    --mps-max-parallel) MPS_MAX_PARALLEL="$2"; shift 2 ;;
    --mps-mem-fraction) MPS_MEM_FRACTION="$2"; shift 2 ;;
    --mps-memory-reserve-gb) MPS_MEMORY_RESERVE_GB="$2"; shift 2 ;;
    --mps-cpu-cap) MPS_CPU_CAP="$2"; shift 2 ;;
    --mem-budget-gb) MEM_BUDGET_GB="$2"; shift 2 ;;
    --mem-safety) MEM_SAFETY="$2"; shift 2 ;;
    --mem-basis) MEM_BASIS="$2"; shift 2 ;;

    --cpu-only) CPU_ONLY=1; shift 1 ;;

    --intellifold-buckets) INTELLIFOLD_BUCKETS="$2"; shift 2 ;;
    --alphafold3-buckets) die "--alphafold3-buckets was retired with AlphaFold 3." ;;
    --boltz-extra) BOLTZ_EXTRA_CLI_STRING="$2"; shift 2 ;;
    --intellifold-extra) INTELLIFOLD_EXTRA_CLI_STRING="$2"; shift 2 ;;
    --openfold-extra) OPENFOLD_EXTRA_CLI_STRING="$2"; shift 2 ;;
    --ligand-extra) LIGAND_EXTRA_CLI_STRING="$2"; shift 2 ;;
    --antifold-extra) ANTIFOLD_EXTRA_CLI_STRING="$2"; shift 2 ;;

    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $1" ;;
  esac
done

apply_nanohunter_settings_payload() {
  local payload="$1"
  local source_name="$2"
  [[ -n "${payload}" ]] || return 0
  while IFS=$'\t' read -r _nh_key _nh_value; do
    [[ -n "${_nh_key:-}" ]] || continue
    case "${_nh_key}" in
      target_epitope_residues)
        if [[ "${TARGET_EPITOPE_RESIDUES_SET}" -eq 0 ]]; then
          TARGET_EPITOPE_RESIDUES="${_nh_value}"
        fi
        ;;
      boltz_contact_distance)
        if [[ "${BOLTZ_CONTACT_DISTANCE_SET}" -eq 0 ]]; then
          BOLTZ_CONTACT_DISTANCE="${_nh_value}"
        fi
        ;;
      boltz_contact_mode)
        if [[ "${BOLTZ_CONTACT_MODE_SET}" -eq 0 ]]; then
          BOLTZ_CONTACT_MODE="${_nh_value}"
        fi
        ;;
      boltz_contact_force)
        if [[ "${BOLTZ_CONTACT_FORCE_SET}" -eq 0 ]]; then
          case "$(printf '%s' "${_nh_value}" | tr '[:upper:]' '[:lower:]')" in
            1|true|yes|on) BOLTZ_CONTACT_FORCE=1 ;;
            0|false|no|off) BOLTZ_CONTACT_FORCE=0 ;;
            *) die "${source_name}: boltz_contact_force must be true or false" ;;
          esac
        fi
        ;;
      nanobody_seed_percent_x)
        if [[ "${NANOBODY_SEED_PERCENT_X_SET}" -eq 0 ]]; then
          NANOBODY_SEED_PERCENT_X="${_nh_value}"
        fi
        ;;
      target_msa_mode)
        if [[ "${TARGET_MSA_MODE_SET}" -eq 0 ]]; then
          TARGET_MSA_MODE="${_nh_value}"
        fi
        ;;
      target_msa_generator)
        if [[ "${TARGET_MSA_GENERATOR_SET}" -eq 0 ]]; then
          TARGET_MSA_GENERATOR="${_nh_value}"
        fi
        ;;
      target_msa_path)
        if [[ "${TARGET_MSA_PATH_OVERRIDE_SET}" -eq 0 ]]; then
          TARGET_MSA_PATH_OVERRIDE="${_nh_value}"
        fi
        ;;
      target_msa_required)
        if [[ "${TARGET_MSA_REQUIRED_SET}" -eq 0 ]]; then
          case "$(printf '%s' "${_nh_value}" | tr '[:upper:]' '[:lower:]')" in
            1|true|yes|on) TARGET_MSA_REQUIRED=1 ;;
            0|false|no|off) TARGET_MSA_REQUIRED=0 ;;
            *) die "${source_name}: target_msa_required must be true or false" ;;
          esac
        fi
        ;;
      nanobody_scaffold_msa)
        if [[ "${NANOBODY_SCAFFOLD_MSA_MODE_SET}" -eq 0 ]]; then
          NANOBODY_SCAFFOLD_MSA_MODE="${_nh_value}"
        fi
        ;;
      nanobody_scaffold_msa_source)
        if [[ "${NANOBODY_SCAFFOLD_MSA_SOURCE_SET}" -eq 0 ]]; then
          NANOBODY_SCAFFOLD_MSA_SOURCE="${_nh_value}"
        fi
        ;;
      nanobody_scaffold_msa_cache_dir)
        if [[ "${NANOBODY_SCAFFOLD_MSA_CACHE_DIR_SET}" -eq 0 ]]; then
          NANOBODY_SCAFFOLD_MSA_CACHE_DIR="${_nh_value}"
        fi
        ;;
      nanobody_scaffold_msa_mask_cdrs)
        if [[ "${NANOBODY_SCAFFOLD_MSA_MASK_CDRS_SET}" -eq 0 ]]; then
          NANOBODY_SCAFFOLD_MSA_MASK_CDRS="${_nh_value}"
        fi
        ;;
      nanobody_scaffold_msa_max_seqs)
        if [[ "${NANOBODY_SCAFFOLD_MSA_MAX_SEQS_SET}" -eq 0 ]]; then
          NANOBODY_SCAFFOLD_MSA_MAX_SEQS="${_nh_value}"
        fi
        ;;
    esac
  done <<< "${payload}"
}

if [[ -f "${TEMPLATE_YAML}" ]]; then
  apply_nanohunter_settings_payload "$(load_nanohunter_input_settings "${TEMPLATE_YAML}" || true)" "${TEMPLATE_YAML}"
fi
if [[ -n "${NANOHUNTER_CONFIG_JSON}" ]]; then
  [[ -f "${NANOHUNTER_CONFIG_JSON}" ]] || die "Workflow config JSON not found: ${NANOHUNTER_CONFIG_JSON}"
  apply_nanohunter_settings_payload "$(load_nanohunter_input_settings "${NANOHUNTER_CONFIG_JSON}" || true)" "${NANOHUNTER_CONFIG_JSON}"
fi

WORKFLOW="$(printf '%s' "${WORKFLOW}" | tr '[:upper:]' '[:lower:]' | tr '_' '-')"
case "${WORKFLOW}" in
  protein|protein-binder|binder|iproteinhunter) WORKFLOW="protein" ;;
  nanobody|vhh|nanohunter) WORKFLOW="nanobody" ;;
  *) die "--workflow must be protein or nanobody" ;;
esac
PREDICTOR="$(norm_predictor "$PREDICTOR")" || die "Unsupported --predictor: ${PREDICTOR}"
SEQUENCE_DESIGNER="$(norm_sequence_designer "$SEQUENCE_DESIGNER")" || die "Unsupported --sequence-designer: ${SEQUENCE_DESIGNER}"
ANTIFOLD_REGIONS_RAW="${ANTIFOLD_REGIONS}"
ANTIFOLD_REGIONS="$(normalize_antifold_regions "${ANTIFOLD_REGIONS_RAW}")" || die "Invalid --nanobody-cdrs: ${ANTIFOLD_REGIONS_RAW}. Use CDR1, CDR2, and/or CDR3."
NANOBODY_SEED_MODE_RAW="${NANOBODY_SEED_MODE}"
NANOBODY_SEED_MODE="$(normalize_nanobody_seed_mode "${NANOBODY_SEED_MODE_RAW}")" || die "Invalid --nanobody-seed-mode: ${NANOBODY_SEED_MODE_RAW}. Use native or cdr-random."
if [[ "$(printf '%s' "${NANOBODY_SEED_CDRS}" | tr '[:upper:]' '[:lower:]')" == "auto" ]]; then
  NANOBODY_SEED_CDRS="${ANTIFOLD_REGIONS}"
else
  NANOBODY_SEED_CDRS_RAW="${NANOBODY_SEED_CDRS}"
  NANOBODY_SEED_CDRS="$(normalize_antifold_regions "${NANOBODY_SEED_CDRS_RAW}")" || die "Invalid --nanobody-seed-cdrs: ${NANOBODY_SEED_CDRS_RAW}. Use CDR1, CDR2, and/or CDR3."
fi
TARGET_MSA_MODE="$(printf '%s' "${TARGET_MSA_MODE}" | tr '[:upper:]' '[:lower:]' | tr '_' '-')"
case "${TARGET_MSA_MODE}" in
  auto|on|true|yes) TARGET_MSA_MODE="auto" ;;
  off|none|false|no) TARGET_MSA_MODE="off" ;;
  *) die "--target-msa-mode must be auto or off" ;;
esac
TARGET_MSA_GENERATOR="$(printf '%s' "${TARGET_MSA_GENERATOR}" | tr '[:upper:]' '[:lower:]' | tr '_' '-')"
case "${TARGET_MSA_GENERATOR}" in
  auto)
    case "${PREDICTOR}" in
      boltz) TARGET_MSA_GENERATOR="boltz" ;;
      intellifold) TARGET_MSA_GENERATOR="intellifold" ;;
      protenix-v2|protenix-mini|protenix-constraint-v0.5) TARGET_MSA_GENERATOR="protenix" ;;
      openfold-3-mlx) TARGET_MSA_GENERATOR="openfold" ;;
      *) die "Cannot infer target MSA generator for predictor ${PREDICTOR}" ;;
    esac
    ;;
  boltz|protenix|intellifold|openfold) : ;;
  *) die "--target-msa-generator must be auto, boltz, protenix, intellifold, or openfold" ;;
esac
case "${TARGET_MSA_REQUIRED}" in
  0|1) : ;;
  *) die "--require-target-msa setting must be boolean" ;;
esac
NANOBODY_SCAFFOLD_MSA_MODE="$(printf '%s' "${NANOBODY_SCAFFOLD_MSA_MODE}" | tr '[:upper:]' '[:lower:]' | tr '_' '-')"
case "${NANOBODY_SCAFFOLD_MSA_MODE}" in
  auto|on|true|yes|masked|masked-cdr|masked-cdrs|masked-cdr3) NANOBODY_SCAFFOLD_MSA_MODE="masked-cdr" ;;
  single|single-sequence|query-only) NANOBODY_SCAFFOLD_MSA_MODE="single" ;;
  off|none|false|no) NANOBODY_SCAFFOLD_MSA_MODE="off" ;;
  *) die "--nanobody-scaffold-msa must be off, masked-cdr, or single" ;;
esac
if [[ "$(printf '%s' "${NANOBODY_SCAFFOLD_MSA_MASK_CDRS}" | tr '[:upper:]' '[:lower:]')" == "auto" ]]; then
  NANOBODY_SCAFFOLD_MSA_MASK_CDRS="${NANOBODY_SEED_CDRS}"
else
  NANOBODY_SCAFFOLD_MSA_MASK_CDRS_RAW="${NANOBODY_SCAFFOLD_MSA_MASK_CDRS}"
  NANOBODY_SCAFFOLD_MSA_MASK_CDRS="$(normalize_antifold_regions "${NANOBODY_SCAFFOLD_MSA_MASK_CDRS_RAW}")" || die "Invalid --nanobody-scaffold-msa-mask-cdrs: ${NANOBODY_SCAFFOLD_MSA_MASK_CDRS_RAW}. Use CDR1, CDR2, and/or CDR3."
fi
case "${NANOBODY_SCAFFOLD_MSA_MASK_CHAR}" in
  -|X|x) : ;;
  *) die "--nanobody-scaffold-msa-mask-char must be '-' or 'X'" ;;
esac
NANOBODY_SCAFFOLD_MSA_MASK_CHAR="$(printf '%s' "${NANOBODY_SCAFFOLD_MSA_MASK_CHAR}" | tr '[:lower:]' '[:upper:]')"

POST_PREDICTOR_RAW="${POST_PREDICTOR}"
POST_PREDICTORS=()
if [[ -n "${POST_PREDICTOR_RAW}" && "$(printf '%s' "${POST_PREDICTOR_RAW}" | tr '[:upper:]' '[:lower:]')" != "none" ]]; then
  IFS=',' read -r -a _tmp_post <<< "${POST_PREDICTOR_RAW}"
  for p in "${_tmp_post[@]}"; do
    p="$(echo "$p" | xargs)"
    [[ -z "$p" ]] && continue
    p="$(norm_predictor "$p")" || die "Unsupported --post-predictor entry: ${p}"
    [[ "$p" == "none" ]] && continue
    _post_seen=0
    for _existing_post in "${POST_PREDICTORS[@]:-}"; do
      if [[ "${_existing_post}" == "${p}" ]]; then _post_seen=1; break; fi
    done
    [[ "${_post_seen}" -eq 1 ]] || POST_PREDICTORS+=("$p")
  done
fi

case "${POST_MODE}" in
  none|all|iptm|final|final-iptm) : ;;
  *) die "--post-mode must be none, all, iptm, final, or final-iptm" ;;
esac

if [[ "${POST_MODE}" == "none" ]]; then
  POST_PREDICTORS=()
fi

# Studio builds before Lab Book 0019 emitted its one visible hit threshold as
# --post-iptm-threshold even when checking was disabled. In that exact case the
# value otherwise has no effect, so recover it as the campaign threshold. Do
# not merge the thresholds for real post-prediction CLI workflows, where users
# may deliberately set different values.
if [[ "${POST_MODE}" == "none" && "${POST_IPTM_THRESHOLD_SET}" -eq 1 \
      && "${IPTM_THRESHOLD_SET}" -eq 0 ]]; then
  IPTM_THRESHOLD="${POST_IPTM_THRESHOLD}"
  echo "WARNING: treating legacy no-checker --post-iptm-threshold as --iptm-threshold (${IPTM_THRESHOLD})." >&2
fi

for _post in "${POST_PREDICTORS[@]:-}"; do
  [[ "${_post}" != "protenix-constraint-v0.5" ]] \
    || die "Protenix Constraint v0.5 is a guided design engine, not an independent post-predictor."
  if [[ -n "${_post}" && "${_post}" == "${PREDICTOR}" ]]; then
    die "--post-predictor must be independent of --predictor; ${_post} cannot check its own designs."
  fi
done

# Mini and v2 are checkpoints from the same Protenix family, not independent
# evidence. They may each drive a campaign, but one must not be presented as an
# orthogonal check of the other.
if [[ "${PREDICTOR}" == protenix-* ]]; then
  for _post in "${POST_PREDICTORS[@]:-}"; do
    [[ "${_post}" != protenix-* ]] \
      || die "Protenix Mini and v2 are not independent models; choose a different post-predictor."
  done
fi

PROTENIX_SELECTED=0
case "${PREDICTOR}" in protenix-v2|protenix-mini|protenix-constraint-v0.5) PROTENIX_SELECTED=1 ;; esac
for _protenix_check in "${POST_PREDICTORS[@]:-}"; do
  case "${_protenix_check}" in protenix-v2|protenix-mini) PROTENIX_SELECTED=1 ;; esac
done
if [[ "${PROTENIX_SELECTED}" -eq 1 && "${MAX_PARALLEL_USER}" != "1" ]]; then
  echo "==> Protenix selected: capping the campaign at one native MPS process."
  MAX_PARALLEL_USER=1
fi

INTELLIFOLD_IN_USE=0
if [[ "${PREDICTOR}" == "intellifold" ]]; then INTELLIFOLD_IN_USE=1; fi
for _post in "${POST_PREDICTORS[@]:-}"; do
  if [[ "${_post}" == "intellifold" ]]; then INTELLIFOLD_IN_USE=1; fi
done
if [[ "${INTELLIFOLD_IN_USE}" -eq 1 ]]; then
  case "${INTELLIFOLD_MODEL}" in
    v2-flash|v2) : ;;
    *) die "--model must be v2-flash or v2 when IntelliFold is used." ;;
  esac
fi

if [[ "${WORKFLOW}" == "protein" ]]; then
  case "${SEQUENCE_DESIGNER}" in
    antifold|abmpnn)
      die "--sequence-designer ${SEQUENCE_DESIGNER} is antibody-specific and requires --workflow nanobody."
      ;;
  esac
  if [[ "${NANOBODY_SCAFFOLD_MSA_MODE}" != "off" ]]; then
    die "--nanobody-scaffold-msa is only valid with --workflow nanobody."
  fi
else
  if [[ "${SCAFFOLD_FROM_TEMPLATE}" -ne 1 ]]; then
    die "--workflow nanobody requires a fixed scaffold; remove --random-binder or pass --scaffold-from-template."
  fi
  if [[ "${MOTIF_SCAFFOLDING}" -eq 1 || "${PARTIAL_REDESIGN}" -eq 1 ]]; then
    die "Motif scaffolding and arbitrary partial redesign belong to --workflow protein; nanobody mode redesigns exact CDR positions."
  fi
fi
if [[ -n "${TARGET_EPITOPE_RESIDUES}" && "${PREDICTOR}" != "boltz" \
      && "${PREDICTOR}" != "protenix-constraint-v0.5" ]]; then
  die "Target hotspot restraints require Boltz or Protenix Constraint v0.5; ${PREDICTOR} cannot honour them."
fi

if [[ "${MOTIF_SCAFFOLDING}" -eq 1 && "${PREDICTOR}" != "boltz" ]]; then
  die "--motif-scaffolding currently supports --predictor boltz only."
fi
if [[ "${MOTIF_SCAFFOLDING}" -eq 1 && "${PARTIAL_REDESIGN}" -eq 1 ]]; then
  die "--motif-scaffolding and --partial-redesign cannot be used together."
fi
if [[ "${SEQUENCE_DESIGNER}" == "antifold" && "${MOTIF_SCAFFOLDING}" -eq 1 ]]; then
  die "--sequence-designer antifold is not compatible with --motif-scaffolding; use --nanobody-cdrs for CDR sampling."
fi
if [[ "${SEQUENCE_DESIGNER}" == "antifold" && "${PARTIAL_REDESIGN}" -eq 1 ]]; then
  die "--sequence-designer antifold is not compatible with --partial-redesign; use --nanobody-cdrs for CDR1/CDR2/CDR3 sampling."
fi
if [[ "${SEQUENCE_DESIGNER}" == "antifold" && "${SCAFFOLD_FROM_TEMPLATE}" -ne 1 ]]; then
  die "--sequence-designer antifold requires a fixed nanobody scaffold template."
fi
if [[ "${SKIP_PREDICTOR_CALIBRATION}" -eq 1 && "${CALIBRATE_ONLY}" -eq 1 ]]; then
  die "--skip-predictor-calibration cannot be combined with --calibrate-only."
fi
if [[ "${SKIP_PREDICTOR_CALIBRATION}" -eq 1 && "${MAX_PARALLEL_USER}" == "auto" ]]; then
  die "--skip-predictor-calibration requires an explicit --max-parallel value."
fi
if [[ "${MAX_PARALLEL_USER}" != "auto" && ! "${MAX_PARALLEL_USER}" =~ ^[1-9][0-9]*$ ]]; then
  die "--max-parallel must be auto or a positive integer."
fi
DESIGN_SCHEDULER="$(printf '%s' "${DESIGN_SCHEDULER}" | tr '[:upper:]' '[:lower:]' | tr '_' '-')"
case "${DESIGN_SCHEDULER}" in
  run|per-run|run-parallel) DESIGN_SCHEDULER="run" ;;
  cycle-wave|wave) DESIGN_SCHEDULER="cycle-wave" ;;
  resident|campaign-resident) DESIGN_SCHEDULER="resident" ;;
  *) die "--design-scheduler must be run, cycle-wave, or resident." ;;
esac
if [[ "${WAVE_BATCH_SIZE}" != "all" && ! "${WAVE_BATCH_SIZE}" =~ ^[1-9][0-9]*$ ]]; then
  die "--wave-batch-size must be all or a positive integer."
fi
if [[ ! "${MPNN_WAVE_MAX_PARALLEL}" =~ ^[1-9][0-9]*$ ]]; then
  die "--wave-mpnn-max-parallel must be a positive integer."
fi
if [[ "${DESIGN_SCHEDULER}" == "cycle-wave" || "${DESIGN_SCHEDULER}" == "resident" ]]; then
  case "${WORKFLOW}" in
    nanobody|protein) ;;
    *) die "--design-scheduler ${DESIGN_SCHEDULER} supports protein and nanobody workflows." ;;
  esac
  case "${PREDICTOR}" in
    boltz|intellifold|protenix-v2|protenix-mini|protenix-constraint-v0.5|openfold-3-mlx) ;;
    *) die "--design-scheduler ${DESIGN_SCHEDULER} does not support predictor ${PREDICTOR}." ;;
  esac
  if [[ "${WORKFLOW}" == "nanobody" && "${SCAFFOLD_FROM_TEMPLATE}" -ne 1 ]]; then
    die "--design-scheduler ${DESIGN_SCHEDULER} requires fixed-scaffold nanobody design."
  fi
  if [[ "${WORKFLOW}" == "protein" && "${SEQUENCE_DESIGNER}" == "antifold" ]]; then
    die "AntiFold is nanobody-specific; use a ProteinMPNN-family designer for protein cycle-wave jobs."
  fi
  if [[ "${MOTIF_SCAFFOLDING}" -eq 1 || "${PARTIAL_REDESIGN}" -eq 1 ]]; then
    die "--design-scheduler ${DESIGN_SCHEDULER} does not support motif or partial-redesign modes."
  fi
fi
if [[ "${DESIGN_SCHEDULER}" == "resident" ]]; then
  case "${PREDICTOR}" in
    boltz|intellifold|protenix-v2|protenix-mini|protenix-constraint-v0.5) ;;
    *) die "--design-scheduler resident has no validated worker for predictor ${PREDICTOR}." ;;
  esac
  [[ -f "${RESIDENT_PREDICTOR}" ]] || die "Resident predictor worker not found: ${RESIDENT_PREDICTOR}"
  [[ "${MAX_PARALLEL_USER}" == "1" ]] || die "--design-scheduler resident requires --max-parallel 1."
  [[ "${WAVE_BATCH_SIZE}" == "all" ]] || die "--design-scheduler resident requires --wave-batch-size all."
fi

if [[ ! "${LIGANDMPNN_SEED}" =~ ^[0-9]+$ ]]; then
  die "--mpnn-seed must be a non-negative integer."
fi
if [[ ! "${LASERMPNN_SEED}" =~ ^[0-9]+$ ]]; then
  die "--lasermpnn-seed must be a non-negative integer."
fi
if [[ -n "${BINDER_RANDOM_SEED}" && ! "${BINDER_RANDOM_SEED}" =~ ^[0-9]+$ ]]; then
  die "--binder-random-seed must be a non-negative integer."
fi
if [[ ! "${PREDICTOR_SEED}" =~ ^[0-9]+$ ]]; then
  die "--predictor-seed must be a non-negative integer."
fi
if [[ "${PREDICTOR_SAMPLES}" != "auto" && ! "${PREDICTOR_SAMPLES}" =~ ^[1-9][0-9]*$ ]]; then
  die "--predictor-samples must be auto or a positive integer."
fi

python3 - "$N_RUNS" "$N_CYCLES" "$IPTM_THRESHOLD" "$POST_IPTM_THRESHOLD" "$MEM_SAFETY" "$LIGAND_TEMP_DEFAULT" "$LIGAND_TEMP_CYCLE01" "$NEGATIVE_HELIX_CONSTANT" "$LOOP_KILL" "$ANTIFOLD_SEED" "$ANTIFOLD_NUM_SEQ_PER_TARGET" "$ANTIFOLD_BATCH_SIZE" "$ANTIFOLD_NUM_THREADS" "$NANOBODY_SEED_MAX_ATTEMPTS" "$NANOBODY_CHARGE_MIN" "$NANOBODY_CHARGE_MAX" "$NANOBODY_HYDRO_MAX" "$NANOBODY_SEED_PERCENT_X" "$BOLTZ_CONTACT_DISTANCE" "$NANOBODY_SCAFFOLD_MSA_MAX_SEQS" <<'PY'
import sys
for idx, name, minimum in (
    (1, "--num-runs", 1),
    (2, "--num-opt-cycles", 0),
):
    try:
        v = int(sys.argv[idx])
    except Exception:
        raise SystemExit(f"{name} must be an integer")
    if v < minimum:
        raise SystemExit(f"{name} must be >= {minimum}")
for idx, name in ((3,"--iptm-threshold"),(4,"--post-iptm-threshold"),(5,"--mem-safety"),(6,"--ligand-temp-other"),(7,"--ligand-temp-cycle1")):
    try:
        float(sys.argv[idx])
    except Exception:
        raise SystemExit(f"{name} must be numeric")
try:
    nhc = float(sys.argv[8])
except Exception:
    raise SystemExit("--negative-helix-constant must be numeric")
if not (0.0 <= nhc <= 1.0):
    raise SystemExit("--negative-helix-constant must be between 0 and 1")
try:
    lkc = float(sys.argv[9])
except Exception:
    raise SystemExit("--loopkill must be numeric")
if not (0.0 <= lkc <= 1.0):
    raise SystemExit("--loopkill must be between 0 and 1")
for idx, name in ((10, "--antifold-seed"), (11, "--antifold-num-seq-per-target"), (12, "--antifold-batch-size"), (13, "--antifold-num-threads")):
    try:
        v = int(sys.argv[idx])
    except Exception:
        raise SystemExit(f"{name} must be an integer")
    if name in {"--antifold-num-seq-per-target", "--antifold-batch-size"} and v < 1:
        raise SystemExit(f"{name} must be >= 1")
    if name == "--antifold-num-threads" and v < 0:
        raise SystemExit(f"{name} must be >= 0")
try:
    attempts = int(sys.argv[14])
except Exception:
    raise SystemExit("--nanobody-seed-max-attempts must be an integer")
if attempts < 1:
    raise SystemExit("--nanobody-seed-max-attempts must be >= 1")
try:
    charge_min = float(sys.argv[15])
    charge_max = float(sys.argv[16])
except Exception:
    raise SystemExit("--nanobody-charge-min and --nanobody-charge-max must be numeric")
if charge_min > charge_max:
    raise SystemExit("--nanobody-charge-min must be <= --nanobody-charge-max")
try:
    hydro_max = float(sys.argv[17])
except Exception:
    raise SystemExit("--nanobody-hydrophobic-max must be numeric")
if not (0.0 <= hydro_max <= 1.0):
    raise SystemExit("--nanobody-hydrophobic-max must be between 0 and 1")
try:
    seed_pct_x = float(sys.argv[18])
except Exception:
    raise SystemExit("--nanobody-seed-percent-x must be numeric")
if not (0.0 <= seed_pct_x <= 100.0):
    raise SystemExit("--nanobody-seed-percent-x must be between 0 and 100")
try:
    contact_distance = float(sys.argv[19])
except Exception:
    raise SystemExit("--boltz-contact-distance must be numeric")
if not (4.0 <= contact_distance <= 20.0):
    raise SystemExit("--boltz-contact-distance must be between 4 and 20")
try:
    scaffold_msa_max = int(sys.argv[20])
except Exception:
    raise SystemExit("--nanobody-scaffold-msa-max-seqs must be an integer")
if scaffold_msa_max < 1:
    raise SystemExit("--nanobody-scaffold-msa-max-seqs must be >= 1")
PY

case "${NANOBODY_ALLOW_CDR_CYS}" in
  0|1) : ;;
  *) die "Internal error: NANOBODY_ALLOW_CDR_CYS must be 0 or 1" ;;
esac
case "${NANOBODY_USE_SOFT_FILTERS}" in
  0|1) : ;;
  *) die "Internal error: NANOBODY_USE_SOFT_FILTERS must be 0 or 1" ;;
esac
case "${BOLTZ_CONTACT_FORCE}" in
  0|1) : ;;
  *) die "Internal error: BOLTZ_CONTACT_FORCE must be 0 or 1" ;;
esac
BOLTZ_CONTACT_MODE="$(printf '%s' "${BOLTZ_CONTACT_MODE}" | tr '[:upper:]' '[:lower:]')"
case "${BOLTZ_CONTACT_MODE}" in
  auto|none|pocket|cdr3|pocket+cdr3|cdr3+pocket) : ;;
  *) die "--boltz-contact-mode must be auto, none, pocket, cdr3, or pocket+cdr3" ;;
esac
if [[ "${BOLTZ_CONTACT_MODE}" == "cdr3+pocket" ]]; then
  BOLTZ_CONTACT_MODE="pocket+cdr3"
fi
if [[ "${WORKFLOW}" == "protein" ]]; then
  case "${BOLTZ_CONTACT_MODE}" in
    auto) BOLTZ_CONTACT_MODE="pocket" ;;
    cdr3|pocket+cdr3)
      echo "WARNING: CDR3 contact mode has no meaning for --workflow protein; using the equivalent binder-pocket restraint." >&2
      BOLTZ_CONTACT_MODE="pocket"
      ;;
  esac
elif [[ "${BOLTZ_CONTACT_MODE}" == "auto" ]]; then
  BOLTZ_CONTACT_MODE="pocket+cdr3"
fi
if [[ -n "${TARGET_EPITOPE_RESIDUES}" ]]; then
  python3 - "${TARGET_EPITOPE_RESIDUES}" <<'PY'
import re
import sys
raw = sys.argv[1]
tokens = [t.strip() for t in re.split(r"[\s,;]+", raw) if t.strip()]
if not tokens:
    raise SystemExit("No residues parsed from --target-epitope-residues")
for tok in tokens:
    if ":" in tok:
        ok = re.match(r"^[A-Za-z0-9]+\s*:\s*\d+$", tok)
    else:
        ok = re.match(r"^[A-Za-z]+\d+$", tok)
    if not ok:
        raise SystemExit(f"Invalid target epitope residue '{tok}'. Use forms like B6 or B:6.")
PY
fi

if [[ "${UNK_PATCH_MODE}" == "auto" ]]; then
  if [[ "${HELIX_KILL}" -eq 1 ]]; then
    UNK_PATCH_MODE="ala_gly_ser"
  else
    UNK_PATCH_MODE="ala"
  fi
fi
case "${UNK_PATCH_MODE}" in
  ala|ala_gly|ala_gly_ser) : ;;
  *) die "Invalid --unk-patch-mode: ${UNK_PATCH_MODE}" ;;
esac

BOLTZ_EXTRA_FLAGS=("${BOLTZ_EXTRA_FLAGS_DEFAULT[@]}")
if [[ -n "${BOLTZ_EXTRA_CLI_STRING}" ]]; then
  # shellcheck disable=SC2206
  _arr=(${BOLTZ_EXTRA_CLI_STRING})
  BOLTZ_EXTRA_FLAGS+=("${_arr[@]}")
fi

INTELLIFOLD_EXTRA_FLAGS=("${INTELLIFOLD_EXTRA_FLAGS_DEFAULT[@]}" "--model" "${INTELLIFOLD_MODEL}")
if [[ -n "${INTELLIFOLD_EXTRA_CLI_STRING}" ]]; then
  # shellcheck disable=SC2206
  _arr=(${INTELLIFOLD_EXTRA_CLI_STRING})
  INTELLIFOLD_EXTRA_FLAGS+=("${_arr[@]}")
fi

# Explicit work controls are primarily for reproducible validation. `auto`
# keeps the established engine defaults; setting a value equalizes the number
# of generated structures without changing it for existing projects.
BOLTZ_EXTRA_FLAGS+=("--seed" "${PREDICTOR_SEED}")
INTELLIFOLD_EXTRA_FLAGS+=("--seed" "${PREDICTOR_SEED}")
if [[ "${PREDICTOR_SAMPLES}" != "auto" ]]; then
  BOLTZ_EXTRA_FLAGS+=("--diffusion_samples" "${PREDICTOR_SAMPLES}")
  INTELLIFOLD_EXTRA_FLAGS+=("--num_diffusion_samples" "${PREDICTOR_SAMPLES}")
fi

OPENFOLD_EXTRA_FLAGS=("${OPENFOLD_EXTRA_FLAGS_DEFAULT[@]}")
if [[ -n "${OPENFOLD_EXTRA_CLI_STRING}" ]]; then
  # shellcheck disable=SC2206
  _arr=(${OPENFOLD_EXTRA_CLI_STRING})
  OPENFOLD_EXTRA_FLAGS+=("${_arr[@]}")
fi

LIGANDMPNN_EXTRA_FLAGS=("${LIGANDMPNN_EXTRA_FLAGS_DEFAULT[@]}")
if [[ -n "${LIGAND_EXTRA_CLI_STRING}" ]]; then
  # shellcheck disable=SC2206
  _arr=(${LIGAND_EXTRA_CLI_STRING})
  LIGANDMPNN_EXTRA_FLAGS+=("${_arr[@]}")
fi

ANTIFOLD_EXTRA_FLAGS=()
if [[ -n "${ANTIFOLD_EXTRA_CLI_STRING}" ]]; then
  # shellcheck disable=SC2206
  _arr=(${ANTIFOLD_EXTRA_CLI_STRING})
  ANTIFOLD_EXTRA_FLAGS+=("${_arr[@]}")
fi

if [[ "${CPU_ONLY}" -eq 1 ]]; then
  _tmp_flags=()
  _skip_next=0
  for tok in "${BOLTZ_EXTRA_FLAGS[@]}"; do
    if [[ "${_skip_next}" -eq 1 ]]; then
      _skip_next=0
      continue
    fi
    if [[ "${tok}" == "--accelerator" || "${tok}" == "--devices" ]]; then
      _skip_next=1
      continue
    fi
    _tmp_flags+=("${tok}")
  done
  BOLTZ_EXTRA_FLAGS=("${_tmp_flags[@]}" "--accelerator" "cpu" "--devices" "1")
fi

[[ -d "${REPO_ROOT}" ]] || die "Repo root not found: ${REPO_ROOT}"
[[ -f "${TEMPLATE_YAML}" ]] || die "Template YAML not found: ${TEMPLATE_YAML}"
if [[ -n "${INITIAL_CONFIDENCE_JSON}" && -z "${INITIAL_STRUCTURE}" ]]; then
  die "--initial-confidence-json requires --initial-structure."
fi
if [[ -n "${INITIAL_STRUCTURE}" ]]; then
  [[ -f "${INITIAL_STRUCTURE}" ]] || die "Initial structure not found: ${INITIAL_STRUCTURE}"
  case "$(printf '%s' "${INITIAL_STRUCTURE##*.}" | tr '[:upper:]' '[:lower:]')" in
    cif|pdb) : ;;
    *) die "--initial-structure must be a CIF or PDB file." ;;
  esac
  [[ "${N_RUNS}" == "1" ]] || die "--initial-structure currently requires --num-runs 1."
  [[ "${DESIGN_SCHEDULER}" == "run" ]] || die "--initial-structure requires --design-scheduler run."
  [[ "${SCAFFOLD_FROM_TEMPLATE}" -eq 1 ]] || die "--initial-structure requires --scaffold-from-template with its exact chain A sequence."
  [[ "${MOTIF_SCAFFOLDING}" -eq 0 && "${PARTIAL_REDESIGN}" -eq 0 ]] || die "--initial-structure cannot be combined with motif scaffolding or partial redesign."
  INITIAL_STRUCTURE="$(cd "$(dirname "${INITIAL_STRUCTURE}")" && pwd)/$(basename "${INITIAL_STRUCTURE}")"
  if [[ -n "${INITIAL_CONFIDENCE_JSON}" ]]; then
    [[ -f "${INITIAL_CONFIDENCE_JSON}" ]] || die "Initial confidence JSON not found: ${INITIAL_CONFIDENCE_JSON}"
    INITIAL_CONFIDENCE_JSON="$(cd "$(dirname "${INITIAL_CONFIDENCE_JSON}")" && pwd)/$(basename "${INITIAL_CONFIDENCE_JSON}")"
  fi
fi

# Only validate venvs for predictors actually in use (design predictor + any
# post-predictors). This avoids requiring, e.g., OpenFold when running
# boltz + intellifold.
require_predictor_venv() {
  case "$1" in
    boltz)
      [[ -x "${BOLTZ_VENV}/bin/python" ]] || die "Boltz venv not found: ${BOLTZ_VENV}" ;;
    intellifold)
      [[ -x "${INTELLIFOLD_VENV}/bin/python" ]] || die "IntelliFold venv not found: ${INTELLIFOLD_VENV}"
      [[ "${CPU_ONLY}" -eq 0 ]] || die "IntelliFold is GPU-only in iProteinStudio; --cpu-only is not available."
      [[ -f "${INTELLIFOLD_UPSTREAM_RUNNER}" ]] || die "IntelliFold upstream runner not found: ${INTELLIFOLD_UPSTREAM_RUNNER}"
      [[ -f "${INTELLIFOLD_RUNNER}" ]] || die "IntelliFold MPS launcher not found: ${INTELLIFOLD_RUNNER}" ;;
    protenix-v2|protenix-mini)
      [[ "${CPU_ONLY}" -eq 0 ]] || die "Protenix is GPU-only in iProteinStudio; --cpu-only is not available."
      [[ -x "${PROTENIX_VENV}/bin/python" ]] || die "Protenix venv not found: ${PROTENIX_VENV}"
      [[ -f "${PROTENIX_ADAPTER}" ]] || die "Protenix adapter not found: ${PROTENIX_ADAPTER}"
      [[ -f "${PROTENIX_MODEL_DIR}/checkpoint/protenix-v2.pt" ]] || die "Protenix v2 checkpoint is missing. Re-run setup."
      [[ -f "${PROTENIX_MODEL_DIR}/checkpoint/protenix_mini_default_v0.5.0.pt" ]] || die "Protenix Mini checkpoint is missing. Re-run setup." ;;
    protenix-constraint-v0.5)
      [[ "${CPU_ONLY}" -eq 0 ]] || die "Protenix Constraint is GPU-only; --cpu-only is not available."
      [[ -x "${PROTENIX_CONSTRAINT_VENV}/bin/python" ]] || die "Protenix Constraint venv not found: ${PROTENIX_CONSTRAINT_VENV}"
      [[ -f "${PROTENIX_ADAPTER}" ]] || die "Protenix adapter not found: ${PROTENIX_ADAPTER}"
      [[ -f "${PROTENIX_CONSTRAINT_MODEL_DIR}/checkpoint/protenix_base_constraint_v0.5.0.pt" ]] || die "Protenix Constraint checkpoint is missing. Re-run setup."
      [[ -f "${PROTENIX_CONSTRAINT_MODEL_DIR}/install_receipt.json" ]] || die "Protenix Constraint install receipt is missing. Repair the engine in Setup." ;;
    openfold-3-mlx)
      [[ -x "${OPENFOLD_VENV}/bin/python" ]] || die "OpenFold venv not found: ${OPENFOLD_VENV}"
      [[ -f "${OPENFOLD_A3M_QUERY_REWRITER}" ]] || die "OpenFold A3M query helper not found: ${OPENFOLD_A3M_QUERY_REWRITER}" ;;
    none|"") : ;;
    *) die "Unknown predictor for venv check: $1" ;;
  esac
}

require_predictor_venv "${PREDICTOR}"
for _pp in "${POST_PREDICTORS[@]:-}"; do
  [[ -n "${_pp}" ]] && require_predictor_venv "${_pp}"
done
if [[ "$(post_predictors_count)" -gt 0 ]]; then
  [[ -f "${POST_TASK_SELECTOR}" ]] || die "Post-prediction task selector not found: ${POST_TASK_SELECTOR}"
fi
if sequence_designer_uses_ligandmpnn; then
  [[ -x "${LIGAND_VENV}/bin/python" ]] || die "LigandMPNN venv not found: ${LIGAND_VENV}"
  [[ -f "${LIGANDMPNN_REPO}/run.py" ]] || die "LigandMPNN run.py not found: ${LIGANDMPNN_REPO}/run.py"
fi
if [[ "${SEQUENCE_DESIGNER}" == "antifold" ]]; then
  [[ -x "${ANTIFOLD_VENV}/bin/python" ]] || die "AntiFold venv not found: ${ANTIFOLD_VENV}"
  [[ -f "${ANTIFOLD_REPO}/antifold/main.py" ]] || die "AntiFold main.py not found: ${ANTIFOLD_REPO}/antifold/main.py"
  [[ -f "${ANTIFOLD_EXACT_SAMPLER}" ]] || die "NanoHunter exact-position AntiFold sampler not found: ${ANTIFOLD_EXACT_SAMPLER}"
fi
if [[ "${SEQUENCE_DESIGNER}" == "lasermpnn" ]]; then
  [[ -x "${LASERMPNN_VENV}/bin/python" ]] || die "LASErMPNN venv not found: ${LASERMPNN_VENV} (run install_nanohunter.sh)"
  [[ -f "${LASERMPNN_REPO}/run_batch_inference.py" ]] || die "LASErMPNN not found: ${LASERMPNN_REPO}/run_batch_inference.py"
  [[ -f "${LASERMPNN_WEIGHTS}" ]] || die "LASErMPNN weights not found: ${LASERMPNN_WEIGHTS}"
  [[ -f "${LASERMPNN_PREPARE}" ]] || die "LASErMPNN input-prep helper not found: ${LASERMPNN_PREPARE}"
  [[ -f "${LASERMPNN_SEEDED_RUNNER}" ]] || die "LASErMPNN seeded launcher not found: ${LASERMPNN_SEEDED_RUNNER}"
fi

if [[ "${MOTIF_SCAFFOLDING}" -eq 1 ]]; then
  [[ -f "${MOTIF_HELPER}" ]] || die "Motif helper not found: ${MOTIF_HELPER}"
  [[ -n "${MOTIF_POSITIONS}" ]] || die "--motif-positions is required with --motif-scaffolding"
  [[ -n "${MOTIF_SOURCE_SEQ}" ]] || die "--motif-source-seq is required with --motif-scaffolding"
  python3 "${MOTIF_HELPER}" validate \
    --motif-positions "${MOTIF_POSITIONS}" \
    --source-sequence "${MOTIF_SOURCE_SEQ}" \
    --motif-fixed-positions "${MOTIF_FIXED_POSITIONS}" \
    --gap-between-motifs "${MOTIF_GAP_BETWEEN}" \
    --min-length "${BINDER_MIN_LEN}" \
    --max-length "${BINDER_MAX_LEN}" \
    >/dev/null
fi

if [[ "${PARTIAL_REDESIGN}" -eq 1 ]]; then
  [[ -n "${PARTIAL_REDESIGN_RANGES}" ]] || die "--partial-redesign-ranges is required with --partial-redesign"
  set +e
  local_partial_payload="$(
    python3 - "${TEMPLATE_YAML}" "${PARTIAL_REDESIGN_RANGES}" 2>&1 <<'PY'
import re
import sys

template_yaml, ranges_raw = sys.argv[1:3]

cur = None
seqs = {}
in_protein = False
for raw in open(template_yaml):
    s = raw.strip()
    if s.startswith("- protein:"):
        in_protein = True
        cur = None
        continue
    if not in_protein:
        continue
    if s.startswith("-") and not s.startswith("- protein:"):
        in_protein = False
        continue
    if s.startswith("id:"):
        cur = s.split(":", 1)[1].strip().strip("'\"")
        continue
    if s.startswith("sequence:") and cur:
        seqs[cur] = s.split(":", 1)[1].strip().strip("'\"")

binder_seq = (seqs.get("A", "") or "").strip()
if not binder_seq or binder_seq.lower() in {"empty", "none", "null"}:
    raise SystemExit("Template chain A sequence is empty; partial redesign requires a concrete binder sequence.")

L = len(binder_seq)
tokens = [t.strip() for t in re.split(r"[;,]", ranges_raw) if t.strip()]
if not tokens:
    raise SystemExit("No valid ranges parsed from --partial-redesign-ranges.")

ranges = []
for tok in tokens:
    if "-" not in tok:
        raise SystemExit(f"Invalid redesign range '{tok}', expected start-end.")
    a, b = tok.split("-", 1)
    start = int(a.strip())
    end = int(b.strip())
    if start < 1 or end < 1:
        raise SystemExit(f"Invalid redesign range '{tok}', positions must be >= 1.")
    if start > end:
        raise SystemExit(f"Invalid redesign range '{tok}', start > end.")
    if end > L:
        raise SystemExit(
            f"Invalid redesign range '{tok}', exceeds binder length {L}."
        )
    ranges.append((start, end))

ranges.sort()
for i in range(1, len(ranges)):
    if ranges[i][0] <= ranges[i - 1][1]:
        raise SystemExit("Redesign ranges must be non-overlapping.")

positions = []
for a, b in ranges:
    positions.extend(range(a, b + 1))

norm_ranges = ",".join(f"{a}-{b}" for a, b in ranges)
redesigned = " ".join(f"A{p}" for p in positions)
print("\t".join([binder_seq, redesigned, norm_ranges, str(L)]))
PY
  )"
  partial_rc=$?
  set -e
  if [[ "${partial_rc}" -ne 0 ]]; then
    die "${local_partial_payload}"
  fi
  IFS=$'\t' read -r PARTIAL_BINDER_SEQ PARTIAL_REDESIGNED_RESIDUES PARTIAL_REDESIGN_RANGES PARTIAL_BINDER_LEN <<< "${local_partial_payload}"
  [[ -n "${PARTIAL_BINDER_SEQ}" ]] || die "Failed to parse binder sequence for partial redesign."
  [[ -n "${PARTIAL_REDESIGNED_RESIDUES}" ]] || die "Failed to parse redesigned residues for partial redesign."
fi

HAS_SMALL_MOLECULE_LIGAND="$(python3 - "${TEMPLATE_YAML}" <<'PY'
import sys
path = sys.argv[1]
for raw in open(path):
    if raw.strip().startswith("- ligand:"):
        print("1")
        raise SystemExit(0)
print("0")
PY
)"

if [[ "${SEQUENCE_DESIGNER}" == "auto" ]]; then
  if [[ "${WORKFLOW}" == "nanobody" ]]; then
    SEQUENCE_DESIGNER="abmpnn"
  elif [[ "${HAS_SMALL_MOLECULE_LIGAND}" == "1" ]]; then
    SEQUENCE_DESIGNER="ligandmpnn"
  else
    SEQUENCE_DESIGNER="solublempnn"
  fi
fi

# LASErMPNN is deliberately restricted to small-molecule minibinder design:
# it is a ligand-aware inverse folder and is never auto-selected.
if [[ "${SEQUENCE_DESIGNER}" == "lasermpnn" ]]; then
  [[ "${WORKFLOW}" == "protein" ]] || die "--sequence-designer lasermpnn is only for small-molecule minibinder design (--workflow protein), not --workflow ${WORKFLOW}."
  [[ "${HAS_SMALL_MOLECULE_LIGAND}" == "1" ]] || die "--sequence-designer lasermpnn requires a small-molecule ligand in the template; ${TEMPLATE_YAML} has none."
  if [[ "${MOTIF_SCAFFOLDING}" -eq 1 ]]; then
    die "--sequence-designer lasermpnn does not support motif scaffolding; use ligandmpnn for that mode."
  fi
fi

case "${SEQUENCE_DESIGNER}" in
  proteinmpnn)
    [[ -f "${LIGANDMPNN_CHECKPOINT_PROTEIN}" ]] || die "ProteinMPNN checkpoint not found: ${LIGANDMPNN_CHECKPOINT_PROTEIN}"
    LIGANDMPNN_MODEL_FLAGS=(
      "--model_type" "protein_mpnn"
      "--checkpoint_protein_mpnn" "${LIGANDMPNN_CHECKPOINT_PROTEIN}"
    )
    LIGANDMPNN_MODEL_LABEL="protein_mpnn"
    SEQUENCE_DESIGNER_LABEL="protein_mpnn"
    ;;
  ligandmpnn)
    [[ -f "${LIGANDMPNN_CHECKPOINT_LIGAND}" ]] || die "LigandMPNN checkpoint not found: ${LIGANDMPNN_CHECKPOINT_LIGAND}"
    LIGANDMPNN_MODEL_FLAGS=(
      "--model_type" "ligand_mpnn"
      "--checkpoint_ligand_mpnn" "${LIGANDMPNN_CHECKPOINT_LIGAND}"
    )
    LIGANDMPNN_MODEL_LABEL="ligand_mpnn"
    SEQUENCE_DESIGNER_LABEL="ligand_mpnn"
    ;;
  abmpnn)
    # AbMPNN is a ProteinMPNN-architecture checkpoint fine-tuned on antibodies,
    # so it is loaded through the protein_mpnn model type.
    [[ -f "${LIGANDMPNN_CHECKPOINT_ABMPNN}" ]] || die "AbMPNN checkpoint not found: ${LIGANDMPNN_CHECKPOINT_ABMPNN} (download abmpnn.pt from Zenodo 10.5281/zenodo.8164693 into ${LIGANDMPNN_REPO}/model_params/)"
    LIGANDMPNN_MODEL_FLAGS=(
      "--model_type" "protein_mpnn"
      "--checkpoint_protein_mpnn" "${LIGANDMPNN_CHECKPOINT_ABMPNN}"
    )
    LIGANDMPNN_MODEL_LABEL="abmpnn"
    SEQUENCE_DESIGNER_LABEL="abmpnn"
    ;;
  solublempnn)
    [[ -f "${LIGANDMPNN_CHECKPOINT_SOLUBLE}" ]] || die "SolubleMPNN checkpoint not found: ${LIGANDMPNN_CHECKPOINT_SOLUBLE}"
    LIGANDMPNN_MODEL_FLAGS=(
      "--model_type" "soluble_mpnn"
      "--checkpoint_soluble_mpnn" "${LIGANDMPNN_CHECKPOINT_SOLUBLE}"
    )
    LIGANDMPNN_MODEL_LABEL="soluble_mpnn"
    SEQUENCE_DESIGNER_LABEL="soluble_mpnn"
    ;;
  lasermpnn)
    # Only for small-molecule minibinder design: enforced in the workflow guard below.
    [[ -f "${LASERMPNN_WEIGHTS}" ]] || die "LASErMPNN weights not found: ${LASERMPNN_WEIGHTS}"
    LASERMPNN_LIGAND_SMILES="$(extract_ligand_smiles_from_yaml "${TEMPLATE_YAML}")"
    [[ -n "${LASERMPNN_LIGAND_SMILES}" ]] || die "LASErMPNN requires a ligand SMILES in ${TEMPLATE_YAML} (CCD-only ligands are not supported for LASErMPNN; add a 'smiles:' field)."
    SEQUENCE_DESIGNER_LABEL="lasermpnn"
    ;;
  antifold)
    SEQUENCE_DESIGNER_LABEL="antifold"
    ;;
  *)
    die "Unsupported sequence designer: ${SEQUENCE_DESIGNER}"
    ;;
esac

if [[ "${CHECK_CONFIG_ONLY}" -eq 1 ]]; then
  _check_post_names="none"
  if [[ "$(post_predictors_count)" -gt 0 ]]; then
    _check_post_names=""
    for _check_post in "${POST_PREDICTORS[@]}"; do
      _check_safe="$(safe_predictor_name "${_check_post}")" \
        || die "No output-name mapping for post predictor ${_check_post}."
      [[ -z "${_check_post_names}" ]] \
        && _check_post_names="${_check_safe}" \
        || _check_post_names="${_check_post_names},${_check_safe}"
    done
  fi
  _check_intellifold_model="unused"
  [[ "${INTELLIFOLD_IN_USE}" -eq 0 ]] || _check_intellifold_model="${INTELLIFOLD_MODEL}"
  echo "CHECK_CONFIG_OK workflow=${WORKFLOW} predictor=${PREDICTOR} sequence_designer=${SEQUENCE_DESIGNER} post=${_check_post_names} post_mode=${POST_MODE} hit_threshold=${IPTM_THRESHOLD} intellifold_model=${_check_intellifold_model} contact_mode=${BOLTZ_CONTACT_MODE} predictor_seed=${PREDICTOR_SEED} predictor_samples=${PREDICTOR_SAMPLES} template=${TEMPLATE_YAML} scheduler=${DESIGN_SCHEDULER}"
  exit 0
fi

mkdir -p "${BASE_RUN_ROOT}"

now_epoch() {
  python3 - <<'PY'
import time
print(f"{time.time():.6f}")
PY
}

calc_duration() {
  python3 - "$1" "$2" <<'PY'
import sys
s=float(sys.argv[1]); e=float(sys.argv[2])
print(f"{max(0.0,e-s):.6f}")
PY
}

total_ram_bytes() { sysctl -n hw.memsize 2>/dev/null || echo "0"; }

default_mem_budget_mb() {
  local total_b
  total_b="$(total_ram_bytes)"
  python3 - "$total_b" <<'PY'
import sys
total=int(sys.argv[1])
budget=int(total*0.75/1024/1024)
print(max(1024, budget))
PY
}

floor_mul() {
  python3 - "$1" "$2" <<'PY'
import sys, math
a=float(sys.argv[1]); b=float(sys.argv[2])
print(int(math.floor(a*b)))
PY
}

float_ge() {
  python3 - "$1" "$2" <<'PY'
import sys
a=float(sys.argv[1]); b=float(sys.argv[2])
raise SystemExit(0 if a>=b else 1)
PY
}

is_float() {
  python3 - "$1" <<'PY'
import sys
try:
    float(sys.argv[1])
except Exception:
    raise SystemExit(1)
raise SystemExit(0)
PY
}

normalize_predictor_result_line() {
  local raw="$1"
  python3 - "$raw" <<'PY'
import sys

text = sys.argv[1]
lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
for ln in reversed(lines):
    if ln.count("|") >= 3:
        print(ln)
        raise SystemExit(0)
if lines:
    print(lines[-1])
PY
}

get_system_available_kb() {
  python3 - <<'PY'
import re
import subprocess

try:
    out = subprocess.check_output(["vm_stat"], text=True, stderr=subprocess.DEVNULL)
except Exception:
    print(0)
    raise SystemExit(0)

m = re.search(r"page size of (\d+) bytes", out)
page_size = int(m.group(1)) if m else 4096

pages = {
    "Pages free": 0,
    "Pages inactive": 0,
    "Pages speculative": 0,
}

for raw in out.splitlines():
    line = raw.strip()
    m = re.match(r"^([^:]+):\s*([0-9][0-9,]*)\.?$", line)
    if not m:
        continue
    key = m.group(1)
    if key in pages:
        pages[key] = int(m.group(2).replace(",", ""))

available_pages = pages["Pages free"] + pages["Pages inactive"] + pages["Pages speculative"]
print(max(0, (available_pages * page_size) // 1024))
PY
}

get_process_physical_footprint_kb() {
  local pid="$1"
  python3 - "${pid}" <<'PY'
import re
import subprocess
import sys

pid = str(sys.argv[1]).strip()
if not pid:
    print(0)
    raise SystemExit(0)

try:
    out = subprocess.check_output(["vmmap", "-summary", pid], text=True, stderr=subprocess.DEVNULL)
except Exception:
    print(0)
    raise SystemExit(0)

m = re.search(r"Physical footprint:\s*([0-9]+(?:\.[0-9]+)?)\s*([KMGT]?)[Bb]?", out)
if not m:
    print(0)
    raise SystemExit(0)

value = float(m.group(1))
unit = (m.group(2) or "K").upper()
scale = {
    "": 1,
    "K": 1,
    "M": 1024,
    "G": 1024 * 1024,
    "T": 1024 * 1024 * 1024,
}.get(unit, 1)
print(max(0, int(value * scale)))
PY
}

write_calibration_memory_metrics() {
  local out_csv="$1"
  {
    echo "metric,mb"
    echo "peak_rss_mb,${PEAK_RSS_MB}"
    echo "peak_physical_footprint_mb,${PEAK_FOOTPRINT_MB}"
    echo "peak_system_delta_mb,${PEAK_SYS_DELTA_MB}"
    echo "peak_effective_mb,${PEAK_EFFECTIVE_MB}"
    echo "configured_safe_mb,${CONFIG_SAFE_MB:-}"
    echo "system_available_mb,${SYSTEM_AVAILABLE_MB:-}"
    echo "mps_live_budget_mb,${MPS_LIVE_BUDGET_MB:-}"
    echo "mps_memory_reserve_gb,${MPS_MEMORY_RESERVE_GB:-}"
  } > "${out_csv}"
}

generate_random_binder_seq() {
  local min_len="$1"
  local max_len="$2"
  local percent_x="$3"
  local helix_kill="$4"
  local neg_helix_constant="$5"
  local loop_kill="${6:-0}"
  local predictor="${7:-}"
  local random_seed="${8:-}"
  python3 - "$min_len" "$max_len" "$percent_x" "$helix_kill" "$neg_helix_constant" "$loop_kill" "$predictor" "$random_seed" <<'PY'
import sys, random
min_len, max_len, pct_x, helix_kill, neg_helix_constant, loop_kill, predictor, random_seed = sys.argv[1:9]
min_len = int(min_len); max_len = int(max_len)
pct_x = float(pct_x); helix_kill = int(helix_kill)
neg_helix_constant = max(0.0, min(1.0, float(neg_helix_constant)))
loop_kill = max(0.0, min(1.0, float(loop_kill)))
if max_len < min_len:
    raise SystemExit("binder-max-len must be >= binder-min-len")
seed = int(random_seed) if random_seed else None
rng = random.Random(seed)
# Unsupported X positions receive deterministic predictor-compatible spikes,
# but spike draws must not perturb the paired latent sequence used by models
# that accept X/UNK.
spike_rng = random.Random(None if seed is None else seed + 1_000_000_007)
L = rng.randint(min_len, max_len)
p_x = max(0.0, min(1.0, pct_x / 100.0))
n_x = max(0, min(L, int(round(L * p_x))))
AA_POOL = list("ADEFGHIKLMNPQRSTVWY")
HELIX_PRONE = set("AEKLMQ")
# Tuned so 0.5 reproduces approximately previous defaults:
# - global helix-prone downweight ~0.55
# - local i-4 helix suppression ~0.15
base_helix_penalty = max(0.10, 1.0 - 0.90 * neg_helix_constant)
local_helix_penalty = max(0.02, 1.0 - 1.70 * neg_helix_constant)
ser_boost = 1.0 + 1.0 * neg_helix_constant
proline_scale = max(0.0, 1.0 - loop_kill)

base_weights = []
for aa in AA_POOL:
    w = 1.0
    if helix_kill and aa in HELIX_PRONE:
        w *= base_helix_penalty
    if helix_kill and aa == "S":
        w *= ser_boost
    if aa == "P":
        w *= proline_scale
    base_weights.append(w)
seq = [None] * L
idx = list(range(L)); rng.shuffle(idx)
x_positions = set(idx[:n_x])
of3_spike_pool = list("ANGHFSY")
for i in range(L):
    if i in x_positions:
        if predictor == "openfold-3-mlx":
            seq[i] = spike_rng.choice(of3_spike_pool)
        else:
            seq[i] = "X"
        continue
    if not helix_kill:
        seq[i] = rng.choices(AA_POOL, weights=base_weights, k=1)[0]
        continue
    w = base_weights[:]
    if i >= 4 and seq[i-4] in HELIX_PRONE:
        for j, aa in enumerate(AA_POOL):
            if aa in HELIX_PRONE:
                w[j] *= local_helix_penalty
    seq[i] = rng.choices(AA_POOL, weights=w, k=1)[0]
print("".join(seq))
PY
}

generate_partial_redesign_seed_seq() {
  local base_seq="$1"
  local ranges_csv="$2"
  local percent_x="$3"
  local helix_kill="$4"
  local neg_helix_constant="$5"
  local loop_kill="${6:-0}"
  local predictor="${7:-}"
  local random_seed="${8:-}"

  local seq_len seeded_random
  seq_len="${#base_seq}"
  seeded_random="$(generate_random_binder_seq "${seq_len}" "${seq_len}" "${percent_x}" "${helix_kill}" "${neg_helix_constant}" "${loop_kill}" "${predictor}" "${random_seed}")"

  python3 - "${base_seq}" "${seeded_random}" "${ranges_csv}" <<'PY'
import re
import sys

base_seq, seeded_seq, ranges_raw = sys.argv[1:4]

if len(base_seq) != len(seeded_seq):
    raise SystemExit("Internal error: partial redesign seed length mismatch.")

tokens = [t.strip() for t in re.split(r"[;,]", ranges_raw) if t.strip()]
if not tokens:
    raise SystemExit("Internal error: no ranges provided to partial redesign seeding.")

out = list(base_seq)
L = len(out)
for tok in tokens:
    if "-" not in tok:
        raise SystemExit(f"Internal error: invalid range '{tok}'.")
    a, b = tok.split("-", 1)
    start = int(a.strip())
    end = int(b.strip())
    if start < 1 or end < 1 or start > end or end > L:
        raise SystemExit(f"Internal error: range '{tok}' out of bounds for length {L}.")
    out[start - 1 : end] = list(seeded_seq[start - 1 : end])

print("".join(out))
PY
}

generate_nanobody_seed_seq() {
  local base_seq="$1"
  local regions="$2"
  local seed="$3"
  local report_json="$4"
  local catalog_tsv="${REPO_ROOT}/examples/nanobody_scaffolds/catalog.tsv"

  python3 - \
    "${base_seq}" \
    "${regions}" \
    "${seed}" \
    "${report_json}" \
    "${catalog_tsv}" \
    "${NANOBODY_SEED_CDR_RANGES}" \
    "${NANOBODY_SEED_MAX_ATTEMPTS}" \
    "${NANOBODY_ALLOW_CDR_CYS}" \
    "${NANOBODY_CHARGE_MIN}" \
    "${NANOBODY_CHARGE_MAX}" \
    "${NANOBODY_HYDRO_MAX}" \
    "${NANOBODY_USE_SOFT_FILTERS}" \
    "${NANOBODY_SEED_PERCENT_X}" <<'PY'
import csv
import json
import random
import re
import sys
from pathlib import Path

(
    base_seq,
    regions_raw,
    seed_raw,
    report_json,
    catalog_tsv,
    ranges_raw,
    max_attempts_raw,
    allow_cys_raw,
    charge_min_raw,
    charge_max_raw,
    hydro_max_raw,
    use_soft_raw,
    seed_percent_x_raw,
) = sys.argv[1:14]

base_seq = re.sub(r"[^A-Za-z]", "", base_seq).upper()
if not base_seq:
    raise SystemExit("Template nanobody scaffold sequence is empty.")

rng = random.Random(int(seed_raw))
max_attempts = int(max_attempts_raw)
allow_cys = bool(int(allow_cys_raw))
charge_min = float(charge_min_raw)
charge_max = float(charge_max_raw)
hydro_max = float(hydro_max_raw)
use_soft = bool(int(use_soft_raw))
seed_percent_x = max(0.0, min(100.0, float(seed_percent_x_raw)))

DEFAULT_RANGES = {
    "CDR1": (27, 38),
    "CDR2": (56, 65),
    "CDR3": (105, 117),
}


def expand_regions(raw):
    tokens = [t.strip().upper() for t in re.split(r"[\s,;]+", raw or "") if t.strip()]
    if not tokens:
        raise SystemExit("No CDR regions provided for nanobody seed generation.")
    out = []
    for tok in tokens:
        tok = {"CDRH1": "CDR1", "CDRH2": "CDR2", "CDRH3": "CDR3"}.get(tok, tok)
        if tok in {"ALL", "ALLH", "CDRH"}:
            out.extend(["CDR1", "CDR2", "CDR3"])
        elif tok in {"CDR1", "CDR2", "CDR3"}:
            out.append(tok)
        else:
            raise SystemExit(f"Unsupported nanobody seed CDR region: {tok}")
    deduped = []
    for region in ["CDR1", "CDR2", "CDR3"]:
        if region in out:
            deduped.append(region)
    return deduped


def parse_range_value(value):
    m = re.match(r"^\s*(\d+)\s*(?:-|\.\.)\s*(\d+)\s*$", value or "")
    if not m:
        raise ValueError(value)
    start, end = int(m.group(1)), int(m.group(2))
    if start < 1 or end < start:
        raise ValueError(value)
    return start, end


def load_catalog_ranges():
    path = Path(catalog_tsv)
    if not path.exists():
        return {}
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            seq = re.sub(r"[^A-Za-z]", "", row.get("sequence", "")).upper()
            if seq != base_seq:
                continue
            try:
                return {
                    "CDR1": parse_range_value(row.get("cdr1_range_1based", "")),
                    "CDR2": parse_range_value(row.get("cdr2_range_1based", "")),
                    "CDR3": parse_range_value(row.get("cdr3_range_1based", "")),
                }
            except ValueError as exc:
                raise SystemExit(f"Invalid scaffold catalog CDR range: {exc}")
    return {}


def parse_override_ranges():
    raw = (ranges_raw or "").strip()
    if not raw or raw.lower() in {"auto", "none", "null"}:
        return {}
    out = {}
    matches = list(
        re.finditer(
            r"\b(CDR[123]|CDRH[123])\b\s*[:=]\s*(\d+)\s*(?:-|\.\.)\s*(\d+)",
            raw,
            flags=re.I,
        )
    )
    if not matches:
        raise SystemExit(
            "--nanobody-seed-cdr-ranges must look like CDR1:26-33,CDR2:51-57,CDR3:97-110"
        )
    for match in matches:
        region = match.group(1).upper().replace("CDRH", "CDR")
        start, end = int(match.group(2)), int(match.group(3))
        if start < 1 or end < start:
            raise SystemExit(f"Invalid {region} seed CDR range: {start}-{end}")
        out[region] = (start, end)
    return out


regions = expand_regions(regions_raw)
range_source = "generic_vhh_default"
ranges = dict(DEFAULT_RANGES)
catalog_ranges = load_catalog_ranges()
if catalog_ranges:
    ranges.update(catalog_ranges)
    range_source = "nanobody_scaffold_catalog"
override_ranges = parse_override_ranges()
if override_ranges:
    ranges.update(override_ranges)
    range_source = "cli_override"

seq_len = len(base_seq)
for region in regions:
    start, end = ranges[region]
    if end > seq_len:
        raise SystemExit(
            f"{region} seed range {start}-{end} exceeds scaffold length {seq_len}. "
            "Use --nanobody-seed-cdr-ranges for this scaffold."
        )

positions = []
for region in regions:
    start, end = ranges[region]
    positions.extend(range(start - 1, end))
positions = sorted(set(positions))
if not positions:
    raise SystemExit("No positions selected for nanobody seed randomization.")

AA_POOL = list("ACDEFGHIKLMNPQRSTVWY") if allow_cys else list("ADEFGHIKLMNPQRSTVWY")
BASE_WEIGHTS = {
    "A": 0.70,
    "C": 0.10,
    "D": 0.80,
    "E": 0.80,
    "F": 0.55,
    "G": 1.10,
    "H": 0.45,
    "I": 0.45,
    "K": 0.80,
    "L": 0.55,
    "M": 0.25,
    "N": 1.00,
    "P": 0.55,
    "Q": 0.90,
    "R": 0.75,
    "S": 1.25,
    "T": 1.00,
    "V": 0.55,
    "W": 0.25,
    "Y": 1.05,
}
WEIGHTS = [BASE_WEIGHTS[aa] for aa in AA_POOL]
HYDROPHOBIC = set("AVILMFWY")


def region_sequence(seq, region):
    start, end = ranges[region]
    return seq[start - 1 : end]


def designed_residues(seq):
    return "".join(seq[i] for i in positions)


def hard_filter_reasons(seq):
    reasons = []
    designed = designed_residues(seq)
    if not allow_cys and "C" in designed:
        reasons.append("cysteine_in_randomized_cdr")
    if re.search(r"N[^P][ST]", seq):
        reasons.append("n_x_s_t_glycosylation_motif")
    if re.search(r"([A-Z])\1{3,}", seq):
        reasons.append("homopolymer_ge_4")
    if re.search(r"G{4,}", seq):
        reasons.append("consecutive_glycine_gt_3")
    if re.search(r"P{3,}", seq):
        reasons.append("consecutive_proline_gt_2")
    return reasons


def soft_metrics(seq):
    designed = designed_residues(seq)
    charge = 0.0
    for aa in designed:
        if aa in {"K", "R"}:
            charge += 1.0
        elif aa == "H":
            charge += 0.1
        elif aa in {"D", "E"}:
            charge -= 1.0
    hydrophobic_fraction = (
        sum(1 for aa in designed if aa in HYDROPHOBIC) / max(1, len(designed))
    )
    charge_penalty = max(0.0, charge_min - charge, charge - charge_max)
    hydro_penalty = max(0.0, hydrophobic_fraction - hydro_max)
    penalty = charge_penalty + hydro_penalty
    return charge, hydrophobic_fraction, penalty


def make_candidate():
    seq = list(base_seq)
    for idx in positions:
        seq[idx] = rng.choices(AA_POOL, weights=WEIGHTS, k=1)[0]
    return "".join(seq)


def apply_x_mask(seq):
    masked = list(seq)
    n_x = int(round(len(positions) * seed_percent_x / 100.0))
    n_x = max(0, min(len(positions), n_x))
    x_positions = sorted(rng.sample(positions, n_x)) if n_x else []
    for idx in x_positions:
        masked[idx] = "X"
    return "".join(masked), x_positions


best = None
selected = None
attempts_used = 0
for attempt in range(1, max_attempts + 1):
    attempts_used = attempt
    candidate = make_candidate()
    reasons = hard_filter_reasons(candidate)
    if reasons:
        continue
    charge, hydro, penalty = soft_metrics(candidate)
    record = {
        "sequence": candidate,
        "charge": charge,
        "hydrophobic_fraction": hydro,
        "penalty": penalty,
        "attempt": attempt,
    }
    if not use_soft or penalty <= 1e-12:
        selected = record
        selected["selected_by"] = "hard_filters_only" if not use_soft else "hard_and_soft_filters"
        break
    if best is None or penalty < best["penalty"]:
        best = record

if selected is None and best is not None:
    selected = best
    selected["selected_by"] = "best_hard_filter_candidate_soft_fallback"

if selected is None:
    raise SystemExit(
        "Could not generate a nanobody CDR seed passing hard filters. "
        "Increase --nanobody-seed-max-attempts or adjust CDR ranges."
    )

resolved_seq = selected["sequence"]
emitted_seq, x_positions = apply_x_mask(resolved_seq)
charge = selected["charge"]
hydro = selected["hydrophobic_fraction"]
penalty = selected["penalty"]
hard_pass = not hard_filter_reasons(resolved_seq)
soft_pass = penalty <= 1e-12

if use_soft and not soft_pass:
    print(
        "WARNING: nanobody seed used the best hard-filtered candidate but did not meet "
        "charge/hydrophobic soft targets.",
        file=sys.stderr,
    )

def masked_region_sequence(seq, region):
    start, end = ranges[region]
    return seq[start - 1 : end]


report = {
    "mode": "cdr-random",
    "regions": regions,
    "range_source": range_source,
    "region_ranges_1based": {region: f"{ranges[region][0]}-{ranges[region][1]}" for region in regions},
    "resolved_region_sequences": {region: region_sequence(resolved_seq, region) for region in regions},
    "emitted_region_sequences": {region: masked_region_sequence(emitted_seq, region) for region in regions},
    "region_sequences": {region: masked_region_sequence(emitted_seq, region) for region in regions},
    "resolved_designed_sequence": designed_residues(resolved_seq),
    "emitted_designed_sequence": designed_residues(emitted_seq),
    "designed_sequence": designed_residues(emitted_seq),
    "full_sequence": emitted_seq,
    "resolved_full_sequence": resolved_seq,
    "x_mask_percent": seed_percent_x,
    "x_mask_positions_1based": [idx + 1 for idx in x_positions],
    "seed": int(seed_raw),
    "attempts_used": attempts_used,
    "max_attempts": max_attempts,
    "hard_filter_pass": hard_pass,
    "soft_filter_pass": soft_pass,
    "selected_by": selected["selected_by"],
    "net_charge_randomized_cdrs": round(charge, 3),
    "hydrophobic_fraction_randomized_cdrs": round(hydro, 3),
    "constraints": {
        "no_cysteine_in_randomized_cdrs": not allow_cys,
        "no_n_x_s_t_glycosylation_motif_full_sequence": True,
        "no_homopolymers_ge_4_full_sequence": True,
        "no_consecutive_glycines_gt_3_full_sequence": True,
        "no_consecutive_prolines_gt_2_full_sequence": True,
        "fixed_scaffold_cdr_lengths": True,
        "developability_filters_evaluated_on_resolved_sequence_before_x_masking": True,
        "antifold_receives_predicted_structure_after_unk_patch_not_raw_x_sequence": True,
        "soft_charge_min": charge_min if use_soft else None,
        "soft_charge_max": charge_max if use_soft else None,
        "soft_hydrophobic_fraction_max": hydro_max if use_soft else None,
    },
}

Path(report_json).parent.mkdir(parents=True, exist_ok=True)
with Path(report_json).open("w") as handle:
    json.dump(report, handle, indent=2, sort_keys=True)
    handle.write("\n")

print(emitted_seq)
PY
}

generate_motif_scaffold_bundle() {
  local min_len="$1"
  local max_len="$2"
  python3 "${MOTIF_HELPER}" generate \
    --motif-positions "${MOTIF_POSITIONS}" \
    --source-sequence "${MOTIF_SOURCE_SEQ}" \
    --motif-fixed-positions "${MOTIF_FIXED_POSITIONS}" \
    --gap-between-motifs "${MOTIF_GAP_BETWEEN}" \
    --min-length "${min_len}" \
    --max-length "${max_len}"
}

compute_loopkill_mpnn_bias() {
  local base_bias="${1:-}"
  local loop_kill="${2:-0}"
  python3 - "$base_bias" "$loop_kill" <<'PY'
import sys
base = sys.argv[1].strip()
lk = max(0.0, min(1.0, float(sys.argv[2])))
if lk <= 0.0:
    print(base)
    raise SystemExit(0)
if lk >= 1.0:
    # loopkill=1 uses omit_AA to remove proline entirely.
    print(base)
    raise SystemExit(0)
bias_p = -0.1 - 1.9 * lk
if base:
    print(f"{base},P:{bias_p:.6f}")
else:
    print(f"P:{bias_p:.6f}")
PY
}

make_yaml_with_binder_sequence() {
  local template_yaml="$1"
  local out_yaml="$2"
  local new_seq="$3"
  local target_msa_path="${4:-}"
  local predictor="${5:-}"
  local binder_msa_path="${6:-}"
  local phase="${7:-design}"
  local catalog_tsv="${REPO_ROOT}/examples/nanobody_scaffolds/catalog.tsv"
  python3 - \
    "$template_yaml" \
    "$out_yaml" \
    "$new_seq" \
    "$target_msa_path" \
    "$predictor" \
    "$TARGET_EPITOPE_RESIDUES" \
    "$BOLTZ_CONTACT_DISTANCE" \
    "$BOLTZ_CONTACT_FORCE" \
    "$BOLTZ_CONTACT_MODE" \
    "$NANOBODY_SEED_CDR_RANGES" \
    "$catalog_tsv" \
    "$binder_msa_path" \
    "$phase" \
    "${TARGET_MSA_MANIFEST:-}" <<'PY'
import csv
import re
import sys
from pathlib import Path

(
    template,
    out,
    new_seq,
    msa_path,
    predictor,
    epitope_raw,
    contact_distance_raw,
    contact_force_raw,
    contact_mode_raw,
    cdr_ranges_raw,
    catalog_tsv,
    binder_msa_path,
    phase,
    target_msa_manifest,
) = sys.argv[1:15]
msa_path = msa_path or None
binder_msa_path = binder_msa_path or None
contact_distance = float(contact_distance_raw)
contact_force = bool(int(contact_force_raw))
contact_mode = (contact_mode_raw or "auto").strip().lower()

in_binder = False
in_protein = False
desired_msa_value = None
skip_existing_msa = False
cur = None
original_binder_seq = ""
out_lines = []
skip_nanohunter_block = False

target_msa_by_chain = {}
if target_msa_manifest:
    manifest = Path(target_msa_manifest)
    if not manifest.is_file():
        raise SystemExit(f"Target MSA manifest is missing: {manifest}")
    for line in manifest.read_text().splitlines():
        if not line.strip():
            continue
        fields = line.split("\t", 1)
        if len(fields) != 2 or not fields[0] or not fields[1]:
            raise SystemExit(f"Invalid target MSA manifest row: {line!r}")
        target_msa_by_chain[fields[0]] = fields[1]


def parse_range_value(value):
    m = re.match(r"^\s*(\d+)\s*(?:-|\.\.)\s*(\d+)\s*$", value or "")
    if not m:
        raise ValueError(value)
    start, end = int(m.group(1)), int(m.group(2))
    if start < 1 or end < start:
        raise ValueError(value)
    return start, end


def parse_override_cdr3_range(raw):
    raw = (raw or "").strip()
    if not raw or raw.lower() in {"auto", "none", "null"}:
        return None
    matches = list(
        re.finditer(
            r"\b(CDR3|CDRH3)\b\s*[:=]\s*(\d+)\s*(?:-|\.\.)\s*(\d+)",
            raw,
            flags=re.I,
        )
    )
    if not matches:
        return None
    return int(matches[-1].group(2)), int(matches[-1].group(3))


def infer_cdr3_range(base_seq, current_seq):
    override = parse_override_cdr3_range(cdr_ranges_raw)
    if override:
        return override
    base_seq = re.sub(r"[^A-Za-z]", "", base_seq or "").upper()
    current_seq = re.sub(r"[^A-Za-z]", "", current_seq or "").upper()
    path = Path(catalog_tsv)
    if path.exists() and base_seq:
        with path.open(newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            for row in reader:
                seq = re.sub(r"[^A-Za-z]", "", row.get("sequence", "")).upper()
                if seq == base_seq:
                    return parse_range_value(row.get("cdr3_range_1based", ""))
    # Generic IMGT-like fallback for uncatalogued VHHs.
    if len(current_seq) >= 117:
        return 105, 117
    raise SystemExit(
        "Could not infer CDR3 range for Boltz CDR3 contacts. "
        "Use --nanobody-seed-cdr-ranges with CDR3:start-end."
    )


def parse_epitope_residues(raw):
    contacts = []
    for tok in re.split(r"[\s,;]+", raw or ""):
        tok = tok.strip()
        if not tok:
            continue
        if ":" in tok:
            m = re.match(r"^([A-Za-z0-9]+)\s*:\s*(\d+)$", tok)
        else:
            m = re.match(r"^([A-Za-z]+)(\d+)$", tok)
        if not m:
            raise SystemExit(
                f"Invalid epitope residue '{tok}'. Use forms like B6 or B:6."
            )
        contacts.append((m.group(1), int(m.group(2))))
    return contacts


def middle_cdr3_pairs(cdr3_start, cdr3_end, contacts):
    if not contacts:
        return []
    # For even-length CDR3s, use the lower central residue. For 7XL0 CDR3
    # 97-110 this is A103, which keeps CDR3 contact bias relaxed and local.
    middle_pos = (cdr3_start + cdr3_end) // 2
    return [(middle_pos, contact) for contact in contacts]


def format_bool(value):
    return "true" if value else "false"


def build_dynamic_constraints():
    if predictor != "boltz" or phase != "design":
        return []
    contacts = parse_epitope_residues(epitope_raw)
    if not contacts:
        return []
    mode = contact_mode
    if mode == "auto":
        mode = "pocket+cdr3"
    if mode == "none":
        return []

    lines = ["  # NanoHunter dynamic epitope constraints\n"]
    contact_list = ", ".join(f"[{chain}, {pos}]" for chain, pos in contacts)
    if mode in {"pocket", "pocket+cdr3", "cdr3+pocket"}:
        lines.extend(
            [
                "  - pocket:\n",
                "      binder: A\n",
                f"      contacts: [{contact_list}]\n",
                f"      max_distance: {contact_distance:g}\n",
                f"      force: {format_bool(contact_force)}\n",
            ]
        )
    if mode in {"cdr3", "pocket+cdr3", "cdr3+pocket"}:
        cdr3_start, cdr3_end = infer_cdr3_range(original_binder_seq, new_seq)
        if cdr3_end > len(new_seq):
            raise SystemExit(
                f"CDR3 contact range {cdr3_start}-{cdr3_end} exceeds binder sequence length {len(new_seq)}."
            )
        for binder_pos, (target_chain, target_pos) in middle_cdr3_pairs(
            cdr3_start, cdr3_end, contacts
        ):
            lines.extend(
                [
                    "  - contact:\n",
                    f"      token1: [A, {binder_pos}]\n",
                    f"      token2: [{target_chain}, {target_pos}]\n",
                    f"      max_distance: {contact_distance:g}\n",
                    f"      force: {format_bool(contact_force)}\n",
                ]
            )
    return lines


def desired_msa_for_chain(chain_id):
    if chain_id == "A":
        return binder_msa_path
    if chain_id in target_msa_by_chain:
        return target_msa_by_chain[chain_id]
    if msa_path is not None:
        return msa_path
    # Boltz cannot mix custom and auto-generated MSAs. If chain A has a custom
    # scaffold MSA but the target chain has no reusable MSA, force target chains
    # into explicit single-sequence mode instead of leaving them as auto.
    if binder_msa_path is not None and predictor == "boltz":
        return "empty"
    return None


def emit_msa_after_sequence(indent):
    global desired_msa_value, skip_existing_msa
    if desired_msa_value is None:
        return []
    value = desired_msa_value
    desired_msa_value = None
    skip_existing_msa = True
    return [f"{indent}msa: {value}\n"]


for line in Path(template).read_text().splitlines(keepends=True):
    stripped = line.strip()

    if skip_nanohunter_block:
        if stripped and not line.startswith((" ", "\t")):
            skip_nanohunter_block = False
        else:
            continue

    if stripped in {"nanohunter:", "nano_hunter:", "NanoHunter:"} and not line.startswith((" ", "\t")):
        # The constraint adapter consumes this pocket metadata during design.
        # Post-checks and other predictors remain explicitly unconstrained.
        if predictor == "protenix-constraint-v0.5" and phase == "design":
            out_lines.append(line)
        else:
            skip_nanohunter_block = True
        continue

    if stripped.startswith("- protein:"):
        in_protein = True
        in_binder = False
        desired_msa_value = None
        skip_existing_msa = False
        cur = None
        out_lines.append(line)
        continue

    if in_protein and stripped.startswith("- ") and not stripped.startswith("- protein:"):
        in_protein = False
        in_binder = False
        desired_msa_value = None
        skip_existing_msa = False
        cur = None
        out_lines.append(line)
        continue

    if in_protein and stripped.startswith("id:"):
        cid = stripped.split("id:", 1)[1].strip().strip("'\"")
        cur = cid
        in_binder = cid == "A"
        desired_msa_value = desired_msa_for_chain(cid)
        skip_existing_msa = desired_msa_value is not None
        out_lines.append(line)
        continue

    if in_protein and stripped.startswith("msa:"):
        if desired_msa_value is not None:
            indent = line.split("msa:")[0]
            out_lines.append(f"{indent}msa: {desired_msa_value}\n")
            desired_msa_value = None
            skip_existing_msa = True
            continue
        if skip_existing_msa:
            continue

    if in_binder and stripped.startswith("sequence:"):
        original_binder_seq = stripped.split("sequence:", 1)[1].strip().strip("'\"")
        indent = line.split("sequence:")[0]
        out_lines.append(f"{indent}sequence: {new_seq}\n")
        out_lines.extend(emit_msa_after_sequence(indent))
        continue

    if in_protein and desired_msa_value is not None and stripped.startswith("sequence:"):
        out_lines.append(line)
        indent = line.split("sequence:")[0]
        out_lines.extend(emit_msa_after_sequence(indent))
        continue

    out_lines.append(line)


def remove_top_level_block(lines, block_name):
    """Remove one top-level YAML mapping and all of its indented children."""
    kept = []
    skipping = False
    for line in lines:
        stripped = line.strip()
        is_top_level = bool(stripped) and not line.startswith((" ", "\t"))
        if is_top_level and stripped == f"{block_name}:":
            skipping = True
            continue
        if skipping:
            if is_top_level:
                skipping = False
            else:
                continue
        kept.append(line)
    return kept


# Boltz restraints are a design-time steering mechanism. Other predictors do
# not consume Boltz's constraints or affinity-property schema, and
# post-prediction should score the resulting sequence without the restraints
# that generated it.
if predictor != "boltz" or phase != "design":
    out_lines = remove_top_level_block(out_lines, "constraints")
if predictor != "boltz":
    out_lines = remove_top_level_block(out_lines, "properties")

dynamic_constraints = build_dynamic_constraints()
if dynamic_constraints:
    constraints_idx = None
    for i, line in enumerate(out_lines):
        if line.strip() == "constraints:" and not line.startswith((" ", "\t")):
            constraints_idx = i
            break
    if constraints_idx is not None:
        insert_at = len(out_lines)
        for i in range(constraints_idx + 1, len(out_lines)):
            stripped = out_lines[i].strip()
            if stripped and not out_lines[i].startswith((" ", "\t")):
                insert_at = i
                break
        out_lines[insert_at:insert_at] = dynamic_constraints
    else:
        insert_at = len(out_lines)
        for i, line in enumerate(out_lines):
            if line.strip().startswith("version:") and not line.startswith((" ", "\t")):
                insert_at = i
                break
        block = ["constraints:\n", *dynamic_constraints]
        out_lines[insert_at:insert_at] = block

Path(out).write_text("".join(out_lines))
PY
}

extract_binder_sequence_from_yaml() {
  local template_yaml="$1"
  local chain_id="${2:-A}"
  python3 - "$template_yaml" "$chain_id" <<'PY'
import sys
path, wanted = sys.argv[1:3]
cur = None
seqs = {}
in_protein = False
for raw in open(path):
    s = raw.strip()
    if s.startswith("- protein:"):
        in_protein = True
        cur = None
        continue
    if not in_protein:
        continue
    if s.startswith("-") and not s.startswith("- protein:"):
        in_protein = False
        continue
    if s.startswith("id:"):
        cur = s.split("id:", 1)[1].strip().strip("'\"")
        continue
    if s.startswith("sequence:") and cur:
        seqs[cur] = s.split("sequence:", 1)[1].strip().strip("'\"")
seq = (seqs.get(wanted, "") or "").strip()
if seq.lower() in {"empty", "none", "null"}:
    seq = ""
print(seq)
PY
}

extract_target_sequence_from_yaml() {
  local template_yaml="$1"
  python3 - "$template_yaml" <<'PY'
import sys
path = sys.argv[1]
cur=None
seqs={}
in_protein=False
for raw in open(path):
    s=raw.strip()
    if s.startswith("- protein:"):
        in_protein=True
        cur=None
        continue
    if not in_protein:
        continue
    if s.startswith("-") and not s.startswith("- protein:"):
        in_protein=False
        continue
    if s.startswith("id:"):
        cur=s.split(":",1)[1].strip().strip("'\"")
        continue
    if s.startswith("sequence:") and cur:
        seq=s.split(":",1)[1].strip().strip("'\"")
        seqs[cur]=seq
if "B" in seqs and seqs["B"]:
    print(seqs["B"])
else:
    for cid in sorted(seqs):
        if cid != "A" and seqs[cid]:
            print(seqs[cid])
            break
PY
}

extract_target_chains_from_yaml() {
  local template_yaml="$1"
  python3 - "$template_yaml" <<'PY'
import sys

path = sys.argv[1]
records = []
current = None
in_protein = False
for raw in open(path):
    value = raw.strip()
    if value.startswith("- protein:"):
        if current:
            records.append(current)
        current = {"id": "", "sequence": "", "msa": ""}
        in_protein = True
        continue
    if in_protein and value.startswith("- "):
        if current:
            records.append(current)
        current = None
        in_protein = False
        continue
    if not in_protein or current is None:
        continue
    for key in ("id", "sequence", "msa"):
        prefix = f"{key}:"
        if value.startswith(prefix):
            current[key] = value.split(":", 1)[1].strip().strip("'\"")
            break
if current:
    records.append(current)

seen = set()
for record in records:
    chain = record["id"]
    sequence = "".join(record["sequence"].split()).upper()
    if not chain or chain == "A":
        continue
    if len(chain) != 1 or not chain.isalpha() or chain in seen:
        raise SystemExit(f"Target protein chain IDs must be unique letters; got {chain!r}.")
    if not sequence or any(residue not in "ACDEFGHIKLMNPQRSTVWYXBZJUO" for residue in sequence):
        raise SystemExit(f"Target chain {chain} has an empty or invalid sequence.")
    seen.add(chain)
    print(f"{chain}\t{sequence}\t{record['msa'] or 'auto'}")
PY
}

extract_target_msa_from_yaml() {
  local template_yaml="$1"
  local target_chain="${2:-}"
  python3 - "$template_yaml" "$target_chain" <<'PY'
import sys
path, wanted = sys.argv[1:3]
cur=None
in_protein=False
for raw in open(path):
    s=raw.strip()
    if s.startswith("- protein:"):
        in_protein=True
        cur=None
        continue
    if not in_protein:
        continue
    if s.startswith("-") and not s.startswith("- protein:"):
        in_protein=False
        continue
    if s.startswith("id:"):
        cur=s.split(":",1)[1].strip().strip("'\"")
        continue
    if s.startswith("msa:") and cur and cur != "A" and (not wanted or cur == wanted):
        val=s.split(":",1)[1].strip().strip("'\"")
        low=val.lower()
        if val and low not in {"empty", "none", "null"}:
            print(val)
            break
PY
}

extract_chain_msa_from_yaml() {
  local template_yaml="$1"
  local chain_id="$2"
  python3 - "$template_yaml" "$chain_id" <<'PY'
import sys

path, wanted = sys.argv[1:3]
cur = None
in_protein = False
for raw in open(path):
    stripped = raw.strip()
    if stripped.startswith("- protein:"):
        in_protein = True
        cur = None
        continue
    if not in_protein:
        continue
    if stripped.startswith("-") and not stripped.startswith("- protein:"):
        in_protein = False
        cur = None
        continue
    if stripped.startswith("id:"):
        cur = stripped.split(":", 1)[1].strip().strip("'\"")
        continue
    if stripped.startswith("msa:") and cur == wanted:
        value = stripped.split(":", 1)[1].strip().strip("'\"")
        if value and value.lower() not in {"empty", "none", "null"}:
            print(value)
        break
PY
}

template_has_boltz_partner() {
  local template_yaml="$1"
  python3 - "$template_yaml" <<'PY'
import sys
path = sys.argv[1]

kind = None
in_entry = False
has_partner = False

for raw in open(path):
    s = raw.strip()
    if s.startswith("- protein:"):
        kind = "protein"
        in_entry = True
        continue
    if s.startswith("- ligand:"):
        # For binder-vs-ligand cases, ligand is the partner.
        print("1")
        raise SystemExit(0)

    if in_entry and s.startswith("id:"):
        cid = s.split(":", 1)[1].strip().strip("'\"")
        if kind == "protein" and cid and cid != "A":
            has_partner = True
        continue

    if in_entry and s.startswith("- ") and not (s.startswith("- protein:") or s.startswith("- ligand:")):
        in_entry = False

print("1" if has_partner else "0")
PY
}

template_has_small_molecule_ligand() {
  local template_yaml="$1"
  python3 - "$template_yaml" <<'PY'
import sys
path = sys.argv[1]
for raw in open(path):
    if raw.strip().startswith("- ligand:"):
        print("1")
        raise SystemExit(0)
print("0")
PY
}

extract_target_chain_id_from_yaml() {
  local template_yaml="$1"
  python3 - "$template_yaml" <<'PY'
import sys
path = sys.argv[1]
cur = None
in_protein = False
for raw in open(path):
    s = raw.strip()
    if s.startswith("- protein:"):
        in_protein = True
        cur = None
        continue
    if not in_protein:
        continue
    if s.startswith("-") and not s.startswith("- protein:"):
        in_protein = False
        continue
    if s.startswith("id:"):
        cid = s.split(":", 1)[1].strip().strip("'\"")
        if cid and cid != "A":
            print(cid)
            break
PY
}

is_openfold_msa_path_compatible() {
  local msa_path="${1:-}"
  [[ -n "${msa_path}" ]] || return 1
  case "${msa_path##*.}" in
    a3m|sto|npz) return 0 ;;
    *) return 1 ;;
  esac
}

sanitize_a3m_file() {
  local in_path="$1"
  [[ -f "${in_path}" ]] || { echo "${in_path}"; return 0; }
  local out_path
  out_path="$(python3 - "${in_path}" <<'PY'
import sys
from pathlib import Path
p = Path(sys.argv[1])
b = p.read_bytes()
if b"\x00" in b:
    out = p.with_name(p.stem + ".sanitized.a3m")
    out.write_bytes(b.replace(b"\x00", b""))
    print(str(out))
else:
    print(str(p))
PY
)"
  echo "${out_path}"
}

resolve_a3m_from_msa_path() {
  local msa_path="${1:-}"
  [[ -n "${msa_path}" ]] || { echo ""; return 0; }
  if [[ "${msa_path##*.}" == "a3m" ]]; then
    sanitize_a3m_file "${msa_path}"
    return 0
  fi
  if [[ "${msa_path##*.}" == "npz" ]]; then
    local root_dir cand
    root_dir="$(cd "$(dirname "${msa_path}")/.." 2>/dev/null && pwd || true)"
    cand=""
    if [[ -n "${root_dir}" && -f "${root_dir}/raw/main/uniref90_hits.a3m" ]]; then
      cand="${root_dir}/raw/main/uniref90_hits.a3m"
    elif [[ -n "${root_dir}" && -f "${root_dir}/raw/main/uniref.a3m" ]]; then
      cand="${root_dir}/raw/main/uniref.a3m"
    elif [[ -n "${root_dir}" ]]; then
      cand="$(find "${root_dir}/raw/main" -maxdepth 1 -type f -name '*.a3m' 2>/dev/null | sort | head -n 1 || true)"
    fi
    if [[ -n "${cand}" ]]; then
      sanitize_a3m_file "${cand}"
      return 0
    fi
  fi
  echo "${msa_path}"
}

pick_target_msa_for_predictor() {
  local msa_path="$1"
  local predictor="$2"

  if [[ -z "${msa_path}" ]]; then
    echo ""
    return 0
  fi
  case "${predictor}" in
    openfold-3-mlx)
      # OpenFold only accepts specific MSA formats (a3m/sto/npz). If we have a
      # dedicated cached path for OpenFold, always prefer it.
      if [[ -n "${OPENFOLD_TARGET_MSA_PATH:-}" ]]; then
        echo "${OPENFOLD_TARGET_MSA_PATH}"
        return 0
      fi
      if is_openfold_msa_path_compatible "${msa_path}"; then
        echo "${msa_path}"
      else
        # Returning empty here avoids passing incompatible files (e.g. Boltz CSV)
        # into OpenFold query JSON as main_msa_file_paths.
        echo ""
      fi
      return 0
      ;;
    boltz|intellifold|protenix-v2|protenix-mini|protenix-constraint-v0.5)
      if [[ "${msa_path##*.}" == "npz" ]]; then
        local a3m_path
        a3m_path="$(resolve_a3m_from_msa_path "${msa_path}")"
        if [[ -n "${a3m_path}" && "${a3m_path##*.}" == "a3m" ]]; then
          echo "${a3m_path}"
          return 0
        fi
        if [[ "${predictor}" == "boltz" && -n "${OPENFOLD_TARGET_MSA_PATH:-}" ]]; then
          a3m_path="$(resolve_a3m_from_msa_path "${OPENFOLD_TARGET_MSA_PATH}")"
          if [[ -n "${a3m_path}" && "${a3m_path##*.}" == "a3m" ]]; then
            echo "${a3m_path}"
            return 0
          fi
        fi
        if [[ "${predictor}" == "boltz" ]]; then
          # Avoid feeding unknown NPZ formats (e.g. IntelliFold internal cache)
          # to Boltz directly; let Boltz resolve MSA itself.
          echo ""
          return 0
        fi
      fi
      if [[ "${msa_path##*.}" == "a3m" ]]; then
        sanitize_a3m_file "${msa_path}"
        return 0
      fi
      ;;
  esac
  echo "${msa_path}"
}

write_single_seq_a3m() {
  local seq="$1"
  local out="$2"
  mkdir -p "$(dirname "$out")"
  {
    echo ">query"
    echo "$seq"
  } > "$out"
}

validate_target_msa_file() {
  local msa_path="$1"
  local target_seq="$2"
  local require_depth="${3:-0}"
  local msa_label="${4:-Target}"
  python3 - "${msa_path}" "${target_seq}" "${require_depth}" "${msa_label}" <<'PY'
import csv
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
target = re.sub(r"[^A-Za-z]", "", sys.argv[2]).upper()
require_depth = sys.argv[3] == "1"
label = sys.argv[4]

if not path.is_file() or path.stat().st_size == 0:
    raise SystemExit(f"{label} MSA is missing or empty: {path}")

suffix = path.suffix.lower()
records = []
if suffix == ".a3m":
    current = []
    for raw in path.read_text(errors="ignore").replace("\x00", "").splitlines():
        if raw.startswith(">"):
            if current:
                records.append("".join(current))
                current = []
        else:
            current.append(raw.strip())
    if current:
        records.append("".join(current))
elif suffix == ".csv":
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        if "sequence" not in (reader.fieldnames or []):
            raise SystemExit(f"{label} MSA CSV lacks a sequence column: {path}")
        records = [(row.get("sequence") or "").strip() for row in reader]
elif suffix in {".npz", ".sto"}:
    # These formats are accepted by OpenFold but are not cheaply depth-checked here.
    print("unknown")
    raise SystemExit(0)
else:
    raise SystemExit(
        f"Unsupported {label.lower()} MSA format {suffix or '<none>'}: {path}. "
        "Use A3M/CSV for Boltz or IntelliFold, or NPZ/STO for OpenFold."
    )

records = [record for record in records if record]
if not records:
    raise SystemExit(f"{label} MSA contains no sequences: {path}")

query = "".join(ch for ch in records[0] if not ch.islower() and ch not in ".-").upper()
if target and query != target:
    raise SystemExit(
        f"{label} MSA query does not match the expected sequence: {path} "
        f"(query length {len(query)}, expected length {len(target)})"
    )
if require_depth and len(records) < 2:
    raise SystemExit(
        f"Required {label.lower()} MSA contains only {len(records)} sequence: {path}"
    )
print(len(records))
PY
}

find_reusable_target_msa() {
  local target_seq="$1"
  local search_roots="$2"
  python3 "${REPO_ROOT}/scripts/find_target_msa.py" \
    --sequence "${target_seq}" --roots "${search_roots}"
}

publish_target_msa_to_shared_cache() {
  local msa_path="$1"
  local target_seq="$2"
  [[ -s "${msa_path}" ]] || return 0
  mkdir -p "${TARGET_MSA_SHARED_CACHE_DIR}"
  local digest destination
  digest="$(python3 - "${target_seq}" <<'PY'
import hashlib
import re
import sys
sequence = re.sub(r"[^A-Za-z]", "", sys.argv[1]).upper()
print(hashlib.sha256(sequence.encode()).hexdigest()[:32])
PY
)"
  destination="${TARGET_MSA_SHARED_CACHE_DIR}/${digest}.a3m"
  if [[ "$(cd "$(dirname "${msa_path}")" && pwd)/$(basename "${msa_path}")" != "$(cd "${TARGET_MSA_SHARED_CACHE_DIR}" && pwd)/$(basename "${destination}")" ]]; then
    cp -f "${msa_path}" "${destination}"
  fi
}

csv_msa_to_a3m() {
  local csv_path="$1"
  local a3m_path="$2"
  python3 - "${csv_path}" "${a3m_path}" <<'PY'
import csv
import re
import sys
from pathlib import Path

csv_path, a3m_path = map(Path, sys.argv[1:3])
a3m_path.parent.mkdir(parents=True, exist_ok=True)

with csv_path.open(newline="") as handle:
    reader = csv.DictReader(handle)
    if not {"sequence", "key"}.issubset(reader.fieldnames or []):
        raise SystemExit(f"Invalid Boltz MSA CSV {csv_path}: expected sequence,key columns.")
    records = []
    for i, row in enumerate(reader):
        seq = (row.get("sequence") or "").strip()
        if not seq:
            continue
        key = str(row.get("key") or f"seq_{i}").strip() or f"seq_{i}"
        key = re.sub(r"[^A-Za-z0-9_.:-]+", "_", key)[:120] or f"seq_{i}"
        records.append((key, seq))

if not records:
    raise SystemExit(f"Boltz MSA CSV {csv_path} did not contain any sequences.")

with a3m_path.open("w") as handle:
    for i, (key, seq) in enumerate(records):
        handle.write(f">{i}_{key}\n{seq}\n")
PY
}

generate_boltz_auto_msa_cache() {
  local seq="$1"
  local chain_id="$2"
  local cache_label="$3"
  local cache_dir="$4"

  local safe_label yaml_path out_dir log_path cached_csv cached_a3m attempts attempt
  safe_label="$(printf '%s' "${cache_label}" | tr -c 'A-Za-z0-9_' '_')"
  cache_dir="${cache_dir}/${safe_label}_boltz"
  yaml_path="${cache_dir}/${safe_label}.yaml"
  out_dir="${cache_dir}/boltz"
  log_path="${cache_dir}/${safe_label}.log"
  cached_csv="${cache_dir}/${safe_label}_full_msa.csv"
  cached_a3m="${cache_dir}/${safe_label}_full_msa.a3m"
  attempts="${NANOHUNTER_AUTO_MSA_RETRIES:-3}"
  mkdir -p "${cache_dir}" "${out_dir}"

  if [[ -s "${cached_a3m}" ]]; then
    echo "${cached_a3m}"
    return 0
  fi
  if [[ -s "${cached_csv}" ]]; then
    csv_msa_to_a3m "${cached_csv}" "${cached_a3m}"
    echo "${cached_a3m}"
    return 0
  fi

  python3 - "${seq}" "${chain_id}" "${yaml_path}" <<'PY'
import sys
from pathlib import Path

seq, chain_id, out_yaml = sys.argv[1:4]
seq = "".join(ch for ch in seq.strip().upper() if ch.isalpha())
if not seq:
    raise SystemExit("Cannot generate Boltz MSA for an empty sequence.")
Path(out_yaml).parent.mkdir(parents=True, exist_ok=True)
Path(out_yaml).write_text(
    "sequences:\n"
    "  - protein:\n"
    f"      id: {chain_id}\n"
    f"      sequence: {seq}\n"
    "version: 1\n"
)
PY

  for attempt in $(seq 1 "${attempts}"); do
    source "${BOLTZ_VENV}/bin/activate"
    set +e
    "${BOLTZ_CLI}" predict "${yaml_path}" \
      --out_dir "${out_dir}" \
      "${BOLTZ_EXTRA_FLAGS[@]}" \
      --override \
      > "${log_path}" 2>&1
    local rc=$?
    set -e
    deactivate || true

    local raw_csv
    raw_csv="$(find "${out_dir}" -type f -path '*/msa/*.csv' | sort | head -n 1 || true)"
    if [[ "${rc}" -eq 0 && -n "${raw_csv}" ]]; then
      cp -f "${raw_csv}" "${cached_csv}"
      csv_msa_to_a3m "${cached_csv}" "${cached_a3m}"
      echo "${cached_a3m}"
      return 0
    fi

    if [[ "${attempt}" -lt "${attempts}" ]]; then
      echo "WARNING: Boltz auto-MSA attempt ${attempt}/${attempts} failed for ${safe_label}; retrying..." >&2
      sleep "$((attempt * 5))"
    fi
  done

  tail -n 120 "${log_path}" >&2 || true
  echo "ERROR: Boltz auto-MSA generation failed for ${safe_label}; no reusable MSA was produced." >&2
  return 1
}

generate_protenix_auto_msa_cache() {
  local seq="$1"
  local chain_id="$2" # retained for the common generator signature
  local cache_label="$3"
  local cache_dir="$4"

  local safe_label cached_a3m work_dir log_path
  safe_label="$(printf '%s' "${cache_label}" | tr -c 'A-Za-z0-9_' '_')"
  cache_dir="${cache_dir}/${safe_label}_protenix"
  cached_a3m="${cache_dir}/${safe_label}_full_msa.a3m"
  work_dir="${cache_dir}/work"
  log_path="${cache_dir}/${safe_label}.log"
  mkdir -p "${cache_dir}"

  if [[ -s "${cached_a3m}" ]]; then
    echo "${cached_a3m}"
    return 0
  fi
  local msa_venv="${PROTENIX_VENV}" msa_model_dir="${PROTENIX_MODEL_DIR}" msa_profile="standard"
  if [[ "${PREDICTOR}" == "protenix-constraint-v0.5" ]]; then
    msa_venv="${PROTENIX_CONSTRAINT_VENV}"
    msa_model_dir="${PROTENIX_CONSTRAINT_MODEL_DIR}"
    msa_profile="constraint"
  fi
  [[ -x "${msa_venv}/bin/python" ]] \
    || { echo "ERROR: Protenix environment is not installed." >&2; return 1; }
  [[ -f "${REPO_ROOT}/scripts/protenix_msa.py" ]] \
    || { echo "ERROR: Protenix MSA adapter is missing." >&2; return 1; }

  set +e
  PROTENIX_ROOT_DIR="${msa_model_dir}" \
    "${msa_venv}/bin/python" "${REPO_ROOT}/scripts/protenix_msa.py" \
      --sequence "${seq}" --output "${cached_a3m}" \
      --nanohunter-root "${REPO_ROOT}" --work-dir "${work_dir}" --profile "${msa_profile}" \
      >"${log_path}" 2>&1
  local rc=$?
  set -e
  if [[ "${rc}" -eq 0 && -s "${cached_a3m}" ]]; then
    echo "${cached_a3m}"
    return 0
  fi
  tail -n 120 "${log_path}" >&2 || true
  echo "ERROR: Protenix MSA generation failed for ${safe_label}; no reusable MSA was produced." >&2
  return 1
}

generate_intellifold_auto_msa_cache() {
  local seq="$1"
  local chain_id="$2"
  local cache_label="$3"
  local cache_dir="$4"

  local safe_label yaml_path out_dir log_path cached_csv cached_a3m raw_a3m raw_csv
  safe_label="$(printf '%s' "${cache_label}" | tr -c 'A-Za-z0-9_' '_')"
  cache_dir="${cache_dir}/${safe_label}_intellifold"
  yaml_path="${cache_dir}/${safe_label}.yaml"
  out_dir="${cache_dir}/intellifold"
  log_path="${cache_dir}/${safe_label}.log"
  cached_csv="${cache_dir}/${safe_label}_full_msa.csv"
  cached_a3m="${cache_dir}/${safe_label}_full_msa.a3m"
  mkdir -p "${cache_dir}" "${out_dir}"

  if [[ -s "${cached_a3m}" ]]; then
    echo "${cached_a3m}"
    return 0
  fi
  if [[ -s "${cached_csv}" ]]; then
    csv_msa_to_a3m "${cached_csv}" "${cached_a3m}"
    echo "${cached_a3m}"
    return 0
  fi

  python3 - "${seq}" "${chain_id}" "${yaml_path}" <<'PY'
import sys
from pathlib import Path

seq, chain_id, out_yaml = sys.argv[1:4]
seq = "".join(ch for ch in seq.strip().upper() if ch.isalpha())
if not seq:
    raise SystemExit("Cannot generate IntelliFold MSA for an empty sequence.")
Path(out_yaml).parent.mkdir(parents=True, exist_ok=True)
# Deliberately omit `msa:`: IntelliFold's data-processing path then calls its
# configured MSA server instead of entering explicit single-sequence mode.
Path(out_yaml).write_text(
    "sequences:\n"
    "  - protein:\n"
    f"      id: {chain_id}\n"
    f"      sequence: {seq}\n"
    "version: 1\n"
)
PY

  source "${INTELLIFOLD_VENV}/bin/activate"
  set +e
  OMP_NUM_THREADS="${INTELLIFOLD_OMP_NUM_THREADS}" VECLIB_MAXIMUM_THREADS="${INTELLIFOLD_VECLIB_MAXIMUM_THREADS}" KMP_USE_SHM=0 python "${INTELLIFOLD_RUNNER}" "${yaml_path}" \
    --out_dir "${out_dir}" \
    "${INTELLIFOLD_EXTRA_FLAGS[@]}" \
    --msa_server_url "https://api.colabfold.com" \
    --only_run_data_process \
    > "${log_path}" 2>&1
  local rc=$?
  set -e
  deactivate || true

  raw_a3m="$(find "${out_dir}" -type f -name '*_unpaired.a3m' | sort | head -n 1 || true)"
  raw_csv="$(find "${out_dir}" -type f -name '*_0.csv' | sort | head -n 1 || true)"
  if [[ "${rc}" -eq 0 && -n "${raw_a3m}" && -s "${raw_a3m}" ]]; then
    cp -f "${raw_a3m}" "${cached_a3m}"
    if [[ -n "${raw_csv}" && -s "${raw_csv}" ]]; then
      cp -f "${raw_csv}" "${cached_csv}"
    fi
    echo "${cached_a3m}"
    return 0
  fi

  if [[ "${rc}" -eq 0 && -n "${raw_csv}" && -s "${raw_csv}" ]]; then
    cp -f "${raw_csv}" "${cached_csv}"
    csv_msa_to_a3m "${cached_csv}" "${cached_a3m}"
    echo "${cached_a3m}"
    return 0
  fi

  tail -n 120 "${log_path}" >&2 || true
  echo "ERROR: IntelliFold native auto-MSA generation failed for ${safe_label}; no reusable MSA was produced." >&2
  return 1
}

prepare_nanobody_scaffold_msa_cache() {
  if [[ "${WORKFLOW}" != "nanobody" || "${SCAFFOLD_FROM_TEMPLATE}" -ne 1 || "${NANOBODY_SCAFFOLD_MSA_MODE}" == "off" ]]; then
    NANOBODY_SCAFFOLD_MSA_BASE_A3M=""
    return 0
  fi

  local scaffold_seq cache_dir source_path generated_path catalog_tsv precomputed_path scaffold_id
  scaffold_seq="$(extract_binder_sequence_from_yaml "${TEMPLATE_YAML}" "${ANTIFOLD_NANOBODY_CHAIN}")"
  [[ -n "${scaffold_seq}" ]] || die "Template chain ${ANTIFOLD_NANOBODY_CHAIN} sequence is empty; scaffold MSA requires a concrete nanobody scaffold sequence."
  catalog_tsv="${REPO_ROOT}/examples/nanobody_scaffolds/catalog.tsv"

  cache_dir="${MSA_CACHE_DIR}/nanobody_scaffold_msa"
  mkdir -p "${cache_dir}"

  if [[ -n "${NANOBODY_SCAFFOLD_MSA_SOURCE}" ]]; then
    [[ -f "${NANOBODY_SCAFFOLD_MSA_SOURCE}" ]] || die "Nanobody scaffold MSA source not found: ${NANOBODY_SCAFFOLD_MSA_SOURCE}"
    NANOBODY_SCAFFOLD_MSA_SOURCE="$(cd "$(dirname "${NANOBODY_SCAFFOLD_MSA_SOURCE}")" && pwd)/$(basename "${NANOBODY_SCAFFOLD_MSA_SOURCE}")"
    if [[ "${NANOBODY_SCAFFOLD_MSA_SOURCE##*.}" == "a3m" ]]; then
      source_path="$(sanitize_a3m_file "${NANOBODY_SCAFFOLD_MSA_SOURCE}")"
    elif [[ "${NANOBODY_SCAFFOLD_MSA_SOURCE##*.}" == "csv" ]]; then
      source_path="${cache_dir}/source_full_msa.a3m"
      csv_msa_to_a3m "${NANOBODY_SCAFFOLD_MSA_SOURCE}" "${source_path}"
    else
      die "--nanobody-scaffold-msa-source must be an A3M file, or a Boltz MSA CSV that can be converted to A3M."
    fi
    NANOBODY_SCAFFOLD_MSA_BASE_A3M="${source_path}"
    echo "==> Using nanobody scaffold MSA source: ${NANOBODY_SCAFFOLD_MSA_BASE_A3M}"
    return 0
  fi

  if [[ "${NANOBODY_SCAFFOLD_MSA_MODE}" == "single" ]]; then
    source_path="${cache_dir}/scaffold_single.a3m"
    write_single_seq_a3m "${scaffold_seq}" "${source_path}"
    NANOBODY_SCAFFOLD_MSA_BASE_A3M="${source_path}"
    echo "==> Using single-sequence nanobody scaffold MSA seed: ${NANOBODY_SCAFFOLD_MSA_BASE_A3M}"
    return 0
  fi

  precomputed_path="$(python3 - \
    "${catalog_tsv}" \
    "${scaffold_seq}" \
    "${NANOBODY_SCAFFOLD_MSA_CACHE_DIR}" \
    "${NANOBODY_SCAFFOLD_MSA_LEGACY_CACHE_DIR}" <<'PY'
import csv
import re
import sys
from pathlib import Path

catalog_tsv, scaffold_seq, cache_dir, legacy_cache_dir = sys.argv[1:5]
scaffold_seq = re.sub(r"[^A-Za-z]", "", scaffold_seq).upper()
catalog = Path(catalog_tsv)
caches = []
for raw in (cache_dir, legacy_cache_dir):
    cache = Path(raw).expanduser()
    if cache not in caches:
        caches.append(cache)
if catalog.exists():
    with catalog.open(newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            seq = re.sub(r"[^A-Za-z]", "", row.get("sequence", "")).upper()
            if seq != scaffold_seq:
                continue
            scaffold_id = (row.get("scaffold_id") or "").strip()
            if scaffold_id:
                found = False
                for cache in caches:
                    for filename in ("full_msa.a3m", "full_msa.csv"):
                        candidate = cache / scaffold_id / filename
                        if candidate.exists() and candidate.stat().st_size > 0:
                            print(candidate)
                            found = True
                            break
                    if found:
                        break
            break
PY
)"
  if [[ -n "${precomputed_path}" && -s "${precomputed_path}" ]]; then
    precomputed_path="$(cd "$(dirname "${precomputed_path}")" && pwd)/$(basename "${precomputed_path}")"
    if [[ "${precomputed_path}" == "${NANOBODY_SCAFFOLD_MSA_LEGACY_CACHE_DIR}/"* ]]; then
      scaffold_id="$(basename "$(dirname "${precomputed_path}")")"
      local migrated_dir legacy_csv
      migrated_dir="${NANOBODY_SCAFFOLD_MSA_CACHE_DIR}/${scaffold_id}"
      mkdir -p "${migrated_dir}"
      if [[ "${precomputed_path##*.}" == "a3m" ]]; then
        cp -f "${precomputed_path}" "${migrated_dir}/full_msa.a3m"
        legacy_csv="$(dirname "${precomputed_path}")/full_msa.csv"
        if [[ -s "${legacy_csv}" ]]; then
          cp -f "${legacy_csv}" "${migrated_dir}/full_msa.csv"
        fi
        precomputed_path="$(cd "${migrated_dir}" && pwd)/full_msa.a3m"
        echo "==> Migrated legacy scaffold MSA beside catalog: ${precomputed_path}"
      elif [[ "${precomputed_path##*.}" == "csv" ]]; then
        cp -f "${precomputed_path}" "${migrated_dir}/full_msa.csv"
        csv_msa_to_a3m "${migrated_dir}/full_msa.csv" "${migrated_dir}/full_msa.a3m"
        precomputed_path="$(cd "${migrated_dir}" && pwd)/full_msa.a3m"
        echo "==> Migrated legacy scaffold MSA beside catalog: ${precomputed_path}"
      fi
    fi
    if [[ "${precomputed_path##*.}" == "csv" ]]; then
      source_path="${cache_dir}/precomputed_full_msa.a3m"
      csv_msa_to_a3m "${precomputed_path}" "${source_path}"
      precomputed_path="${source_path}"
    else
      precomputed_path="$(sanitize_a3m_file "${precomputed_path}")"
    fi
    NANOBODY_SCAFFOLD_MSA_BASE_A3M="${precomputed_path}"
    echo "==> Using precomputed nanobody scaffold MSA: ${NANOBODY_SCAFFOLD_MSA_BASE_A3M}"
    return 0
  fi

  echo "==> Calibration: generating Boltz nanobody scaffold MSA cache for chain ${ANTIFOLD_NANOBODY_CHAIN}..."
  if ! source_path="$(generate_boltz_auto_msa_cache "${scaffold_seq}" "${ANTIFOLD_NANOBODY_CHAIN}" "nanobody_scaffold" "${MSA_CACHE_DIR}")"; then
    die "Boltz nanobody scaffold MSA precompute failed; use --nanobody-scaffold-msa single/off or provide --nanobody-scaffold-msa-source."
  fi
  [[ -n "${source_path}" && -f "${source_path}" ]] || die "Nanobody scaffold MSA cache did not produce a reusable MSA path."
  scaffold_id="$(python3 - "${catalog_tsv}" "${scaffold_seq}" <<'PY'
import csv
import re
import sys

catalog_tsv, scaffold_seq = sys.argv[1:3]
scaffold_seq = re.sub(r"[^A-Za-z]", "", scaffold_seq).upper()
with open(catalog_tsv, newline="") as handle:
    for row in csv.DictReader(handle, delimiter="\t"):
        sequence = re.sub(r"[^A-Za-z]", "", row.get("sequence", "")).upper()
        if sequence == scaffold_seq:
            print((row.get("scaffold_id") or "").strip())
            break
PY
)"
  if [[ -n "${scaffold_id}" ]]; then
    local persistent_dir generated_csv
    persistent_dir="${NANOBODY_SCAFFOLD_MSA_CACHE_DIR}/${scaffold_id}"
    mkdir -p "${persistent_dir}"
    cp -f "${source_path}" "${persistent_dir}/full_msa.a3m"
    generated_csv="$(dirname "${source_path}")/nanobody_scaffold_full_msa.csv"
    if [[ -s "${generated_csv}" ]]; then
      cp -f "${generated_csv}" "${persistent_dir}/full_msa.csv"
    fi
    source_path="$(cd "${persistent_dir}" && pwd)/full_msa.a3m"
    echo "==> Persisted scaffold MSA beside catalog: ${source_path}"
  fi
  NANOBODY_SCAFFOLD_MSA_BASE_A3M="${source_path}"
  echo "==> Cached nanobody scaffold MSA: ${NANOBODY_SCAFFOLD_MSA_BASE_A3M}"
}

make_masked_nanobody_scaffold_msa() {
  local binder_seq="$1"
  local out_a3m="$2"
  local predictor="$3"

  if [[ "${WORKFLOW}" != "nanobody" || "${SCAFFOLD_FROM_TEMPLATE}" -ne 1 || "${NANOBODY_SCAFFOLD_MSA_MODE}" == "off" ]]; then
    echo ""
    return 0
  fi
  case "${predictor}" in
    boltz|intellifold|protenix-v2|protenix-mini|protenix-constraint-v0.5|openfold-3-mlx) : ;;
    *) echo ""; return 0 ;;
  esac
  [[ -n "${NANOBODY_SCAFFOLD_MSA_BASE_A3M}" ]] || { echo ""; return 0; }

  local scaffold_seq catalog_tsv
  scaffold_seq="$(extract_binder_sequence_from_yaml "${TEMPLATE_YAML}" "${ANTIFOLD_NANOBODY_CHAIN}")"
  catalog_tsv="${REPO_ROOT}/examples/nanobody_scaffolds/catalog.tsv"
  mkdir -p "$(dirname "${out_a3m}")"

  python3 - \
    "${NANOBODY_SCAFFOLD_MSA_BASE_A3M}" \
    "${out_a3m}" \
    "${binder_seq}" \
    "${scaffold_seq}" \
    "${NANOBODY_SCAFFOLD_MSA_MASK_CDRS}" \
    "${NANOBODY_SEED_CDR_RANGES}" \
    "${catalog_tsv}" \
    "${NANOBODY_SCAFFOLD_MSA_MAX_SEQS}" \
    "${NANOBODY_SCAFFOLD_MSA_MASK_CHAR}" <<'PY'
import csv
import re
import sys
from pathlib import Path

(
    base_a3m,
    out_a3m,
    binder_seq,
    scaffold_seq,
    mask_regions_raw,
    ranges_raw,
    catalog_tsv,
    max_seqs_raw,
    mask_char,
) = sys.argv[1:10]

base_a3m = Path(base_a3m)
out_a3m = Path(out_a3m)
binder_seq = re.sub(r"[^A-Za-z-]", "", binder_seq).upper()
scaffold_seq = re.sub(r"[^A-Za-z]", "", scaffold_seq).upper()
max_seqs = max(1, int(max_seqs_raw))
mask_char = mask_char.upper()
if mask_char not in {"-", "X"}:
    raise SystemExit("Internal error: scaffold MSA mask char must be '-' or 'X'.")
if not binder_seq or not scaffold_seq:
    raise SystemExit("Cannot write scaffold MSA without binder and scaffold sequences.")
if len(binder_seq) != len(scaffold_seq):
    raise SystemExit(
        f"Current binder length {len(binder_seq)} does not match scaffold length {len(scaffold_seq)}."
    )

DEFAULT_RANGES = {
    "CDR1": (27, 38),
    "CDR2": (56, 65),
    "CDR3": (105, 117),
}


def expand_regions(raw):
    tokens = [t.strip().upper() for t in re.split(r"[\s,;]+", raw or "") if t.strip()]
    if not tokens:
        return ["CDR3"]
    out = []
    for tok in tokens:
        tok = {"CDRH1": "CDR1", "CDRH2": "CDR2", "CDRH3": "CDR3"}.get(tok, tok)
        if tok in {"ALL", "ALLH", "CDRH"}:
            out.extend(["CDR1", "CDR2", "CDR3"])
        elif tok in {"CDR1", "CDR2", "CDR3"}:
            out.append(tok)
        else:
            raise SystemExit(f"Unsupported scaffold MSA mask CDR region: {tok}")
    return [r for r in ["CDR1", "CDR2", "CDR3"] if r in out]


def parse_range_value(value):
    m = re.match(r"^\s*(\d+)\s*(?:-|\.\.)\s*(\d+)\s*$", value or "")
    if not m:
        raise ValueError(value)
    start, end = int(m.group(1)), int(m.group(2))
    if start < 1 or end < start:
        raise ValueError(value)
    return start, end


def load_catalog_ranges():
    path = Path(catalog_tsv)
    if not path.exists():
        return {}
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            seq = re.sub(r"[^A-Za-z]", "", row.get("sequence", "")).upper()
            if seq != scaffold_seq:
                continue
            return {
                "CDR1": parse_range_value(row.get("cdr1_range_1based", "")),
                "CDR2": parse_range_value(row.get("cdr2_range_1based", "")),
                "CDR3": parse_range_value(row.get("cdr3_range_1based", "")),
            }
    return {}


def parse_override_ranges():
    raw = (ranges_raw or "").strip()
    if not raw or raw.lower() in {"auto", "none", "null"}:
        return {}
    out = {}
    for match in re.finditer(
        r"\b(CDR[123]|CDRH[123])\b\s*[:=]\s*(\d+)\s*(?:-|\.\.)\s*(\d+)",
        raw,
        flags=re.I,
    ):
        region = match.group(1).upper().replace("CDRH", "CDR")
        start, end = int(match.group(2)), int(match.group(3))
        if start < 1 or end < start:
            raise SystemExit(f"Invalid {region} scaffold MSA mask range: {start}-{end}")
        out[region] = (start, end)
    if not out:
        raise SystemExit(
            "--nanobody-seed-cdr-ranges must look like CDR1:26-33,CDR2:51-57,CDR3:97-110"
        )
    return out


regions = expand_regions(mask_regions_raw)
ranges = dict(DEFAULT_RANGES)
ranges.update(load_catalog_ranges())
ranges.update(parse_override_ranges())
mask_positions = set()
for region in regions:
    start, end = ranges[region]
    if end > len(scaffold_seq):
        raise SystemExit(
            f"{region} scaffold MSA mask range {start}-{end} exceeds scaffold length {len(scaffold_seq)}."
        )
    mask_positions.update(range(start - 1, end))


def read_a3m(path):
    records = []
    header = None
    parts = []
    for raw in path.read_text(errors="ignore").splitlines():
        if raw.startswith(">"):
            if header is not None:
                records.append((header, "".join(parts)))
            header = raw[1:].strip() or "sequence"
            parts = []
        else:
            parts.append(raw.strip())
    if header is not None:
        records.append((header, "".join(parts)))
    return records


def read_msa_records(path):
    if path.suffix.lower() == ".csv":
        records = []
        with path.open(newline="") as handle:
            reader = csv.DictReader(handle)
            if not {"sequence", "key"}.issubset(reader.fieldnames or []):
                raise SystemExit(
                    f"Invalid scaffold MSA CSV {path}: expected columns sequence,key."
                )
            for i, row in enumerate(reader):
                seq = (row.get("sequence") or "").strip()
                if not seq:
                    continue
                key = str(row.get("key") or f"row_{i}").strip() or f"row_{i}"
                records.append((key, seq))
        return records
    return read_a3m(path)


def aligned_columns(seq):
    # Drop A3M insertions and dots; keep aligned residues/gaps.
    return "".join(ch for ch in seq if not ch.islower() and ch != ".").upper()


def clean_aligned(seq):
    allowed = set("ACDEFGHIKLMNPQRSTVWYX-")
    return "".join(ch if ch in allowed else "X" for ch in seq.upper())


def mask_support(seq):
    chars = list(clean_aligned(seq))
    if len(chars) != len(scaffold_seq):
        return None
    for idx in mask_positions:
        chars[idx] = mask_char
    return "".join(chars)


def wrap(seq, width=160):
    return "\n".join(seq[i : i + width] for i in range(0, len(seq), width))


query = clean_aligned(binder_seq)
if len(query) != len(scaffold_seq):
    raise SystemExit("Current binder sequence has unexpected aligned length.")

support = []
seen = {query}
for header, seq in read_msa_records(base_a3m):
    aligned = aligned_columns(seq)
    masked = mask_support(aligned)
    if masked is None:
        continue
    if masked in seen:
        continue
    seen.add(masked)
    support.append((header, masked))
    if len(support) >= max(0, max_seqs - 1):
        break

if not support and max_seqs > 1:
    fallback = mask_support(scaffold_seq)
    if fallback and fallback not in seen:
        support.append(("masked_scaffold_support", fallback))

out_a3m.parent.mkdir(parents=True, exist_ok=True)
with out_a3m.open("w") as handle:
    handle.write(">query\n")
    handle.write(wrap(query) + "\n")
    for i, (header, seq) in enumerate(support, start=1):
        safe_header = re.sub(r"\s+", "_", header)[:120] or f"support_{i}"
        handle.write(f">masked_{i}_{safe_header}\n")
        handle.write(wrap(seq) + "\n")
PY

  echo "${out_a3m}"
}

sanitize_protein_sequence_for_openfold() {
  local seq="$1"
  python3 - "$seq" <<'PY'
import sys
s = sys.argv[1].strip().upper()
allowed = set("ACDEFGHIKLMNPQRSTVWY")
changed = 0
out = []
for ch in s:
    if ch in allowed:
        out.append(ch)
    else:
        out.append("A")
        changed += 1
print(f"{''.join(out)}|{changed}")
PY
}

write_openfold_runner_yaml() {
  local out_yaml="$1"
  local acc
  if [[ "${CPU_ONLY}" -eq 1 ]]; then
    acc="cpu"
    cat > "${out_yaml}" <<EOF2
experiment_settings:
  mode: predict

pl_trainer_args:
  accelerator: ${acc}
  devices: 1

model_update:
  presets: ["predict", "pae_enabled"]
  custom:
    settings:
      memory:
        eval:
          use_deepspeed_evo_attention: false
EOF2
  else
    acc="gpu"
    cat > "${out_yaml}" <<EOF2
experiment_settings:
  mode: predict

pl_trainer_args:
  accelerator: ${acc}
  devices: 1

model_update:
  presets: ["predict", "pae_enabled"]
  custom:
    settings:
      memory:
        eval:
          use_deepspeed_evo_attention: false
          use_lma: false
          use_mlx_attention: true
          use_mlx_triangle_kernels: true
          use_mlx_activation_functions: true
EOF2
  fi
}

generate_openfold_target_msa_cache() {
  local template_yaml="$1"
  local msa_cache_dir="$2"
  local target_seq="$3"
  local target_chain_id="$4"
  local cache_label="${5:-target}"

  local safe_label query_json out_dir log_file rc
  safe_label="$(printf '%s' "${cache_label}" | tr -c 'A-Za-z0-9_' '_')"
  query_json="${msa_cache_dir}/${safe_label}_query.json"
  out_dir="${msa_cache_dir}/${safe_label}_msa"
  log_file="${msa_cache_dir}/${safe_label}_msa.log"
  mkdir -p "${msa_cache_dir}" "${out_dir}"

  python3 - "${target_seq}" "${target_chain_id}" "${query_json}" "${safe_label}" <<'PY'
import json, sys
seq, cid, out_json, label = sys.argv[1:5]
payload = {
    "seeds": [42],
    "queries": {
        f"{label}_msa_only": {
            "chains": [
                {
                    "molecule_type": "protein",
                    "chain_ids": [cid],
                    "sequence": seq,
                }
            ]
        }
    },
}
with open(out_json, "w") as f:
    json.dump(payload, f, indent=2)
PY

  source "${OPENFOLD_VENV}/bin/activate"
  set +e
  KMP_USE_SHM=0 "${OPENFOLD_CLI}" align-msa-server \
    --query_json "${query_json}" \
    --output_dir "${out_dir}" \
    >"${log_file}" 2>&1
  rc=$?
  set -e
  deactivate || true
  if [[ "${rc}" -ne 0 ]]; then
    tail -n 120 "${log_file}" >&2 || true
    die "OpenFold ${cache_label} MSA calibration failed (rc=${rc})."
  fi

  local msa_a3m msa_path
  msa_a3m="$(find "${out_dir}/raw/main" -maxdepth 1 -type f -name 'uniref90_hits.a3m' | head -n 1 || true)"
  if [[ -z "${msa_a3m}" ]]; then
    msa_a3m="$(find "${out_dir}/raw/main" -maxdepth 1 -type f -name 'uniref.a3m' | head -n 1 || true)"
  fi
  if [[ -z "${msa_a3m}" ]]; then
    msa_a3m="$(find "${out_dir}/raw/main" -maxdepth 1 -type f -name '*.a3m' | sort | head -n 1 || true)"
  fi
  if [[ -n "${msa_a3m}" ]]; then
    local canonical_a3m
    canonical_a3m="${out_dir}/raw/main/uniref90_hits.a3m"
    python3 - "${msa_a3m}" "${canonical_a3m}" <<'PY'
from pathlib import Path
import sys
src, dst = map(Path, sys.argv[1:3])
data = src.read_bytes().replace(b"\x00", b"")
dst.parent.mkdir(parents=True, exist_ok=True)
dst.write_bytes(data)
PY
  fi

  # Prefer NPZ for OpenFold runtime speed; post predictors map NPZ -> cached A3M.
  msa_path="$(find "${out_dir}/main" -maxdepth 1 -type f -name 'colabfold_main.npz' | head -n 1 || true)"
  if [[ -z "${msa_path}" ]]; then
    msa_path="$(find "${out_dir}/main" -maxdepth 1 -type f -name '*.npz' | head -n 1 || true)"
  fi
  if [[ -z "${msa_path}" && -n "${msa_a3m}" ]]; then
    msa_path="${out_dir}/raw/main/uniref90_hits.a3m"
  fi
  if [[ -z "${msa_path}" ]]; then
    tail -n 120 "${log_file}" >&2 || true
    die "OpenFold ${cache_label} MSA cache was not produced in ${out_dir}."
  fi

  echo "${msa_path}" > "${msa_cache_dir}/${safe_label}_msa_path.txt"
  echo "${msa_path}"
}

build_openfold_query_json() {
  local builder="${REPO_ROOT}/scripts/openfold_query_json.py"
  [[ -f "${builder}" ]] || die "Missing OpenFold query builder: ${builder}"
  python3 "${builder}" "$@"
}

extract_redesigned_sequence_from_fastas() {
  python3 - "$@" <<'PY'
import sys
from pathlib import Path
paths=[Path(p) for p in sys.argv[1:]]
if not paths:
    raise SystemExit("No FASTA files passed")
seqs=[]
for p in paths:
    cur=[]
    for line in p.read_text().splitlines():
        s=line.strip()
        if not s:
            continue
        if s.startswith(">"):
            if cur:
                seqs.append("".join(cur)); cur=[]
        else:
            cur.append(s)
    if cur:
        seqs.append("".join(cur))
if not seqs:
    raise SystemExit("No sequences found")
pick = seqs[1] if len(seqs) >= 2 else seqs[0]
print(pick.split(":",1)[0] if ":" in pick else pick)
PY
}

residue_spec_to_positions() {
  local residue_spec="$1"
  python3 - "${residue_spec}" <<'PY'
import re
import sys

positions = []
for token in sys.argv[1].split():
    match = re.search(r"(\d+)$", token)
    if not match:
        raise SystemExit(f"Invalid residue token: {token}")
    position = int(match.group(1))
    if position not in positions:
        positions.append(position)
print(" ".join(str(position) for position in positions))
PY
}

apply_nanobody_redesign_guard() {
  local previous_seq="$1"
  local candidate_seq="$2"
  local residue_spec="$3"
  python3 - "${previous_seq}" "${candidate_seq}" "${residue_spec}" <<'PY'
import re
import sys

previous, candidate, residue_spec = sys.argv[1:4]
previous = re.sub(r"[^A-Za-z]", "", previous).upper()
candidate = re.sub(r"[^A-Za-z]", "", candidate).upper()
if len(previous) != len(candidate):
    raise SystemExit(
        f"Inverse-folding sequence length changed from {len(previous)} to {len(candidate)}"
    )

positions = set()
for token in residue_spec.split():
    match = re.search(r"(\d+)$", token)
    if not match:
        raise SystemExit(f"Invalid redesigned residue token: {token}")
    position = int(match.group(1))
    if position < 1 or position > len(previous):
        raise SystemExit(
            f"Redesigned residue {token} is outside sequence length {len(previous)}"
        )
    positions.add(position - 1)

if not positions:
    raise SystemExit("No exact nanobody redesign positions were provided")

outside_changes = [
    index + 1
    for index, (old, new) in enumerate(zip(previous, candidate))
    if old != new and index not in positions
]
if outside_changes:
    preview = ",".join(map(str, outside_changes[:12]))
    suffix = "..." if len(outside_changes) > 12 else ""
    print(
        f"WARNING: inverse-folding proposed {len(outside_changes)} framework "
        f"mutation(s) at {preview}{suffix}; NanoHunter restored the framework.",
        file=sys.stderr,
    )

out = list(previous)
for index in positions:
    aa = candidate[index]
    if aa not in "ACDEFGHIKLMNPQRSTVWY":
        raise SystemExit(
            f"Inverse-folding returned non-standard residue {aa!r} at position {index + 1}"
        )
    out[index] = aa
print("".join(out))
PY
}

patch_cif_unk() {
  # Protenix UNKs contain an alanine atom set plus a generic CG pseudo-atom.
  # Its handoff therefore needs a row-aware, binder-chain-scoped repair; the
  # other predictors retain their established placeholder substitution.
  local in_cif="$1"
  local out_cif="$2"
  local mode="$3"
  local predictor="$4"
  local binder_chain="$5"
  python3 "${REPO_ROOT}/scripts/normalize_unk_cif.py" \
    --input "${in_cif}" \
    --output "${out_cif}" \
    --mode "${mode}" \
    --predictor "${predictor}" \
    --binder-chain "${binder_chain}"
}

convert_cif_to_pdb() {
  local in_cif="$1"
  local out_pdb="$2"
  "${BOLTZ_VENV}/bin/python" - "$in_cif" "$out_pdb" <<'PY'
import sys, gemmi

in_path, out_path = sys.argv[1:3]

def has_atoms(structure):
    for model in structure:
        for chain in model:
            for res in chain:
                for _ in res:
                    return True
    return False

try:
    st = gemmi.read_structure(in_path)
except Exception:
    st = None

# Fast path: standard mmCIF readable by gemmi Structure API.
if st is not None and len(st) > 0 and has_atoms(st):
    st.write_pdb(out_path)
    raise SystemExit(0)

# Fallback path for CIFs missing fields expected by gemmi.read_structure
# (e.g. no _atom_site.occupancy in some OpenFold outputs).
doc = gemmi.cif.read_file(in_path)
block = doc.sole_block()
tab = block.find_mmcif_category('_atom_site.')
if len(tab) == 0:
    raise SystemExit(f"No _atom_site category in {in_path}")

tags = [str(t) for t in tab.tags]
idx_full = {t: i for i, t in enumerate(tags)}
idx_short = {}
for t, i in idx_full.items():
    key = t.split('.', 1)[1] if '.' in t else t
    idx_short[key] = i

def get(row, name, default=''):
    if name in idx_short:
        return row[idx_short[name]]
    full = f"_atom_site.{name}"
    if full in idx_full:
        return row[idx_full[full]]
    return default

def as_float(v, default=0.0):
    try:
        if v in ('', '.', '?'):
            return default
        return float(v)
    except Exception:
        return default

def as_int(v, default=0):
    try:
        if v in ('', '.', '?'):
            return default
        return int(float(v))
    except Exception:
        return default

lines = []
serial = 1
for row in tab:
    rec = (get(row, 'group_PDB', 'ATOM') or 'ATOM').strip().upper()
    if rec not in ('ATOM', 'HETATM'):
        continue
    atom_name = (get(row, 'auth_atom_id') or get(row, 'label_atom_id') or 'X').strip()
    alt = (get(row, 'label_alt_id', ' ') or ' ').strip()
    if alt in ('.', '?', ''):
        alt = ' '
    resname = (get(row, 'auth_comp_id') or get(row, 'label_comp_id') or 'UNK').strip()[:3]
    chain = (get(row, 'auth_asym_id') or get(row, 'label_asym_id') or 'A').strip()
    chain = chain[0] if chain else 'A'
    resseq = as_int(get(row, 'auth_seq_id') or get(row, 'label_seq_id'), 1)
    icode = (get(row, 'pdbx_PDB_ins_code', ' ') or ' ').strip()
    if icode in ('.', '?', ''):
        icode = ' '
    x = as_float(get(row, 'Cartn_x'))
    y = as_float(get(row, 'Cartn_y'))
    z = as_float(get(row, 'Cartn_z'))
    occ = as_float(get(row, 'occupancy'), 1.0)
    b = as_float(get(row, 'B_iso_or_equiv'), 0.0)
    elem = (get(row, 'type_symbol') or atom_name[:1] or 'X').strip().upper()[:2]
    charge = (get(row, 'pdbx_formal_charge', '') or '').strip()
    if charge in ('.', '?'):
        charge = ''
    if charge and len(charge) == 1 and charge in '+-':
        charge = f"1{charge}"
    charge = charge[:2]
    atom_name_fmt = atom_name[:4].rjust(4)
    line = (
        f"{rec:<6}{serial:>5} {atom_name_fmt}{alt:1}{resname:>3} {chain:1}"
        f"{resseq:>4}{icode:1}   {x:>8.3f}{y:>8.3f}{z:>8.3f}{occ:>6.2f}{b:>6.2f}"
        f"          {elem:>2}{charge:>2}"
    )
    lines.append(line)
    serial += 1

if not lines:
    raise SystemExit(f"Failed to convert CIF to PDB atoms for {in_path}")

with open(out_path, 'w') as fh:
    for ln in lines:
        fh.write(ln + "\n")
    fh.write("END\n")
PY
}

extract_metrics_from_conf_json() {
  local json_path="$1"
  python3 - "$json_path" <<'PY'
import sys, json
p = sys.argv[1]
try:
    d = json.load(open(p))
except Exception:
    print("nan,nan")
    raise SystemExit(0)

def get_any(obj, keys):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in keys:
                return v
        for v in obj.values():
            x = get_any(v, keys)
            if x is not None:
                return x
    elif isinstance(obj, list):
        for v in obj:
            x = get_any(v, keys)
            if x is not None:
                return x
    return None

iptm = get_any(d, {"iptm", "i_ptm", "iptm_score", "iptm+ptm"})
plddt = get_any(d, {"complex_plddt", "avg_plddt", "plddt"})

def to_float(v):
    try:
        return float(v)
    except Exception:
        return float("nan")

print(f"{to_float(iptm)},{to_float(plddt)}")
PY
}

annotate_boltz_ipsae() {
  local input_yaml="$1"
  local output_dir="$2"
  local log_path="${3:-${output_dir}/predict.log}"
  [[ -f "${IPSAE_SCORER}" ]] || die "ipSAE scorer is missing: ${IPSAE_SCORER}"
  "${BOLTZ_VENV}/bin/python" "${IPSAE_SCORER}" boltz \
    --yaml "${input_yaml}" --output "${output_dir}" \
    >> "${log_path}" 2>&1 \
    || { tail -n 80 "${log_path}" >&2 || true; die "Boltz ipSAE scoring failed for ${input_yaml}"; }
}

find_boltz_results_root() {
  local boltz_out="$1"
  find "${boltz_out}" -maxdepth 2 -type d -name "boltz_results_*" | head -n 1 || true
}

find_boltz_pred_leaf() {
  local boltz_results_root="$1"
  find "${boltz_results_root}/predictions" -maxdepth 2 -type d -print | grep -v "/predictions$" | head -n 1 || true
}

run_predict_boltz() {
  local input_yaml="$1"
  local out_dir="$2"
  local pred_min="$3"
  local use_potentials="${4:-0}"
  local predict_log
  predict_log="${out_dir}/predict.log"

  mkdir -p "${out_dir}"
  local cmd=("${BOLTZ_CLI}" predict "${input_yaml}" --out_dir "${out_dir}" "${BOLTZ_EXTRA_FLAGS[@]}")
  if [[ "${use_potentials}" -eq 1 ]]; then
    local _has_pot=0 tok
    for tok in "${cmd[@]}"; do
      if [[ "${tok}" == "--use_potentials" ]]; then
        _has_pot=1
        break
      fi
    done
    if [[ "${_has_pot}" -eq 0 ]]; then
      cmd+=("--use_potentials")
    fi
  fi
  source "${BOLTZ_VENV}/bin/activate"
  "${cmd[@]}" >"${predict_log}" 2>&1 &
  local pid=$!
  local baseline_avail_kb min_avail_kb
  baseline_avail_kb="$(get_system_available_kb)"
  if [[ -z "${baseline_avail_kb}" || ! "${baseline_avail_kb}" =~ ^[0-9]+$ ]]; then
    baseline_avail_kb=0
  fi
  min_avail_kb="${baseline_avail_kb}"
  local tick=0
  while kill -0 "${pid}" 2>/dev/null; do
    sleep 1
    tick=$((tick + 1))
    if (( tick % 30 == 0 )); then
      local rss_kb footprint_kb avail_kb sys_delta_mb
      rss_kb="$(ps -o rss= -p "${pid}" 2>/dev/null | awk '{print $1}' || echo 0)"
      footprint_kb="$(get_process_physical_footprint_kb "${pid}")"
      avail_kb="$(get_system_available_kb)"
      if [[ -n "${avail_kb}" && "${avail_kb}" =~ ^[0-9]+$ ]]; then
        if (( min_avail_kb == 0 || avail_kb < min_avail_kb )); then
          min_avail_kb="${avail_kb}"
        fi
      fi
      sys_delta_mb=0
      if (( baseline_avail_kb > 0 && min_avail_kb > 0 && baseline_avail_kb > min_avail_kb )); then
        sys_delta_mb="$(( (baseline_avail_kb - min_avail_kb) / 1024 ))"
      fi
      echo ">>> Boltz still running (pid=${pid}, elapsed=${tick}s, rss_kb=${rss_kb}, footprint_kb=${footprint_kb}, sys_delta_mb=${sys_delta_mb})" >&2
    fi
  done
  set +e
  wait "${pid}"
  local rc=$?
  set -e
  deactivate || true
  if [[ "${rc}" -ne 0 ]]; then
    echo "ERROR: Boltz prediction failed (rc=${rc}) for ${input_yaml}" >&2
    tail -n 80 "${predict_log}" >&2 || true
    die "Boltz prediction failed (rc=${rc}) for ${input_yaml}"
  fi
  annotate_boltz_ipsae "${input_yaml}" "${out_dir}" "${predict_log}"

  local root leaf conf struct
  root="$(find_boltz_results_root "${out_dir}")"
  [[ -n "$root" ]] || die "Boltz output missing boltz_results_* in ${out_dir}"
  leaf="$(find_boltz_pred_leaf "${root}")"
  [[ -n "$leaf" ]] || die "Boltz predictions leaf not found in ${root}"

  conf="$(find "${leaf}" -maxdepth 1 -type f -name 'confidence_*_model_0.json' | sort | head -n 1 || true)"
  struct="$(find "${leaf}" -maxdepth 1 -type f \( -name '*.cif' -o -name '*.pdb' \) | sort | head -n 1 || true)"
  [[ -n "$struct" ]] || die "Boltz structure not found in ${leaf}"

  mkdir -p "${pred_min}"
  if [[ -n "$conf" ]]; then cp -f "$conf" "${pred_min}/confidence.json"; fi
  if [[ "${struct##*.}" == "cif" ]]; then
    cp -f "$struct" "${pred_min}/model_0.cif"
  else
    cp -f "$struct" "${pred_min}/model_0.pdb"
  fi

  local iptm plddt
  iptm="nan"; plddt="nan"
  if [[ -f "${pred_min}/confidence.json" ]]; then
    IFS=',' read -r iptm plddt <<< "$(extract_metrics_from_conf_json "${pred_min}/confidence.json")"
    echo "$iptm" > "${pred_min}/iptm.txt" || true
  fi

  echo "${struct}|${conf}|${iptm}|${plddt}"
}

run_boltz_predict_monitored() {
  local yaml="$1"
  local out_dir="$2"
  local peak_file="$3"
  local use_potentials="${4:-0}"
  local predict_log
  predict_log="${out_dir}/calibration_predict.log"

  mkdir -p "${out_dir}"
  rm -f "${peak_file}"

  local cmd=("${BOLTZ_CLI}" predict "${yaml}" --out_dir "${out_dir}" "${BOLTZ_EXTRA_FLAGS[@]}")
  if [[ "${use_potentials}" -eq 1 ]]; then
    local _has_pot=0 tok
    for tok in "${cmd[@]}"; do
      if [[ "${tok}" == "--use_potentials" ]]; then
        _has_pot=1
        break
      fi
    done
    if [[ "${_has_pot}" -eq 0 ]]; then
      cmd+=("--use_potentials")
    fi
  fi
  source "${BOLTZ_VENV}/bin/activate"
  "${cmd[@]}" >"${predict_log}" 2>&1 &
  local pid=$!

  local baseline_avail_kb min_avail_kb
  baseline_avail_kb="$(get_system_available_kb)"
  if [[ -z "${baseline_avail_kb}" || ! "${baseline_avail_kb}" =~ ^[0-9]+$ ]]; then
    baseline_avail_kb=0
  fi
  min_avail_kb="${baseline_avail_kb}"

  local peak_rss_kb=0
  local peak_footprint_kb=0
  local tick=0
  while kill -0 "${pid}" 2>/dev/null; do
    local rss_kb footprint_kb avail_kb sys_delta_mb
    rss_kb="$(ps -o rss= -p "${pid}" 2>/dev/null | awk '{print $1}' || echo 0)"
    footprint_kb="$(get_process_physical_footprint_kb "${pid}")"
    avail_kb="$(get_system_available_kb)"

    if [[ -n "${rss_kb}" && "${rss_kb}" =~ ^[0-9]+$ ]]; then
      if (( rss_kb > peak_rss_kb )); then
        peak_rss_kb="${rss_kb}"
      fi
    fi
    if [[ -n "${footprint_kb}" && "${footprint_kb}" =~ ^[0-9]+$ ]]; then
      if (( footprint_kb > peak_footprint_kb )); then
        peak_footprint_kb="${footprint_kb}"
      fi
    fi
    if [[ -n "${avail_kb}" && "${avail_kb}" =~ ^[0-9]+$ ]]; then
      if (( min_avail_kb == 0 || avail_kb < min_avail_kb )); then
        min_avail_kb="${avail_kb}"
      fi
    fi

    sys_delta_mb=0
    if (( baseline_avail_kb > 0 && min_avail_kb > 0 && baseline_avail_kb > min_avail_kb )); then
      sys_delta_mb="$(( (baseline_avail_kb - min_avail_kb) / 1024 ))"
    fi

    tick=$((tick + 1))
    if (( tick % 30 == 0 )); then
      echo ">>> Calibration Boltz still running (pid=${pid}, elapsed=${tick}s, rss_kb=${rss_kb}, footprint_kb=${footprint_kb}, sys_delta_mb=${sys_delta_mb})" >&2
    fi
    sleep 0.5
  done

  set +e
  wait "${pid}"
  local rc=$?
  set -e
  deactivate || true

  local peak_rss_mb peak_footprint_mb peak_sys_delta_mb peak_effective_mb
  peak_rss_mb="$(python3 - "${peak_rss_kb}" <<'PY'
import sys
kb=int(sys.argv[1])
print(max(1, int(kb/1024)))
PY
)"
  peak_footprint_mb="$(python3 - "${peak_footprint_kb}" <<'PY'
import sys
kb=int(sys.argv[1])
print(max(1, int(kb/1024)))
PY
)"
  peak_sys_delta_mb="$(python3 - "${baseline_avail_kb}" "${min_avail_kb}" <<'PY'
import sys
base=int(sys.argv[1]); minimum=int(sys.argv[2])
delta=max(0, base-minimum)
print(max(0, int(delta/1024)))
PY
)"
  peak_effective_mb="$(python3 - "${peak_rss_mb}" "${peak_footprint_mb}" "${peak_sys_delta_mb}" <<'PY'
import sys
vals=[int(x) for x in sys.argv[1:]]
print(max(vals))
PY
)"
  MONITOR_PEAK_RSS_MB="${peak_rss_mb}"
  MONITOR_PEAK_FOOTPRINT_MB="${peak_footprint_mb}"
  MONITOR_PEAK_SYS_DELTA_MB="${peak_sys_delta_mb}"
  MONITOR_PEAK_EFFECTIVE_MB="${peak_effective_mb}"
  echo "${peak_effective_mb}" > "${peak_file}"
  return "${rc}"
}

run_intellifold_predict_monitored() {
  local yaml="$1"
  local out_dir="$2"
  local peak_file="$3"
  local predict_log
  predict_log="${out_dir}/calibration_predict.log"

  mkdir -p "${out_dir}"
  rm -f "${peak_file}"

  source "${INTELLIFOLD_VENV}/bin/activate"
  if [[ "${CPU_ONLY}" -eq 1 ]]; then
    ACCELERATE_USE_CPU=true OMP_NUM_THREADS="${INTELLIFOLD_OMP_NUM_THREADS}" VECLIB_MAXIMUM_THREADS="${INTELLIFOLD_VECLIB_MAXIMUM_THREADS}" KMP_USE_SHM=0 python "${INTELLIFOLD_RUNNER}" "${yaml}" --out_dir "${out_dir}" "${INTELLIFOLD_EXTRA_FLAGS[@]}" >"${predict_log}" 2>&1 &
  else
    OMP_NUM_THREADS="${INTELLIFOLD_OMP_NUM_THREADS}" VECLIB_MAXIMUM_THREADS="${INTELLIFOLD_VECLIB_MAXIMUM_THREADS}" KMP_USE_SHM=0 python "${INTELLIFOLD_RUNNER}" "${yaml}" --out_dir "${out_dir}" "${INTELLIFOLD_EXTRA_FLAGS[@]}" >"${predict_log}" 2>&1 &
  fi
  local pid=$!

  local baseline_avail_kb min_avail_kb
  baseline_avail_kb="$(get_system_available_kb)"
  if [[ -z "${baseline_avail_kb}" || ! "${baseline_avail_kb}" =~ ^[0-9]+$ ]]; then
    baseline_avail_kb=0
  fi
  min_avail_kb="${baseline_avail_kb}"

  local peak_rss_kb=0
  local peak_footprint_kb=0
  local tick=0
  while kill -0 "${pid}" 2>/dev/null; do
    local rss_kb footprint_kb avail_kb sys_delta_mb
    rss_kb="$(ps -o rss= -p "${pid}" 2>/dev/null | awk '{print $1}' || echo 0)"
    footprint_kb="$(get_process_physical_footprint_kb "${pid}")"
    avail_kb="$(get_system_available_kb)"

    if [[ -n "${rss_kb}" && "${rss_kb}" =~ ^[0-9]+$ ]]; then
      if (( rss_kb > peak_rss_kb )); then
        peak_rss_kb="${rss_kb}"
      fi
    fi
    if [[ -n "${footprint_kb}" && "${footprint_kb}" =~ ^[0-9]+$ ]]; then
      if (( footprint_kb > peak_footprint_kb )); then
        peak_footprint_kb="${footprint_kb}"
      fi
    fi
    if [[ -n "${avail_kb}" && "${avail_kb}" =~ ^[0-9]+$ ]]; then
      if (( min_avail_kb == 0 || avail_kb < min_avail_kb )); then
        min_avail_kb="${avail_kb}"
      fi
    fi

    sys_delta_mb=0
    if (( baseline_avail_kb > 0 && min_avail_kb > 0 && baseline_avail_kb > min_avail_kb )); then
      sys_delta_mb="$(( (baseline_avail_kb - min_avail_kb) / 1024 ))"
    fi

    tick=$((tick + 1))
    if (( tick % 30 == 0 )); then
      echo ">>> Calibration IntelliFold still running (pid=${pid}, elapsed=${tick}s, rss_kb=${rss_kb}, footprint_kb=${footprint_kb}, sys_delta_mb=${sys_delta_mb})" >&2
    fi
    sleep 0.5
  done

  set +e
  wait "${pid}"
  local rc=$?
  set -e
  deactivate || true

  local peak_rss_mb peak_footprint_mb peak_sys_delta_mb peak_effective_mb
  peak_rss_mb="$(python3 - "${peak_rss_kb}" <<'PY'
import sys
kb=int(sys.argv[1])
print(max(1, int(kb/1024)))
PY
)"
  peak_footprint_mb="$(python3 - "${peak_footprint_kb}" <<'PY'
import sys
kb=int(sys.argv[1])
print(max(1, int(kb/1024)))
PY
)"
  peak_sys_delta_mb="$(python3 - "${baseline_avail_kb}" "${min_avail_kb}" <<'PY'
import sys
base=int(sys.argv[1]); minimum=int(sys.argv[2])
delta=max(0, base-minimum)
print(max(0, int(delta/1024)))
PY
)"
  peak_effective_mb="$(python3 - "${peak_rss_mb}" "${peak_footprint_mb}" "${peak_sys_delta_mb}" <<'PY'
import sys
vals=[int(x) for x in sys.argv[1:]]
print(max(vals))
PY
)"
  MONITOR_PEAK_RSS_MB="${peak_rss_mb}"
  MONITOR_PEAK_FOOTPRINT_MB="${peak_footprint_mb}"
  MONITOR_PEAK_SYS_DELTA_MB="${peak_sys_delta_mb}"
  MONITOR_PEAK_EFFECTIVE_MB="${peak_effective_mb}"
  echo "${peak_effective_mb}" > "${peak_file}"
  return "${rc}"
}

run_predict_intellifold() {
  local input_yaml="$1"
  local out_dir="$2"
  local pred_min="$3"
  local predict_log rc
  predict_log="${out_dir}/predict.log"

  local input_stem
  input_stem="$(basename "${input_yaml%.*}")"

  mkdir -p "${out_dir}"
  source "${INTELLIFOLD_VENV}/bin/activate"
  set +e
  if [[ "${CPU_ONLY}" -eq 1 ]]; then
    ACCELERATE_USE_CPU=true OMP_NUM_THREADS="${INTELLIFOLD_OMP_NUM_THREADS}" VECLIB_MAXIMUM_THREADS="${INTELLIFOLD_VECLIB_MAXIMUM_THREADS}" KMP_USE_SHM=0 python "${INTELLIFOLD_RUNNER}" "${input_yaml}" --out_dir "${out_dir}" "${INTELLIFOLD_EXTRA_FLAGS[@]}" >"${predict_log}" 2>&1
  else
    OMP_NUM_THREADS="${INTELLIFOLD_OMP_NUM_THREADS}" VECLIB_MAXIMUM_THREADS="${INTELLIFOLD_VECLIB_MAXIMUM_THREADS}" KMP_USE_SHM=0 python "${INTELLIFOLD_RUNNER}" "${input_yaml}" --out_dir "${out_dir}" "${INTELLIFOLD_EXTRA_FLAGS[@]}" >"${predict_log}" 2>&1
  fi
  rc=$?
  set -e
  deactivate || true
  if [[ "${rc}" -ne 0 ]]; then
    echo "ERROR: IntelliFold prediction failed (rc=${rc}) for ${input_yaml}" >&2
    tail -n 80 "${predict_log}" >&2 || true
    die "IntelliFold prediction failed (rc=${rc}) for ${input_yaml}"
  fi

  local leaf conf struct
  leaf="${out_dir}/${input_stem}/predictions/${input_stem}"
  [[ -d "$leaf" ]] || die "IntelliFold predictions leaf not found: ${leaf}"

  conf="$(find "${leaf}" -maxdepth 1 -type f -name '*_summary_confidences.json' | sort | head -n 1 || true)"
  struct="$(find "${leaf}" -maxdepth 1 -type f -name '*.cif' | sort | head -n 1 || true)"
  [[ -n "$struct" ]] || die "IntelliFold structure not found in ${leaf}"

  mkdir -p "${pred_min}"
  if [[ -n "$conf" ]]; then cp -f "$conf" "${pred_min}/confidence.json"; fi
  cp -f "$struct" "${pred_min}/model_0.cif"

  local iptm plddt
  iptm="nan"; plddt="nan"
  if [[ -f "${pred_min}/confidence.json" ]]; then
    IFS=',' read -r iptm plddt <<< "$(extract_metrics_from_conf_json "${pred_min}/confidence.json")"
    echo "$iptm" > "${pred_min}/iptm.txt" || true
  fi

  echo "${struct}|${conf}|${iptm}|${plddt}"
}

run_predict_protenix() {
  local predictor="$1"
  local input_yaml="$2"
  local out_dir="$3"
  local pred_min="$4"
  local model="v2"
  [[ "${predictor}" == "protenix-mini" ]] && model="mini"
  local protenix_venv="${PROTENIX_VENV}" protenix_model_dir="${PROTENIX_MODEL_DIR}"
  if [[ "${predictor}" == "protenix-constraint-v0.5" ]]; then
    model="constraint"
    protenix_venv="${PROTENIX_CONSTRAINT_VENV}"
    protenix_model_dir="${PROTENIX_CONSTRAINT_MODEL_DIR}"
  fi

  local protenix_work_flags=(--seeds "${PREDICTOR_SEED}")
  if [[ "${PREDICTOR_SAMPLES}" != "auto" ]]; then
    protenix_work_flags+=(--samples "${PREDICTOR_SAMPLES}")
  fi

  mkdir -p "${out_dir}" "${pred_min}"
  PROTENIX_ROOT_DIR="${protenix_model_dir}" \
    "${protenix_venv}/bin/python" "${PROTENIX_ADAPTER}" \
      --yaml "${input_yaml}" --output "${out_dir}" \
      --nanohunter-root "${REPO_ROOT}" --model "${model}" \
      "${protenix_work_flags[@]}" \
      >"${out_dir}/predict.log" 2>&1 \
    || { tail -n 80 "${out_dir}/predict.log" >&2 || true; die "${predictor} prediction failed for ${input_yaml}"; }

  local struct conf iptm plddt
  struct="$(find "${out_dir}" -type f -path '*/pred_min/model_0.cif' | sort | head -n 1 || true)"
  conf="$(find "${out_dir}" -type f -path '*/pred_min/confidence.json' | sort | head -n 1 || true)"
  [[ -n "${struct}" ]] || die "${predictor} produced no normalized model_0.cif in ${out_dir}"
  cp -f "${struct}" "${pred_min}/model_0.cif"
  [[ -n "${conf}" ]] && cp -f "${conf}" "${pred_min}/confidence.json"
  iptm="nan"; plddt="nan"
  if [[ -f "${pred_min}/confidence.json" ]]; then
    IFS=',' read -r iptm plddt <<< "$(extract_metrics_from_conf_json "${pred_min}/confidence.json")"
    echo "${iptm}" > "${pred_min}/iptm.txt" || true
  fi
  echo "${pred_min}/model_0.cif|${pred_min}/confidence.json|${iptm}|${plddt}"
}

run_predict_openfold() {
  local input_yaml="$1"
  local binder_seq="$2"
  local query_name="$3"
  local out_dir="$4"
  local pred_min="$5"
  local target_msa_path="$6"

  local query_json runner_yaml binder_msa_path binder_msa_source use_server
  local predict_log rc
  local binder_seq_clean changed_count
  query_json="${out_dir}/${query_name}_query.json"
  runner_yaml="${out_dir}/${query_name}_runner.yml"
  # Use an OF3-style filename so default MSA settings ingest it without custom
  # runner config. For nanobody jobs, preserve the masked scaffold support rows
  # and rewrite only the query to the OpenFold-safe sequence.
  binder_msa_path="${out_dir}/binder_msa/uniref90_hits.a3m"
  predict_log="${out_dir}/predict.log"
  mkdir -p "${out_dir}"

  IFS='|' read -r binder_seq_clean changed_count <<< "$(sanitize_protein_sequence_for_openfold "${binder_seq}")"
  if [[ "${changed_count}" =~ ^[0-9]+$ ]] && (( changed_count > 0 )); then
    echo "WARN: OpenFold input sequence had ${changed_count} non-standard residues; replaced with 'A' for prediction." >&2
  fi

  binder_msa_source="$(extract_chain_msa_from_yaml "${input_yaml}" "A" || true)"
  if [[ -n "${binder_msa_source}" && "${binder_msa_source}" != /* ]]; then
    binder_msa_source="$(dirname "${input_yaml}")/${binder_msa_source}"
  fi
  if [[ -n "${binder_msa_source}" && -s "${binder_msa_source}" && "${binder_msa_source##*.}" == "a3m" ]]; then
    "${OPENFOLD_VENV}/bin/python" "${OPENFOLD_A3M_QUERY_REWRITER}" \
      --input "${binder_msa_source}" \
      --output "${binder_msa_path}" \
      --query "${binder_seq_clean}"
  elif [[ -n "${binder_msa_source}" && -s "${binder_msa_source}" && "${changed_count}" == "0" ]] && \
       is_openfold_msa_path_compatible "${binder_msa_source}"; then
    binder_msa_path="${binder_msa_source}"
  else
    write_single_seq_a3m "${binder_seq_clean}" "${binder_msa_path}"
  fi
  use_server="$(build_openfold_query_json "${input_yaml}" "${binder_seq_clean}" "${query_name}" "${query_json}" "${target_msa_path}" "${binder_msa_path}")"
  write_openfold_runner_yaml "${runner_yaml}"

  # Avoid interactive checkpoint prompts by ensuring weights are present first.
  ensure_openfold_checkpoint_noninteractive

  source "${OPENFOLD_VENV}/bin/activate"
  set +e
  OPENFOLD_CACHE="${OPENFOLD_CACHE_DIR}" KMP_USE_SHM=0 "${OPENFOLD_CLI}" predict \
    --query_json "${query_json}" \
    --output_dir "${out_dir}" \
    --inference_ckpt_path "${OPENFOLD_CHECKPOINT_PATH}" \
    --runner_yaml "${runner_yaml}" \
    --use_msa_server "${use_server}" \
    "${OPENFOLD_EXTRA_FLAGS[@]}" \
    >"${predict_log}" 2>&1
  rc=$?
  set -e
  deactivate || true
  if [[ "${rc}" -ne 0 ]]; then
    echo "ERROR: OpenFold prediction failed (rc=${rc}) for ${input_yaml}" >&2
    tail -n 80 "${predict_log}" >&2 || true
    die "OpenFold prediction failed (rc=${rc}) for ${input_yaml}"
  fi

  local leaf conf struct
  leaf="${out_dir}/${query_name}/seed_42"
  [[ -d "$leaf" ]] || leaf="$(find "${out_dir}" -maxdepth 4 -type d -name 'seed_*' | sort | head -n 1 || true)"
  if [[ -z "$leaf" || ! -d "$leaf" ]]; then
    echo "ERROR: OpenFold seed output not found in ${out_dir}" >&2
    tail -n 120 "${predict_log}" >&2 || true
    die "OpenFold seed output not found in ${out_dir}"
  fi

  conf="$(find "${leaf}" -maxdepth 1 -type f -name '*_confidences_aggregated.json' | sort | head -n 1 || true)"
  struct="$(find "${leaf}" -maxdepth 1 -type f \( -name '*_model.cif' -o -name '*_model.pdb' \) | sort | head -n 1 || true)"
  [[ -n "$struct" ]] || die "OpenFold structure not found in ${leaf}"

  mkdir -p "${pred_min}"
  if [[ -n "$conf" ]]; then cp -f "$conf" "${pred_min}/confidence.json"; fi
  if [[ "${struct##*.}" == "cif" ]]; then
    cp -f "$struct" "${pred_min}/model_0.cif"
  else
    cp -f "$struct" "${pred_min}/model_0.pdb"
  fi

  local iptm plddt
  iptm="nan"; plddt="nan"
  if [[ -f "${pred_min}/confidence.json" ]]; then
    IFS=',' read -r iptm plddt <<< "$(extract_metrics_from_conf_json "${pred_min}/confidence.json")"
    echo "$iptm" > "${pred_min}/iptm.txt" || true
  fi

  echo "${struct}|${conf}|${iptm}|${plddt}"
}

ensure_openfold_checkpoint_noninteractive() {
  mkdir -p "${OPENFOLD_CACHE_DIR}"
  "${OPENFOLD_VENV}/bin/python" - "${OPENFOLD_CHECKPOINT_PATH}" <<'PY'
import pathlib
import sys

import boto3
from botocore import UNSIGNED
from botocore.config import Config

target = pathlib.Path(sys.argv[1]).expanduser()
target.parent.mkdir(parents=True, exist_ok=True)

# Runtime prediction must remain offline once the complete checkpoint has been
# installed. The released checkpoint is ~2.13 GiB; anything smaller is treated
# as incomplete and validated/redownloaded against S3 below.
if target.exists() and target.stat().st_size >= 2_000_000_000:
    print(f"OpenFold checkpoint ready: {target}", file=sys.stderr)
    raise SystemExit(0)

bucket = "openfold"
key = "openfold3_params/of3_ft3_v1.pt"
s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
remote_size = int(s3.head_object(Bucket=bucket, Key=key)["ContentLength"])

if target.exists() and target.stat().st_size == remote_size:
    print(f"OpenFold checkpoint ready: {target}", file=sys.stderr)
    raise SystemExit(0)

tmp = target.with_suffix(target.suffix + ".part")
if tmp.exists():
    tmp.unlink()

print(f"Downloading OpenFold checkpoint to {target} ({remote_size / (1024**3):.2f} GB)...", file=sys.stderr)
s3.download_file(bucket, key, str(tmp))
downloaded_size = tmp.stat().st_size
if downloaded_size != remote_size:
    tmp.unlink(missing_ok=True)
    raise RuntimeError(
        f"OpenFold checkpoint download incomplete: expected {remote_size}, got {downloaded_size}"
    )

tmp.replace(target)
print(f"OpenFold checkpoint ready: {target}", file=sys.stderr)
PY
}

make_calibration_binder_sequence() {
  local predictor="$1"
  local cal_dir="$2"
  local report_name="${3:-nanobody_seed_calibration.json}"

  if [[ "${SCAFFOLD_FROM_TEMPLATE}" -eq 1 ]]; then
    local scaffold_seq
    scaffold_seq="$(extract_binder_sequence_from_yaml "${TEMPLATE_YAML}" "${ANTIFOLD_NANOBODY_CHAIN}")"
    [[ -n "${scaffold_seq}" ]] || die "Template chain ${ANTIFOLD_NANOBODY_CHAIN} sequence is empty; calibration requires a concrete scaffold sequence."

    if [[ "${WORKFLOW}" == "nanobody" && "${NANOBODY_SEED_MODE}" == "cdr-random" ]]; then
      generate_nanobody_seed_seq "${scaffold_seq}" "${NANOBODY_SEED_CDRS}" "${ANTIFOLD_SEED}" "${cal_dir}/${report_name}"
    else
      printf '%s\n' "${scaffold_seq}"
    fi
  else
    # Generic (non-scaffold) mode still calibrates with the longest binder in
    # the configured range.
    generate_random_binder_seq "${BINDER_MAX_LEN}" "${BINDER_MAX_LEN}" "${BINDER_PERCENT_X}" "${HELIX_KILL}" "${NEGATIVE_HELIX_CONSTANT}" "${LOOP_KILL}" "${predictor}" "${BINDER_RANDOM_SEED}"
  fi
}

run_predictor_calibration_once() {
  local predictor="$1"
  local target_msa_path="$2"
  local cal_dir cal_yaml cal_seq cal_target_msa cal_binder_msa qname result
  cal_dir="${EXPT_ROOT}/_calibration/cycle_00"
  cal_yaml="${cal_dir}/boltz_input.yaml"
  qname="calibration_input"
  mkdir -p "${cal_dir}"

  # Nanobody calibration preserves the fixed scaffold and only masks selected
  # CDRs. Protein workflow calibration uses either the concrete fixed binder or
  # the maximum configured random-binder length.
  cal_seq="$(make_calibration_binder_sequence "${predictor}" "${cal_dir}" "nanobody_seed_calibration.json")"
  printf '%s\n' "${#cal_seq}" > "${cal_dir}/calibration_binder_length.txt"
  {
    printf 'workflow\t%s\n' "${WORKFLOW}"
    printf 'predictor\t%s\n' "${predictor}"
    printf 'binder_length\t%s\n' "${#cal_seq}"
    printf 'target_length\t%s\n' "${TARGET_TOTAL_SEQUENCE_LENGTH}"
    printf 'target_chains\t%s\n' "${TARGET_CHAIN_COUNT}"
  } > "${cal_dir}/calibration_context.tsv"
  cal_target_msa="$(pick_target_msa_for_predictor "${target_msa_path}" "${predictor}")"
  cal_binder_msa="$(make_masked_nanobody_scaffold_msa "${cal_seq}" "${cal_dir}/nanobody_scaffold_masked.a3m" "${predictor}")"
  make_yaml_with_binder_sequence "${TEMPLATE_YAML}" "${cal_yaml}" "${cal_seq}" "${cal_target_msa}" "${predictor}" "${cal_binder_msa}" "design"

  case "${predictor}" in
    boltz)
      local peak_file use_pot
      peak_file="${EXPT_ROOT}/calibration_peak_effective_mb.txt"
      use_pot=0
      if [[ "${BOLTZ_USE_POTENTIALS_DEFAULT}" -eq 1 ]]; then
        use_pot=1
      fi
      if ! run_boltz_predict_monitored "${cal_yaml}" "${cal_dir}/boltz" "${peak_file}" "${use_pot}"; then
        die "Calibration Boltz run failed."
      fi
      PEAK_EFFECTIVE_MB="$(cat "${peak_file}" 2>/dev/null || echo 0)"
      PEAK_RSS_MB="${MONITOR_PEAK_RSS_MB:-0}"
      PEAK_FOOTPRINT_MB="${MONITOR_PEAK_FOOTPRINT_MB:-0}"
      PEAK_SYS_DELTA_MB="${MONITOR_PEAK_SYS_DELTA_MB:-0}"
      [[ -n "${PEAK_EFFECTIVE_MB}" && "${PEAK_EFFECTIVE_MB}" != "0" ]] || PEAK_EFFECTIVE_MB="${MONITOR_PEAK_EFFECTIVE_MB:-0}"
      echo "${PEAK_RSS_MB}" > "${EXPT_ROOT}/calibration_peak_rss_mb.txt"
      write_calibration_memory_metrics "${EXPT_ROOT}/calibration_memory_metrics.csv"
      ;;
    intellifold)
      local peak_file
      peak_file="${EXPT_ROOT}/calibration_peak_effective_mb.txt"
      if ! run_intellifold_predict_monitored "${cal_yaml}" "${cal_dir}/intellifold" "${peak_file}"; then
        die "Calibration IntelliFold run failed."
      fi
      PEAK_EFFECTIVE_MB="$(cat "${peak_file}" 2>/dev/null || echo 0)"
      PEAK_RSS_MB="${MONITOR_PEAK_RSS_MB:-0}"
      PEAK_FOOTPRINT_MB="${MONITOR_PEAK_FOOTPRINT_MB:-0}"
      PEAK_SYS_DELTA_MB="${MONITOR_PEAK_SYS_DELTA_MB:-0}"
      [[ -n "${PEAK_EFFECTIVE_MB}" && "${PEAK_EFFECTIVE_MB}" != "0" ]] || PEAK_EFFECTIVE_MB="${MONITOR_PEAK_EFFECTIVE_MB:-0}"
      echo "${PEAK_RSS_MB}" > "${EXPT_ROOT}/calibration_peak_rss_mb.txt"
      write_calibration_memory_metrics "${EXPT_ROOT}/calibration_memory_metrics.csv"
      ;;
    *)
      result="$(run_predictor_once "${predictor}" "${cal_yaml}" "${cal_seq}" "${qname}" "${cal_dir}" "${target_msa_path}" "design")"
      [[ -n "${result}" ]] || die "Calibration prediction produced no output."
      ;;
  esac
}

run_predictor_once() {
  local predictor="$1"
  local cycle_yaml="$2"
  local binder_seq="$3"
  local query_name="$4"
  local cycle_dir="$5"
  local target_msa_path="$6"
  local phase="${7:-design}"

  local pred_min
  pred_min="${cycle_dir}/pred_min"

  case "${predictor}" in
    boltz)
      local _use_pot=0
      if [[ "${phase}" == "design" && "${BOLTZ_USE_POTENTIALS_DEFAULT}" -eq 1 ]]; then
        _use_pot=1
      fi
      run_predict_boltz "${cycle_yaml}" "${cycle_dir}/boltz" "${pred_min}" "${_use_pot}"
      ;;
    intellifold)
      run_predict_intellifold "${cycle_yaml}" "${cycle_dir}/intellifold" "${pred_min}"
      ;;
    protenix-v2|protenix-mini|protenix-constraint-v0.5)
      run_predict_protenix "${predictor}" "${cycle_yaml}" "${cycle_dir}/${predictor}" "${pred_min}"
      ;;
    openfold-3-mlx)
      run_predict_openfold "${cycle_yaml}" "${binder_seq}" "${query_name}" "${cycle_dir}/openfold3" "${pred_min}" "${target_msa_path}"
      ;;
    *)
      die "Unsupported predictor: ${predictor}"
      ;;
  esac
}

import_initial_cycle_structure() {
  local cycle_dir="$1"
  local expected_sequence="$2"
  local pred_min="${cycle_dir}/pred_min"
  local extension struct_out conf_out iptm plddt
  extension="$(printf '%s' "${INITIAL_STRUCTURE##*.}" | tr '[:upper:]' '[:lower:]')"
  mkdir -p "${pred_min}"
  struct_out="${pred_min}/model_0.${extension}"
  cp -f "${INITIAL_STRUCTURE}" "${struct_out}"

  "${BOLTZ_VENV}/bin/python" - \
    "${REPO_ROOT}" \
    "${struct_out}" \
    "${ANTIFOLD_NANOBODY_CHAIN}" \
    "${#expected_sequence}" <<'PY'
import sys
from pathlib import Path

root, structure, chain, expected_length = sys.argv[1:5]
sys.path.insert(0, root)
from score_motif_scaffolding import atom_index, load_atoms

atoms = load_atoms(Path(structure))
residues = {
    atom_index(atom, "auto")
    for atom in atoms
    if atom.chain_id == chain and atom_index(atom, "auto") is not None
}
if len(residues) != int(expected_length):
    raise SystemExit(
        "Imported structure/template binder length mismatch for "
        f"chain {chain}: structure={len(residues)}, sequence={expected_length}"
    )
PY

  conf_out=""
  iptm="nan"
  plddt="nan"
  if [[ -n "${INITIAL_CONFIDENCE_JSON}" ]]; then
    conf_out="${pred_min}/confidence.json"
    cp -f "${INITIAL_CONFIDENCE_JSON}" "${conf_out}"
    IFS=',' read -r iptm plddt <<< "$(extract_metrics_from_conf_json "${conf_out}")"
    [[ -n "${iptm:-}" ]] || iptm="nan"
    [[ -n "${plddt:-}" ]] || plddt="nan"
    printf '%s\n' "${iptm}" > "${pred_min}/iptm.txt"
  fi
  printf '%s|%s|%s|%s\n' "${struct_out}" "${conf_out}" "${iptm}" "${plddt}"
}

run_ligandmpnn_redesign() {
  local cycle_dir="$1"
  local struct_path="$2"
  local cycle_idx="$3"
  local fixed_residues="${4:-}"
  local redesigned_residues="${5:-}"
  local run_index="${6:-0}"
  cycle_dir="$(cd "${cycle_dir}" && pwd)"

  # Keep sampling reproducible while ensuring every run/cycle gets an
  # independent ProteinMPNN-family trajectory.
  local seed
  seed="$((LIGANDMPNN_SEED + run_index * 1000 + cycle_idx))"

  local input_struct
  input_struct="${struct_path}"

  if [[ "${struct_path##*.}" == "cif" && "${cycle_idx}" -eq 0 ]]; then
    local patched
    patched="${cycle_dir}/pred_min/model_0_UNKPATCH.cif"
    patch_cif_unk "${struct_path}" "${patched}" "${UNK_PATCH_MODE}" "${PREDICTOR}" "${ANTIFOLD_NANOBODY_CHAIN}"
    input_struct="${patched}"
  fi

  local lmpnn_input
  if [[ "${input_struct##*.}" == "cif" ]]; then
    lmpnn_input="${cycle_dir}/model_for_ligandmpnn.pdb"
    convert_cif_to_pdb "${input_struct}" "${lmpnn_input}"
  else
    lmpnn_input="${input_struct}"
    cp -f "${input_struct}" "${cycle_dir}/model_for_ligandmpnn.pdb" || true
  fi

  local temp
  local bias_aa
  local omit_aa
  if [[ "${cycle_idx}" -eq 0 ]]; then
    temp="${LIGAND_TEMP_CYCLE01}"
    bias_aa="${LIGAND_BIAS_AA_CYCLE01}"
  else
    temp="${LIGAND_TEMP_DEFAULT}"
    bias_aa="${LIGAND_BIAS_AA_DEFAULT}"
  fi
  bias_aa="$(compute_loopkill_mpnn_bias "${bias_aa}" "${LOOP_KILL}")"
  omit_aa="C"
  if python3 - "${LOOP_KILL}" <<'PY'
import sys
v=float(sys.argv[1])
raise SystemExit(0 if v >= 1.0 else 1)
PY
  then
    omit_aa="CP"
  fi

  local ligand_out
  ligand_out="${cycle_dir}/ligandmpnn"
  mkdir -p "${ligand_out}"
  printf '%s\n' "${seed}" > "${ligand_out}/seed.txt"

  local fixed_flags=()
  if [[ -n "${fixed_residues}" ]]; then
    fixed_flags=(--fixed_residues "${fixed_residues}")
  fi
  local redesigned_flags=()
  if [[ -n "${redesigned_residues}" ]]; then
    redesigned_flags=(--redesigned_residues "${redesigned_residues}")
  fi
  if [[ -n "${fixed_residues}" && -n "${redesigned_residues}" ]]; then
    die "Internal error: both fixed_residues and redesigned_residues were provided to LigandMPNN."
  fi

  source "${LIGAND_VENV}/bin/activate"
  pushd "${LIGANDMPNN_REPO}" >/dev/null
  # LigandMPNN can fail on macOS CPU when OpenMP shared memory is unavailable.
  if [[ -n "${bias_aa}" ]]; then
    KMP_USE_SHM=0 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 ${LIGANDMPNN_RUN} \
      --pdb_path "${lmpnn_input}" \
      --out_folder "${ligand_out}" \
      --temperature "${temp}" \
      --seed "${seed}" \
      --omit_AA "${omit_aa}" \
      --bias_AA "${bias_aa}" \
      ${fixed_flags[@]+"${fixed_flags[@]}"} \
      ${redesigned_flags[@]+"${redesigned_flags[@]}"} \
      "${LIGANDMPNN_MODEL_FLAGS[@]}" \
      "${LIGANDMPNN_EXTRA_FLAGS[@]}" \
      > "${ligand_out}/ligandmpnn.log" 2>&1
  else
    KMP_USE_SHM=0 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 ${LIGANDMPNN_RUN} \
      --pdb_path "${lmpnn_input}" \
      --out_folder "${ligand_out}" \
      --temperature "${temp}" \
      --seed "${seed}" \
      --omit_AA "${omit_aa}" \
      ${fixed_flags[@]+"${fixed_flags[@]}"} \
      ${redesigned_flags[@]+"${redesigned_flags[@]}"} \
      "${LIGANDMPNN_MODEL_FLAGS[@]}" \
      "${LIGANDMPNN_EXTRA_FLAGS[@]}" \
      > "${ligand_out}/ligandmpnn.log" 2>&1
  fi
  popd >/dev/null
  deactivate

  local seqs_dir fasta
  seqs_dir="${ligand_out}/seqs"
  [[ -d "$seqs_dir" ]] || die "LigandMPNN seqs dir not found: ${seqs_dir}"
  fasta="$(ls -1 "${seqs_dir}"/*.fa 2>/dev/null | head -n 1 || true)"
  [[ -n "$fasta" ]] || die "No LigandMPNN FASTA found in ${seqs_dir}"

  mkdir -p "${cycle_dir}/ligandmpnn_min"
  cp -f "$fasta" "${cycle_dir}/ligandmpnn_min/seqs.fa"

  extract_redesigned_sequence_from_fastas "${seqs_dir}"/*.fa
}

# Pick the highest-scoring chain-A design from a LASErMPNN designs.fasta.
# LASErMPNN's score is the mean log10 per-residue selection probability, so the
# maximum score is the most confident design.
select_best_lasermpnn_sequence() {
  python3 - "$1" <<'PY'
import sys, re
fasta = sys.argv[1]
best_seq, best_score = None, None
header, seq = None, []
def flush():
    global best_seq, best_score
    if header is None:
        return
    s = "".join(seq).strip()
    if not s:
        return
    m = re.search(r"score=(-?\d+(?:\.\d+)?)", header)
    score = float(m.group(1)) if m else float("-inf")
    if best_score is None or score > best_score:
        best_score, best_seq = score, s
for line in open(fasta):
    line = line.rstrip("\n")
    if line.startswith(">"):
        flush()
        header, seq = line, []
    elif line.strip():
        seq.append(line.strip())
flush()
if best_seq is None:
    raise SystemExit("No sequence found in LASErMPNN designs.fasta")
print(best_seq)
PY
}

run_lasermpnn_redesign() {
  local cycle_dir="$1"
  local struct_path="$2"
  local cycle_idx="$3"
  local fixed_residues="${4:-}"
  local redesigned_residues="${5:-}"
  local run_index="${6:-0}"
  cycle_dir="$(cd "${cycle_dir}" && pwd)"

  local seed
  seed="$((LASERMPNN_SEED + run_index * 1000 + cycle_idx))"

  # X-seeded designs: predictors emit UNK for masked positions. Normalize the
  # placeholders (cycle 0 only, matching the MPNN path) so LASErMPNN receives a
  # valid all-atom backbone. LASErMPNN designs on backbone coords + ligand, so
  # the patched identities are irrelevant to the redesigned positions.
  local input_struct="${struct_path}"
  if [[ "${struct_path##*.}" == "cif" && "${cycle_idx}" -eq 0 ]]; then
    local patched="${cycle_dir}/pred_min/model_0_UNKPATCH.cif"
    patch_cif_unk "${struct_path}" "${patched}" "${UNK_PATCH_MODE}" "${PREDICTOR}" "${ANTIFOLD_NANOBODY_CHAIN}"
    input_struct="${patched}"
  fi

  local laser_pdb_raw="${cycle_dir}/model_for_lasermpnn_raw.pdb"
  if [[ "${input_struct##*.}" == "cif" ]]; then
    convert_cif_to_pdb "${input_struct}" "${laser_pdb_raw}"
  else
    cp -f "${input_struct}" "${laser_pdb_raw}"
  fi

  local laser_out="${cycle_dir}/lasermpnn"
  mkdir -p "${laser_out}"
  printf '%s\n' "${seed}" > "${laser_out}/seed.txt"

  # Map NanoHunter's fixed/redesigned residue spec to LASErMPNN's B-factor mask.
  local pos_flags=()
  local fixbeta_flag=()
  if [[ -n "${redesigned_residues}" ]]; then
    pos_flags=(--designed-positions "$(residue_spec_to_positions "${redesigned_residues}")")
    fixbeta_flag=(--fix_beta)
  elif [[ -n "${fixed_residues}" ]]; then
    pos_flags=(--fixed-positions "$(residue_spec_to_positions "${fixed_residues}")")
    fixbeta_flag=(--fix_beta)
  else
    pos_flags=(--designed-positions all)
  fi

  # Automatic ligand protonation (SMILES-consistent H) + fix_beta masking.
  "${LASERMPNN_VENV}/bin/python" "${LASERMPNN_PREPARE}" \
    --in-pdb "${laser_pdb_raw}" \
    --out-pdb "${laser_out}/model_prepared.pdb" \
    --smiles "${LASERMPNN_LIGAND_SMILES}" \
    "${pos_flags[@]}" \
    > "${laser_out}/prepare.log" 2>&1 \
    || { sed 's/^/[lasermpnn-prepare] /' "${laser_out}/prepare.log" >&2; die "LASErMPNN input preparation failed (see ${laser_out}/prepare.log)"; }

  # LASErMPNN runs as a package module; sys.path[0] must be src/ (the parent of
  # the LASErMPNN repo dir) so `import LASErMPNN` resolves. CPU only on macOS.
  (
    cd "${LASERMPNN_REPO}/.." || exit 1
    KMP_USE_SHM=0 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    "${LASERMPNN_VENV}/bin/python" "${LASERMPNN_SEEDED_RUNNER}" "${seed}" \
      "${laser_out}/model_prepared.pdb" \
      "${laser_out}/designs" \
      "${LASERMPNN_NUM_SEQ}" \
      --device "${LASERMPNN_DEVICE}" \
      --model_weights_path "${LASERMPNN_WEIGHTS}" \
      --sequence_temp "${LASERMPNN_SEQ_TEMP}" \
      --first_shell_sequence_temp "${LASERMPNN_FS_TEMP}" \
      --disabled_residues "X,C" \
      --output_fasta_only --silent \
      ${fixbeta_flag[@]+"${fixbeta_flag[@]}"} \
      ${LASERMPNN_EXTRA_FLAGS[@]+"${LASERMPNN_EXTRA_FLAGS[@]}"}
  ) > "${laser_out}/lasermpnn.log" 2>&1 \
    || { sed 's/^/[lasermpnn] /' "${laser_out}/lasermpnn.log" >&2; die "LASErMPNN inference failed (see ${laser_out}/lasermpnn.log)"; }

  local fasta="${laser_out}/designs/designs.fasta"
  [[ -f "${fasta}" ]] || die "LASErMPNN produced no designs.fasta in ${laser_out}/designs"

  mkdir -p "${cycle_dir}/lasermpnn_min"
  cp -f "${fasta}" "${cycle_dir}/lasermpnn_min/seqs.fa"

  select_best_lasermpnn_sequence "${fasta}"
}

run_antifold_redesign() {
  local cycle_dir="$1"
  local struct_path="$2"
  local cycle_idx="$3"
  local run_index="${4:-0}"
  local exact_positions="$5"
  local base_sequence="$6"
  cycle_dir="$(cd "${cycle_dir}" && pwd)"

  local input_struct
  input_struct="${struct_path}"

  if [[ "${struct_path##*.}" == "cif" && "${cycle_idx}" -eq 0 ]]; then
    local patched
    patched="${cycle_dir}/pred_min/model_0_UNKPATCH.cif"
    patch_cif_unk "${struct_path}" "${patched}" "${UNK_PATCH_MODE}" "${PREDICTOR}" "${ANTIFOLD_NANOBODY_CHAIN}"
    input_struct="${patched}"
  fi

  local antifold_input
  if [[ "${input_struct##*.}" == "cif" ]]; then
    antifold_input="${cycle_dir}/model_for_antifold.pdb"
    convert_cif_to_pdb "${input_struct}" "${antifold_input}"
  else
    antifold_input="${cycle_dir}/model_for_antifold.pdb"
    cp -f "${input_struct}" "${antifold_input}"
  fi

  local temp
  if [[ "${cycle_idx}" -eq 0 ]]; then
    temp="${LIGAND_TEMP_CYCLE01}"
  else
    temp="${LIGAND_TEMP_DEFAULT}"
  fi

  local antifold_out antifold_log antigen_chain antigen_lower seed
  antifold_out="${cycle_dir}/antifold"
  antifold_log="${antifold_out}/antifold.log"
  mkdir -p "${antifold_out}"

  antigen_chain="${ANTIFOLD_ANTIGEN_CHAIN}"
  antigen_lower="$(printf '%s' "${antigen_chain}" | tr '[:upper:]' '[:lower:]')"
  case "${antigen_lower}" in
    auto) antigen_chain="${TARGET_CHAIN_ID:-}" ;;
    none|no|null|off) antigen_chain="" ;;
  esac
  if [[ "${antigen_chain}" == "${ANTIFOLD_NANOBODY_CHAIN}" ]]; then
    antigen_chain=""
  fi

  seed="$((ANTIFOLD_SEED + run_index * 1000 + cycle_idx))"

  local antigen_flags=()
  if [[ -n "${antigen_chain}" ]]; then
    antigen_flags=(--antigen_chain "${antigen_chain}")
  fi
  source "${ANTIFOLD_VENV}/bin/activate"
  pushd "${ANTIFOLD_REPO}" >/dev/null
  set +e
  PYTORCH_ENABLE_MPS_FALLBACK=1 KMP_USE_SHM=0 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 ${ANTIFOLD_RUN} \
    --pdb_file "${antifold_input}" \
    --out_dir "${antifold_out}" \
    --nanobody_chain "${ANTIFOLD_NANOBODY_CHAIN}" \
    ${antigen_flags[@]+"${antigen_flags[@]}"} \
    --regions "${ANTIFOLD_REGIONS}" \
    --num_seq_per_target 0 \
    --sampling_temp "${temp}" \
    --batch_size "${ANTIFOLD_BATCH_SIZE}" \
    --num_threads "${ANTIFOLD_NUM_THREADS}" \
    --seed "${seed}" \
    ${ANTIFOLD_EXTRA_FLAGS[@]+"${ANTIFOLD_EXTRA_FLAGS[@]}"} \
    > "${antifold_log}" 2>&1
  local rc=$?
  set -e
  popd >/dev/null
  deactivate

  if [[ "${rc}" -ne 0 ]]; then
    echo "ERROR: AntiFold redesign failed (rc=${rc}) for ${antifold_input}" >&2
    tail -n 80 "${antifold_log}" >&2 || true
    die "AntiFold redesign failed (rc=${rc}) for ${antifold_input}"
  fi

  local logits_csv exact_fasta exact_sequence
  logits_csv="$(find "${antifold_out}" -maxdepth 1 -type f -name '*.csv' | sort | head -n 1 || true)"
  [[ -n "${logits_csv}" ]] || die "No AntiFold logits CSV found in ${antifold_out}"
  exact_fasta="${antifold_out}/antifold_exact_positions.fasta"
  local sampler_flags=()
  if [[ "${ANTIFOLD_LIMIT_VARIATION}" -eq 1 ]]; then
    sampler_flags=(--limit-variation)
  fi
  exact_sequence="$(
    "${ANTIFOLD_VENV}/bin/python" "${ANTIFOLD_EXACT_SAMPLER}" \
      --logits-csv "${logits_csv}" \
      --chain "${ANTIFOLD_NANOBODY_CHAIN}" \
      --base-sequence "${base_sequence}" \
      --positions "${exact_positions}" \
      --temperature "${temp}" \
      --seed "${seed}" \
      --num-sequences "${ANTIFOLD_NUM_SEQ_PER_TARGET}" \
      --omit-aa C \
      ${sampler_flags[@]+"${sampler_flags[@]}"} \
      --output-fasta "${exact_fasta}"
  )"
  [[ -n "${exact_sequence}" ]] || die "Exact-position AntiFold sampling produced an empty sequence"

  mkdir -p "${cycle_dir}/antifold_min"
  cp -f "${exact_fasta}" "${cycle_dir}/antifold_min/seqs.fasta"
  cp -f "${logits_csv}" "${cycle_dir}/antifold_min/logits.csv"

  echo "${exact_sequence}"
}

run_sequence_redesign() {
  local cycle_dir="$1"
  local struct_path="$2"
  local cycle_idx="$3"
  local fixed_residues="${4:-}"
  local redesigned_residues="${5:-}"
  local run_index="${6:-0}"
  local current_sequence="${7:-}"
  local antifold_exact_positions="${8:-}"

  local candidate_sequence
  case "${SEQUENCE_DESIGNER}" in
    antifold)
      candidate_sequence="$(run_antifold_redesign "${cycle_dir}" "${struct_path}" "${cycle_idx}" "${run_index}" "${antifold_exact_positions}" "${current_sequence}")"
      ;;
    proteinmpnn|solublempnn|ligandmpnn|abmpnn)
      candidate_sequence="$(run_ligandmpnn_redesign "${cycle_dir}" "${struct_path}" "${cycle_idx}" "${fixed_residues}" "${redesigned_residues}" "${run_index}")"
      ;;
    lasermpnn)
      candidate_sequence="$(run_lasermpnn_redesign "${cycle_dir}" "${struct_path}" "${cycle_idx}" "${fixed_residues}" "${redesigned_residues}" "${run_index}")"
      ;;
    *)
      die "Unsupported sequence designer: ${SEQUENCE_DESIGNER}"
      ;;
  esac

  candidate_sequence="$(python3 - "${candidate_sequence}" "${current_sequence}" <<'PY'
import sys
candidate = "".join(sys.argv[1].split()).upper()
previous = "".join(sys.argv[2].split()).upper()
invalid = sorted(set(candidate) - set("ACDEFGHIKLMNPQRSTVWY"))
if invalid:
    raise SystemExit(
        "Inverse-folding handoff contained non-standard or diagnostic characters: "
        + ",".join(repr(value) for value in invalid)
    )
if previous and len(candidate) != len(previous):
    raise SystemExit(
        f"Inverse-folding changed binder length from {len(previous)} to {len(candidate)}"
    )
if not candidate:
    raise SystemExit("Inverse-folding returned an empty binder sequence")
print(candidate)
PY
)"

  if [[ -n "${redesigned_residues}" && -n "${current_sequence}" ]]; then
    apply_nanobody_redesign_guard "${current_sequence}" "${candidate_sequence}" "${redesigned_residues}"
  else
    echo "${candidate_sequence}"
  fi
}

export_cif() {
  local run_tag="$1"
  local cycle_idx="$2"
  local pred_min="$3"
  local iptm="$4"

  local cycle_tag
  cycle_tag="$(printf "cycle_%02d" "$cycle_idx")"

  local cif_path="${pred_min}/model_0.cif"
  [[ -f "$cif_path" ]] || return 0

  local base_name="${run_tag}_${cycle_tag}_model_0.cif"
  cp -f "$cif_path" "${CIFS_ALL_DIR}/${base_name}"

  if [[ "$cycle_idx" -eq 0 ]]; then
    return 0
  fi

  if is_float "$iptm" && float_ge "$iptm" "$IPTM_THRESHOLD"; then
    cp -f "$cif_path" "${CIFS_PASS_DIR}/${base_name}"
  fi
}

# ---------------------------------------------------------------------------
# Resume support
#
# A cycle is "complete" when its normalised prediction exists, which is the same
# contract every predictor backend satisfies (pred_min/model_0.cif|pdb). The
# per-cycle input YAML is the authoritative record of which binder sequence that
# cycle used, so a resumed run recovers sequences from disk rather than replaying
# the stochastic seeding/redesign steps that produced them.
# ---------------------------------------------------------------------------

cycle_prediction_complete() {
  local cycle_dir="$1"
  [[ -f "${cycle_dir}/pred_min/model_0.cif" || -f "${cycle_dir}/pred_min/model_0.pdb" ]]
}

cycle_structure_path() {
  local cycle_dir="$1"
  if [[ -f "${cycle_dir}/pred_min/model_0.cif" ]]; then
    printf '%s\n' "${cycle_dir}/pred_min/model_0.cif"
  elif [[ -f "${cycle_dir}/pred_min/model_0.pdb" ]]; then
    printf '%s\n' "${cycle_dir}/pred_min/model_0.pdb"
  fi
}

# Sequence a completed cycle actually used, read back from its input YAML.
binder_seq_from_cycle_yaml() {
  local cycle_yaml="$1"
  [[ -f "${cycle_yaml}" ]] || return 1
  local seq
  seq="$(extract_binder_sequence_from_yaml "${cycle_yaml}" "${ANTIFOLD_NANOBODY_CHAIN}" 2>/dev/null || true)"
  seq="$(printf '%s' "${seq}" | tr -d '[:space:]')"
  [[ -n "${seq}" ]] || return 1
  printf '%s\n' "${seq}"
}

# Highest cycle index c such that cycles 0..c are all complete, or -1 if none.
last_complete_cycle() {
  local run_root="$1"
  local n_cycles="$2"
  local cycle last=-1
  for cycle in $(seq 0 "${n_cycles}"); do
    if cycle_prediction_complete "${run_root}/$(printf 'cycle_%02d' "${cycle}")"; then
      last="${cycle}"
    else
      break
    fi
  done
  printf '%s\n' "${last}"
}

wait_for_slot() {
  local limit="$1"
  while true; do
    local running
    running="$(jobs -pr | wc -l | awk '{print $1}')"
    if (( running < limit )); then
      break
    fi
    sleep 0.2
  done
}

initialize_cycle_wave_designs() {
  # Generic protein design uses the same cycle-wave state contract as the
  # nanobody path, but redesigns the complete binder and therefore has no CDR
  # position mask.  Keeping this branch separate avoids weakening the exact-CDR
  # safeguards below.
  if [[ "${WORKFLOW}" == "protein" ]]; then
    local run_index run_tag run_root current_seq seed_value scaffold_seq=""
    if [[ "${SCAFFOLD_FROM_TEMPLATE}" -eq 1 ]]; then
      scaffold_seq="$(extract_binder_sequence_from_yaml "${TEMPLATE_YAML}" "${ANTIFOLD_NANOBODY_CHAIN}")"
      [[ -n "${scaffold_seq}" ]] || die "Cycle-wave fixed protein design requires a concrete chain ${ANTIFOLD_NANOBODY_CHAIN} sequence."
    fi
    for run_index in $(seq 1 "${N_RUNS}"); do
      run_tag="$(printf "run_%03d" "${run_index}")"
      run_root="${EXPT_ROOT}/${run_tag}"
      mkdir -p "${run_root}"
      echo "cycle,iptm,complex_plddt,confidence_json,structure_path,binder_sequence" > "${run_root}/metrics_per_cycle.csv"
      echo "run,cycle,iptm,complex_plddt,binder_sequence,structure_path,confidence_json" > "${run_root}/rows.csv"
      echo "cycle,start_ts,end_ts,duration_sec" > "${run_root}/timing_cycles.csv"
      : > "${run_root}/nanobody_exact_residues.txt"
      : > "${run_root}/nanobody_antifold_positions.txt"
      if [[ "${RESUME}" -ne 1 || ! -s "${run_root}/run_start_epoch.txt" ]]; then
        printf '%s\n' "$(now_epoch)" > "${run_root}/run_start_epoch.txt"
      fi
      if [[ -n "${scaffold_seq}" ]]; then
        current_seq="${scaffold_seq}"
      else
        seed_value=""
        if [[ -n "${BINDER_RANDOM_SEED}" ]]; then
          seed_value="$((BINDER_RANDOM_SEED + run_index))"
        fi
        current_seq="$(generate_random_binder_seq \
          "${BINDER_MIN_LEN}" "${BINDER_MAX_LEN}" "${BINDER_PERCENT_X}" \
          "${HELIX_KILL}" "${NEGATIVE_HELIX_CONSTANT}" "${LOOP_KILL}" "${PREDICTOR}" "${seed_value}")"
      fi
      [[ -n "${current_seq}" ]] || die "Cycle-wave protein initialization produced an empty sequence for ${run_tag}."
      printf '%s\n' "${current_seq}" > "${run_root}/state_current_seq.txt"
      echo ">>> ${run_tag}: cycle-wave protein binder initialized (length=${#current_seq})"
    done
    return 0
  fi

  local scaffold_seq nanobody_exact_residues nanobody_antifold_positions
  scaffold_seq="$(extract_binder_sequence_from_yaml "${TEMPLATE_YAML}" "${ANTIFOLD_NANOBODY_CHAIN}")"
  [[ -n "${scaffold_seq}" ]] || die "Cycle-wave scheduling requires a concrete scaffold sequence on chain ${ANTIFOLD_NANOBODY_CHAIN}."

  local cdr_explicit_flags=()
  if [[ "$(printf '%s' "${NANOBODY_SEED_CDR_RANGES}" | tr '[:upper:]' '[:lower:]')" != "auto" ]]; then
    cdr_explicit_flags=(--explicit "${NANOBODY_SEED_CDR_RANGES}")
  fi
  nanobody_exact_residues="$(python3 "${REPO_ROOT}/scripts/nanobody_cdrs.py" \
    --seq "${scaffold_seq}" \
    --chain "${ANTIFOLD_NANOBODY_CHAIN}" \
    --cdrs "${ANTIFOLD_REGIONS}" \
    --catalog "${REPO_ROOT}/examples/nanobody_scaffolds/catalog.tsv" \
    ${cdr_explicit_flags[@]+"${cdr_explicit_flags[@]}"} \
    --emit residues)" \
    || die "Cycle-wave CDR detection failed for chain ${ANTIFOLD_NANOBODY_CHAIN}."
  [[ -n "${nanobody_exact_residues}" ]] || die "Cycle-wave CDR detection returned no residues."
  nanobody_antifold_positions="$(residue_spec_to_positions "${nanobody_exact_residues}")"

  local run_index run_tag run_root current_seq seed_value
  for run_index in $(seq 1 "${N_RUNS}"); do
    run_tag="$(printf "run_%03d" "${run_index}")"
    run_root="${EXPT_ROOT}/${run_tag}"
    mkdir -p "${run_root}"
    echo "cycle,iptm,complex_plddt,confidence_json,structure_path,binder_sequence" > "${run_root}/metrics_per_cycle.csv"
    echo "run,cycle,iptm,complex_plddt,binder_sequence,structure_path,confidence_json" > "${run_root}/rows.csv"
    echo "cycle,start_ts,end_ts,duration_sec" > "${run_root}/timing_cycles.csv"
    printf '%s\n' "${nanobody_exact_residues}" > "${run_root}/nanobody_exact_residues.txt"
    printf '%s\n' "${nanobody_antifold_positions}" > "${run_root}/nanobody_antifold_positions.txt"
    # Keep the original start stamp on resume so campaign timing stays meaningful.
    if [[ "${RESUME}" -ne 1 || ! -s "${run_root}/run_start_epoch.txt" ]]; then
      printf '%s\n' "$(now_epoch)" > "${run_root}/run_start_epoch.txt"
    fi

    if [[ "${NANOBODY_SEED_MODE}" == "cdr-random" ]]; then
      seed_value="$((ANTIFOLD_SEED + run_index * 1000))"
      current_seq="$(generate_nanobody_seed_seq \
        "${scaffold_seq}" \
        "${NANOBODY_SEED_CDRS}" \
        "${seed_value}" \
        "${run_root}/nanobody_seed_cycle00.json")"
    else
      current_seq="${scaffold_seq}"
    fi
    [[ -n "${current_seq}" ]] || die "Cycle-wave initialization produced an empty sequence for ${run_tag}."
    printf '%s\n' "${current_seq}" > "${run_root}/state_current_seq.txt"
    echo ">>> ${run_tag}: cycle-wave initialized with $(printf '%s' "${nanobody_exact_residues}" | wc -w | tr -d ' ') exact CDR residues"
  done
}

prepare_cycle_wave_input() {
  local run_index="$1"
  local cycle_idx="$2"
  local target_msa_path="$3"
  local run_tag run_root cycle_tag cycle_dir cycle_yaml current_seq
  run_tag="$(printf "run_%03d" "${run_index}")"
  run_root="${EXPT_ROOT}/${run_tag}"
  cycle_tag="$(printf "cycle_%02d" "${cycle_idx}")"
  cycle_dir="${run_root}/${cycle_tag}"
  cycle_yaml="${cycle_dir}/${run_tag}_${cycle_tag}.yaml"
  mkdir -p "${cycle_dir}"

  # Resume: adopt the recorded sequence for an already-predicted cycle and leave
  # its input YAML untouched, so record_cycle_wave_predictions pairs the right
  # sequence with the existing structure.
  if [[ "${RESUME}" -eq 1 ]] && cycle_prediction_complete "${cycle_dir}"; then
    local recovered_seq
    if recovered_seq="$(binder_seq_from_cycle_yaml "${cycle_yaml}")"; then
      printf '%s\n' "${recovered_seq}" > "${run_root}/state_current_seq.txt"
      printf '%s\n' "${cycle_yaml}"
      return 0
    fi
  fi

  current_seq="$(tr -d '[:space:]' < "${run_root}/state_current_seq.txt")"
  [[ -n "${current_seq}" ]] || die "Cycle-wave state sequence is empty for ${run_tag}."

  local target_msa_for_pred binder_msa_for_pred
  target_msa_for_pred="$(pick_target_msa_for_predictor "${target_msa_path}" "${PREDICTOR}")"
  binder_msa_for_pred="$(make_masked_nanobody_scaffold_msa \
    "${current_seq}" \
    "${cycle_dir}/nanobody_scaffold_masked.a3m" \
    "${PREDICTOR}")"
  make_yaml_with_binder_sequence \
    "${TEMPLATE_YAML}" \
    "${cycle_yaml}" \
    "${current_seq}" \
    "${target_msa_for_pred}" \
    "${PREDICTOR}" \
    "${binder_msa_for_pred}" \
    "design"
  printf '%s\n' "${cycle_yaml}"
}

RESIDENT_QUEUE=""
RESIDENT_PID=""
RESIDENT_LOG=""

start_resident_predictor() {
  [[ "${DESIGN_SCHEDULER}" == "resident" ]] || return 0
  local wave_root="${EXPT_ROOT}/_cycle_wave"
  local session_tag config_path worker_python resident_model resident_samples
  local resident_use_msa="false"
  local resident_engine_args=()
  session_tag="session_$(date +%Y%m%dT%H%M%S)_$$"
  RESIDENT_QUEUE="${wave_root}/resident_sessions/${session_tag}"
  RESIDENT_LOG="${RESIDENT_QUEUE}/worker.log"
  config_path="${RESIDENT_QUEUE}/config.json"
  mkdir -p "${RESIDENT_QUEUE}"
  [[ -n "${TARGET_MSA_PATH}" ]] && resident_use_msa="true"

  resident_model="boltz2"
  resident_samples="${PREDICTOR_SAMPLES}"
  if [[ "${resident_samples}" == "auto" ]]; then
    resident_samples=1
    case "${PREDICTOR}" in protenix-v2|protenix-mini) resident_samples=5 ;; esac
  fi
  case "${PREDICTOR}" in
    boltz)
      worker_python="${BOLTZ_VENV}/bin/python"
      resident_engine_args=("${BOLTZ_EXTRA_FLAGS[@]}")
      ;;
    intellifold)
      worker_python="${INTELLIFOLD_VENV}/bin/python"
      resident_model="${INTELLIFOLD_MODEL}"
      resident_engine_args=("${INTELLIFOLD_EXTRA_FLAGS[@]}")
      ;;
    protenix-v2)
      worker_python="${PROTENIX_VENV}/bin/python"
      resident_model="v2"
      ;;
    protenix-mini)
      worker_python="${PROTENIX_VENV}/bin/python"
      resident_model="mini"
      ;;
    protenix-constraint-v0.5)
      worker_python="${PROTENIX_CONSTRAINT_VENV}/bin/python"
      resident_model="constraint"
      ;;
    *) die "No resident worker is defined for ${PREDICTOR}." ;;
  esac

  python3 - "${config_path}" "${RESIDENT_QUEUE}" "${REPO_ROOT}" \
    "${PREDICTOR}" "${resident_model}" "${PREDICTOR_SEED}" \
    "${resident_samples}" "${BOLTZ_USE_POTENTIALS_DEFAULT}" \
    "${resident_use_msa}" "$$" \
    ${resident_engine_args[@]+"${resident_engine_args[@]}"} <<'PY'
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
payload = {
    "schema": 1,
    "queue": sys.argv[2],
    "root": sys.argv[3],
    "engine": sys.argv[4],
    "model": sys.argv[5],
    "seed": sys.argv[6],
    "samples": int(sys.argv[7]),
    "use_potentials": sys.argv[8] == "1",
    "use_msa": sys.argv[9].lower() == "true",
    "owner_pid": int(sys.argv[10]),
    "engine_args": sys.argv[11:],
}
temporary = path.with_suffix(".json.part")
temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
temporary.replace(path)
PY

  echo ">>> Resident ${PREDICTOR}: loading one campaign model (session ${session_tag})"
  # The one-thread BLAS/OpenMP policy is a measured IntelliFold optimization,
  # not a generic MPS setting. Applying it to Protenix made its forwards slower
  # and made the resident comparison less controlled.
  local resident_environment=("PYTORCH_ENABLE_MPS_FALLBACK=0")
  if [[ "${PREDICTOR}" == "intellifold" ]]; then
    resident_environment+=(
      "OMP_NUM_THREADS=${INTELLIFOLD_OMP_NUM_THREADS}"
      "VECLIB_MAXIMUM_THREADS=${INTELLIFOLD_VECLIB_MAXIMUM_THREADS}"
      "KMP_USE_SHM=0"
    )
  fi
  env "${resident_environment[@]}" \
    "${worker_python}" "${RESIDENT_PREDICTOR}" --config "${config_path}" \
    > "${RESIDENT_LOG}" 2>&1 &
  RESIDENT_PID="$!"

  local tick=0
  while [[ ! -s "${RESIDENT_QUEUE}/ready.json" ]]; do
    sleep 0.25
    tick=$((tick + 1))
    if (( tick % 120 == 0 )); then
      echo ">>> Resident ${PREDICTOR} still loading (elapsed=$((tick / 4))s)" >&2
    fi
    if (( tick >= 7200 )); then
      tail -n 160 "${RESIDENT_LOG}" >&2 || true
      die "Resident ${PREDICTOR} did not become ready within 30 minutes."
    fi
  done
  local ready_pid
  ready_pid="$(python3 - "${RESIDENT_QUEUE}/ready.json" <<'PY'
import json, sys
x=json.load(open(sys.argv[1]))
assert x.get("device") == "mps" and x.get("fallback") == 0
assert x.get("model_load_count") == 1
print(int(x["pid"]))
PY
)" || die "Resident ${PREDICTOR} produced an invalid readiness receipt."
  [[ "${ready_pid}" == "${RESIDENT_PID}" ]] || die "Resident readiness PID ${ready_pid} does not match child ${RESIDENT_PID}."
  kill -0 "${RESIDENT_PID}" 2>/dev/null || {
    tail -n 160 "${RESIDENT_LOG}" >&2 || true
    die "Resident ${PREDICTOR} exited immediately after readiness."
  }
  cp -f "${RESIDENT_QUEUE}/ready.json" "${wave_root}/resident_ready.json"
  echo "request_id,cycle,batch,batch_size,wall_seconds,model_load_count" > "${wave_root}/resident_requests.csv"
  echo ">>> Resident ${PREDICTOR}: ready on native MPS (pid=${RESIDENT_PID}, model_load_count=1)"
}

stop_resident_predictor() {
  [[ -n "${RESIDENT_QUEUE}" ]] || return 0
  python3 - "${RESIDENT_QUEUE}/stop.json" <<'PY'
import json, os, sys, time
from pathlib import Path
path=Path(sys.argv[1]); tmp=path.with_suffix(".json.part")
tmp.write_text(json.dumps({"requested_epoch": time.time(), "requester_pid": os.getpid()}) + "\n")
tmp.replace(path)
PY
  local tick=0
  while [[ ! -s "${RESIDENT_QUEUE}/stopped.json" ]]; do
    if [[ -n "${RESIDENT_PID}" ]] && ! kill -0 "${RESIDENT_PID}" 2>/dev/null; then
      break
    fi
    sleep 0.25
    tick=$((tick + 1))
    (( tick < 480 )) || break
  done
  if [[ ! -s "${RESIDENT_QUEUE}/stopped.json" ]]; then
    tail -n 160 "${RESIDENT_LOG}" >&2 || true
    die "Resident ${PREDICTOR} did not stop cleanly."
  fi
  set +e
  wait "${RESIDENT_PID}"
  local resident_rc=$?
  set -e
  [[ "${resident_rc}" -eq 0 ]] || die "Resident ${PREDICTOR} exited with status ${resident_rc}."
  cp -f "${RESIDENT_QUEUE}/stopped.json" "${EXPT_ROOT}/_cycle_wave/resident_stopped.json"
  RESIDENT_PID=""
  RESIDENT_QUEUE=""
}

submit_resident_predictor_request() {
  local cycle_idx="$1" batch_idx="$2" input_dir="$3" output_dir="$4" expected="$5"
  [[ -n "${RESIDENT_PID}" ]] || die "Resident predictor was not started."
  kill -0 "${RESIDENT_PID}" 2>/dev/null || {
    tail -n 160 "${RESIDENT_LOG}" >&2 || true
    die "Resident ${PREDICTOR} died before cycle ${cycle_idx} batch ${batch_idx}."
  }
  local request_id request_path response_path
  request_id="$(printf 'cycle_%02d_batch_%02d' "${cycle_idx}" "${batch_idx}")"
  request_path="${RESIDENT_QUEUE}/requests/request_${request_id}.json"
  response_path="${RESIDENT_QUEUE}/responses/request_${request_id}.json"
  python3 - "${request_path}" "${request_id}" "${input_dir}" "${output_dir}" "${expected}" <<'PY'
import hashlib, json, sys, time
from pathlib import Path
path=Path(sys.argv[1]); source=Path(sys.argv[3]).resolve()
files=sorted(source.glob("*.yaml"))
digest=hashlib.sha256()
for item in files:
    digest.update(item.name.encode()); digest.update(b"\0")
    digest.update(item.resolve().read_bytes()); digest.update(b"\0")
payload={"schema": 1, "request_id": sys.argv[2], "input_dir": str(source),
         "output_dir": str(Path(sys.argv[4]).resolve()), "expected_jobs": int(sys.argv[5]),
         "input_sha256": digest.hexdigest(), "submitted_epoch": time.time()}
path.parent.mkdir(parents=True, exist_ok=True)
tmp=path.with_suffix(".json.part"); tmp.write_text(json.dumps(payload, indent=2, sort_keys=True)+"\n"); tmp.replace(path)
PY
  local tick=0
  while [[ ! -s "${response_path}" ]]; do
    if ! kill -0 "${RESIDENT_PID}" 2>/dev/null; then
      tail -n 200 "${RESIDENT_LOG}" >&2 || true
      die "Resident ${PREDICTOR} died during ${request_id}."
    fi
    sleep 0.25
    tick=$((tick + 1))
    if (( tick % 240 == 0 )); then
      echo ">>> Resident ${PREDICTOR} ${request_id} still running (elapsed=$((tick / 4))s)" >&2
    fi
  done
  local receipt
  receipt="$(python3 - "${response_path}" "${request_id}" "${expected}" <<'PY'
import json, sys
x=json.load(open(sys.argv[1]))
if not x.get("ok"):
    raise SystemExit(x.get("error", "resident request failed"))
assert x.get("request_id") == sys.argv[2]
assert int(x.get("completed_jobs", -1)) == int(sys.argv[3])
assert int(x.get("model_load_count", -1)) == 1
print(f"{x['wall_seconds']},{x['model_load_count']}")
PY
)" || {
    tail -n 200 "${RESIDENT_LOG}" >&2 || true
    die "Resident ${PREDICTOR} returned an invalid response for ${request_id}."
  }
  echo "${request_id},${cycle_idx},${batch_idx},${expected},${receipt}" >> "${EXPT_ROOT}/_cycle_wave/resident_requests.csv"
}

run_cycle_wave_predictor_batch() {
  local cycle_idx="$1"
  local batch_idx="$2"
  local first_run="$3"
  local last_run="$4"
  local wave_root="${EXPT_ROOT}/_cycle_wave"
  local cycle_tag batch_tag batch_root input_dir yaml_input_dir output_dir log_path
  cycle_tag="$(printf "cycle_%02d" "${cycle_idx}")"
  batch_tag="$(printf "batch_%02d" "${batch_idx}")"
  batch_root="${wave_root}/${cycle_tag}/${batch_tag}"
  # Keep the historical basename `inputs`: Boltz and IntelliFold include that
  # basename in their output tree contracts.
  yaml_input_dir="${batch_root}/inputs"
  input_dir="${yaml_input_dir}"
  output_dir="${batch_root}/${PREDICTOR}"
  log_path="${batch_root}/predict.log"
  mkdir -p "${yaml_input_dir}" "${output_dir}"

  # Only fold runs that do not already have a prediction for this cycle. On a
  # resume this can empty the batch entirely, in which case the predictor (and
  # its model load) is skipped rather than invoked with no inputs.
  local run_index run_tag cycle_yaml
  local pending_runs=()
  for run_index in $(seq "${first_run}" "${last_run}"); do
    run_tag="$(printf "run_%03d" "${run_index}")"
    if [[ "${RESUME}" -eq 1 ]] && cycle_prediction_complete "${EXPT_ROOT}/${run_tag}/${cycle_tag}"; then
      continue
    fi
    cycle_yaml="${EXPT_ROOT}/${run_tag}/${cycle_tag}/${run_tag}_${cycle_tag}.yaml"
    [[ -f "${cycle_yaml}" ]] || die "Cycle-wave input missing: ${cycle_yaml}"
    cycle_yaml="$(cd "$(dirname "${cycle_yaml}")" && pwd)/$(basename "${cycle_yaml}")"
    ln -sfn "${cycle_yaml}" "${yaml_input_dir}/$(basename "${cycle_yaml}")"
    pending_runs+=("${run_index}")
  done

  if [[ "${#pending_runs[@]}" -eq 0 ]]; then
    echo ">>> ${cycle_tag} ${batch_tag}: all runs ${first_run}-${last_run} already predicted; skipping ${PREDICTOR}"
    return 0
  fi

  local start_ts end_ts duration rc
  start_ts="$(now_epoch)"
  if [[ "${DESIGN_SCHEDULER}" == "resident" ]]; then
    echo ">>> ${cycle_tag} ${batch_tag}: resident ${PREDICTOR} request for ${#pending_runs[@]} run(s) in ${first_run}-${last_run}"
  else
    echo ">>> ${cycle_tag} ${batch_tag}: ${PREDICTOR} model load for ${#pending_runs[@]} run(s) in ${first_run}-${last_run}"
  fi
  set +e
  if [[ "${DESIGN_SCHEDULER}" == "resident" ]]; then
    submit_resident_predictor_request \
      "${cycle_idx}" "${batch_idx}" "${input_dir}" "${output_dir}" "${#pending_runs[@]}"
    rc=$?
    cp -f "${RESIDENT_LOG}" "${log_path}" 2>/dev/null || true
  else
    case "${PREDICTOR}" in
    boltz)
      local use_potential_flags=()
      if [[ "${BOLTZ_USE_POTENTIALS_DEFAULT}" -eq 1 ]]; then
        use_potential_flags=(--use_potentials)
      fi
      source "${BOLTZ_VENV}/bin/activate"
      "${BOLTZ_CLI}" predict "${input_dir}" \
        --out_dir "${output_dir}" \
        "${BOLTZ_EXTRA_FLAGS[@]}" \
        ${use_potential_flags[@]+"${use_potential_flags[@]}"} \
        --override \
        > "${log_path}" 2>&1
      rc=$?
      deactivate || true
      ;;
    protenix-v2|protenix-mini|protenix-constraint-v0.5)
      local protenix_model="v2"
      local protenix_venv="${PROTENIX_VENV}"
      local protenix_model_dir="${PROTENIX_MODEL_DIR}"
      if [[ "${PREDICTOR}" == "protenix-mini" ]]; then
        protenix_model="mini"
      elif [[ "${PREDICTOR}" == "protenix-constraint-v0.5" ]]; then
        protenix_model="constraint"
        protenix_venv="${PROTENIX_CONSTRAINT_VENV}"
        protenix_model_dir="${PROTENIX_CONSTRAINT_MODEL_DIR}"
      fi
      local protenix_work_flags=(--seeds "${PREDICTOR_SEED}")
      if [[ "${PREDICTOR_SAMPLES}" != "auto" ]]; then
        protenix_work_flags+=(--samples "${PREDICTOR_SAMPLES}")
      fi
      PROTENIX_ROOT_DIR="${protenix_model_dir}" \
        "${protenix_venv}/bin/python" "${PROTENIX_ADAPTER}" \
          --inputs "${input_dir}" --output "${output_dir}" \
          --nanohunter-root "${REPO_ROOT}" --model "${protenix_model}" \
          "${protenix_work_flags[@]}" \
          > "${log_path}" 2>&1
      rc=$?
      ;;
    intellifold)
      source "${INTELLIFOLD_VENV}/bin/activate"
      if [[ "${CPU_ONLY}" -eq 1 ]]; then
        ACCELERATE_USE_CPU=true OMP_NUM_THREADS="${INTELLIFOLD_OMP_NUM_THREADS}" VECLIB_MAXIMUM_THREADS="${INTELLIFOLD_VECLIB_MAXIMUM_THREADS}" KMP_USE_SHM=0 python "${INTELLIFOLD_RUNNER}" "${input_dir}" \
          --out_dir "${output_dir}" \
          "${INTELLIFOLD_EXTRA_FLAGS[@]}" \
          > "${log_path}" 2>&1
      else
        OMP_NUM_THREADS="${INTELLIFOLD_OMP_NUM_THREADS}" VECLIB_MAXIMUM_THREADS="${INTELLIFOLD_VECLIB_MAXIMUM_THREADS}" KMP_USE_SHM=0 python "${INTELLIFOLD_RUNNER}" "${input_dir}" \
          --out_dir "${output_dir}" \
          "${INTELLIFOLD_EXTRA_FLAGS[@]}" \
          > "${log_path}" 2>&1
      fi
      rc=$?
      deactivate || true
      ;;
    openfold-3-mlx)
      local of_query_dir="${batch_root}/openfold_queries"
      local of_batch_query="${batch_root}/openfold_batch_query.json"
      local of_runner="${batch_root}/openfold_runner.yml"
      local of_yaml of_stem of_seq of_binder_msa of_target_msa of_need_server
      local of_query_files=()
      mkdir -p "${of_query_dir}"
      rc=0
      for run_index in "${pending_runs[@]}"; do
        run_tag="$(printf "run_%03d" "${run_index}")"
        of_stem="${run_tag}_${cycle_tag}"
        of_yaml="${EXPT_ROOT}/${run_tag}/${cycle_tag}/${of_stem}.yaml"
        of_seq="$(binder_seq_from_cycle_yaml "${of_yaml}")"
        of_binder_msa="${of_query_dir}/${of_stem}_binder/uniref90_hits.a3m"
        write_single_seq_a3m "${of_seq}" "${of_binder_msa}"
        of_target_msa="$(extract_chain_msa_from_yaml "${of_yaml}" "${TARGET_CHAIN_ID:-B}" || true)"
        if [[ -n "${of_target_msa}" && "${of_target_msa}" != /* ]]; then
          of_target_msa="$(dirname "${of_yaml}")/${of_target_msa}"
        fi
        of_need_server="$(build_openfold_query_json \
          "${of_yaml}" "${of_seq}" "${of_stem}" \
          "${of_query_dir}/${of_stem}.json" "${of_target_msa}" "${of_binder_msa}")" || { rc=$?; break; }
        if [[ "${of_need_server}" != "false" ]]; then
          echo "ERROR: cycle-wave OpenFold query ${of_stem} lacks a cached MSA." >&2
          rc=1
          break
        fi
        of_query_files+=("${of_query_dir}/${of_stem}.json")
      done
      if [[ "${rc}" -eq 0 ]]; then
        python3 "${REPO_ROOT}/scripts/merge_openfold_queries.py" \
          --output "${of_batch_query}" "${of_query_files[@]}" || rc=$?
      fi
      if [[ "${rc}" -eq 0 ]]; then
        write_openfold_runner_yaml "${of_runner}"
        ensure_openfold_checkpoint_noninteractive
        source "${OPENFOLD_VENV}/bin/activate"
        OPENFOLD_CACHE="${OPENFOLD_CACHE_DIR}" KMP_USE_SHM=0 "${OPENFOLD_CLI}" predict \
          --query_json "${of_batch_query}" \
          --output_dir "${output_dir}" \
          --inference_ckpt_path "${OPENFOLD_CHECKPOINT_PATH}" \
          --runner_yaml "${of_runner}" \
          --use_msa_server false \
          "${OPENFOLD_EXTRA_FLAGS[@]}" \
          > "${log_path}" 2>&1
        rc=$?
        deactivate || true
      fi
      ;;
    esac
  fi
  set -e
  end_ts="$(now_epoch)"
  duration="$(calc_duration "${start_ts}" "${end_ts}")"
  echo "${cycle_idx},${batch_idx},${#pending_runs[@]},${start_ts},${end_ts},${duration}" >> "${wave_root}/predictor_batches.csv"
  if [[ "${rc}" -ne 0 ]]; then
    tail -n 120 "${log_path}" >&2 || true
    die "Cycle-wave ${PREDICTOR} batch failed for ${cycle_tag}/${batch_tag}."
  fi

  local stem leaf conf struct pred_min predictor_dir iptm plddt
  for run_index in "${pending_runs[@]}"; do
    run_tag="$(printf "run_%03d" "${run_index}")"
    stem="${run_tag}_${cycle_tag}"
    pred_min="${EXPT_ROOT}/${run_tag}/${cycle_tag}/pred_min"
    predictor_dir="${EXPT_ROOT}/${run_tag}/${cycle_tag}/${PREDICTOR}"
    mkdir -p "${pred_min}" "${predictor_dir}"
    cp -f "${log_path}" "${predictor_dir}/predict.log"
    case "${PREDICTOR}" in
      boltz)
        annotate_boltz_ipsae \
          "${EXPT_ROOT}/${run_tag}/${cycle_tag}/${stem}.yaml" \
          "${output_dir}" "${log_path}"
        leaf="${output_dir}/boltz_results_inputs/predictions/${stem}"
        conf="$(find "${leaf}" -maxdepth 1 -type f -name 'confidence_*_model_0.json' | sort | head -n 1 || true)"
        struct="$(find "${leaf}" -maxdepth 1 -type f \( -name '*.cif' -o -name '*.pdb' \) | sort | head -n 1 || true)"
        ;;
      intellifold)
        leaf="${output_dir}/inputs/predictions/${stem}"
        conf="$(find "${leaf}" -maxdepth 1 -type f -name '*_summary_confidences.json' | sort | head -n 1 || true)"
        struct="$(find "${leaf}" -maxdepth 1 -type f \( -name '*.cif' -o -name '*.pdb' \) | sort | head -n 1 || true)"
        ;;
      protenix-v2|protenix-mini|protenix-constraint-v0.5)
        leaf="${output_dir}/${stem}/pred_min"
        conf="${leaf}/confidence.json"
        struct="${leaf}/model_0.cif"
        [[ -f "${conf}" ]] || conf=""
        [[ -f "${struct}" ]] || struct=""
        ;;
      openfold-3-mlx)
        leaf="${output_dir}/${stem}/seed_42"
        [[ -d "${leaf}" ]] || leaf="$(find "${output_dir}/${stem}" -maxdepth 2 -type d -name 'seed_*' | sort | head -n 1 || true)"
        conf="$(find "${leaf}" -maxdepth 1 -type f -name '*_confidences_aggregated.json' | sort | head -n 1 || true)"
        struct="$(find "${leaf}" -maxdepth 1 -type f \( -name '*_model.cif' -o -name '*_model.pdb' \) | sort | head -n 1 || true)"
        ;;
    esac
    [[ -n "${struct}" && -f "${struct}" ]] || die "Cycle-wave structure not found for ${stem} in ${leaf}."
    if [[ -n "${conf}" && "${conf}" != "${pred_min}/confidence.json" ]]; then
      cp -f "${conf}" "${pred_min}/confidence.json"
    fi
    if [[ "${struct}" == "${pred_min}/model_0.cif" || "${struct}" == "${pred_min}/model_0.pdb" ]]; then
      :
    elif [[ "${struct##*.}" == "cif" ]]; then
      cp -f "${struct}" "${pred_min}/model_0.cif"
    else
      cp -f "${struct}" "${pred_min}/model_0.pdb"
    fi
    iptm="nan"
    plddt="nan"
    if [[ -f "${pred_min}/confidence.json" ]]; then
      IFS=',' read -r iptm plddt <<< "$(extract_metrics_from_conf_json "${pred_min}/confidence.json")"
      printf '%s\n' "${iptm}" > "${pred_min}/iptm.txt"
    fi
    printf '%s\n' "${start_ts}" > "${pred_min}/wave_predict_start.txt"
    printf '%s\n' "${end_ts}" > "${pred_min}/wave_predict_end.txt"
    printf '%s\n' "${duration}" > "${pred_min}/wave_predict_duration.txt"
  done
}

record_cycle_wave_predictions() {
  local cycle_idx="$1"
  local cycle_tag run_index run_tag run_root cycle_dir current_seq
  local iptm plddt conf struct start_ts end_ts duration
  cycle_tag="$(printf "cycle_%02d" "${cycle_idx}")"
  for run_index in $(seq 1 "${N_RUNS}"); do
    run_tag="$(printf "run_%03d" "${run_index}")"
    run_root="${EXPT_ROOT}/${run_tag}"
    cycle_dir="${run_root}/${cycle_tag}"
    current_seq="$(tr -d '[:space:]' < "${run_root}/state_current_seq.txt")"
    conf="${cycle_dir}/pred_min/confidence.json"
    if [[ -f "${cycle_dir}/pred_min/model_0.cif" ]]; then
      struct="${cycle_dir}/pred_min/model_0.cif"
    else
      struct="${cycle_dir}/pred_min/model_0.pdb"
    fi
    iptm="nan"
    plddt="nan"
    if [[ -f "${conf}" ]]; then
      IFS=',' read -r iptm plddt <<< "$(extract_metrics_from_conf_json "${conf}")"
    fi
    start_ts="$(cat "${cycle_dir}/pred_min/wave_predict_start.txt")"
    end_ts="$(cat "${cycle_dir}/pred_min/wave_predict_end.txt")"
    duration="$(cat "${cycle_dir}/pred_min/wave_predict_duration.txt")"
    echo "${cycle_idx},${iptm},${plddt},${conf},${struct},${current_seq}" >> "${run_root}/metrics_per_cycle.csv"
    echo "${run_index},${cycle_idx},${iptm},${plddt},${current_seq},${struct},${conf}" >> "${run_root}/rows.csv"
    echo "${cycle_idx},${start_ts},${end_ts},${duration}" >> "${run_root}/timing_cycles.csv"
    export_cif "${run_tag}" "${cycle_idx}" "${cycle_dir}/pred_min" "${iptm}"
    echo ">>> ${run_tag} ${cycle_tag}: wave prediction recorded (iPTM=${iptm})"
  done
}

run_cycle_wave_antifold_batch() {
  local cycle_idx="$1"
  local wave_root="${EXPT_ROOT}/_cycle_wave"
  local cycle_tag batch_root pdb_dir csv_path out_dir log_path
  cycle_tag="$(printf "cycle_%02d" "${cycle_idx}")"
  batch_root="${wave_root}/${cycle_tag}/antifold_batch"
  pdb_dir="${batch_root}/pdbs"
  csv_path="${batch_root}/pdbs.csv"
  out_dir="${batch_root}/output"
  log_path="${batch_root}/antifold.log"
  mkdir -p "${pdb_dir}" "${out_dir}"
  echo "pdb,Hchain,Agchain" > "${csv_path}"

  local run_index run_tag cycle_dir input_struct patched pdb_path antigen_chain
  antigen_chain="${ANTIFOLD_ANTIGEN_CHAIN}"
  case "$(printf '%s' "${antigen_chain}" | tr '[:upper:]' '[:lower:]')" in
    auto) antigen_chain="${TARGET_CHAIN_ID:-B}" ;;
    none|no|null|off) antigen_chain="" ;;
  esac
  for run_index in $(seq 1 "${N_RUNS}"); do
    run_tag="$(printf "run_%03d" "${run_index}")"
    cycle_dir="${EXPT_ROOT}/${run_tag}/${cycle_tag}"
    if [[ -f "${cycle_dir}/pred_min/model_0.cif" ]]; then
      input_struct="${cycle_dir}/pred_min/model_0.cif"
      if [[ "${cycle_idx}" -eq 0 ]]; then
        patched="${cycle_dir}/pred_min/model_0_UNKPATCH.cif"
        patch_cif_unk "${input_struct}" "${patched}" "${UNK_PATCH_MODE}" "${PREDICTOR}" "${ANTIFOLD_NANOBODY_CHAIN}"
        input_struct="${patched}"
      fi
      pdb_path="${pdb_dir}/${run_tag}_${cycle_tag}.pdb"
      convert_cif_to_pdb "${input_struct}" "${pdb_path}"
    else
      input_struct="${cycle_dir}/pred_min/model_0.pdb"
      pdb_path="${pdb_dir}/${run_tag}_${cycle_tag}.pdb"
      cp -f "${input_struct}" "${pdb_path}"
    fi
    if [[ -n "${antigen_chain}" && "${antigen_chain}" != "${ANTIFOLD_NANOBODY_CHAIN}" ]]; then
      echo "${run_tag}_${cycle_tag},${ANTIFOLD_NANOBODY_CHAIN},${antigen_chain}" >> "${csv_path}"
    else
      echo "${run_tag}_${cycle_tag},${ANTIFOLD_NANOBODY_CHAIN}," >> "${csv_path}"
    fi
  done

  local start_ts end_ts duration rc
  start_ts="$(now_epoch)"
  source "${ANTIFOLD_VENV}/bin/activate"
  pushd "${ANTIFOLD_REPO}" >/dev/null
  set +e
  PYTORCH_ENABLE_MPS_FALLBACK=1 KMP_USE_SHM=0 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 ${ANTIFOLD_RUN} \
    --pdb_dir "${pdb_dir}" \
    --pdbs_csv "${csv_path}" \
    --out_dir "${out_dir}" \
    --regions "${ANTIFOLD_REGIONS}" \
    --num_seq_per_target 0 \
    --sampling_temp "${LIGAND_TEMP_DEFAULT}" \
    --batch_size "${N_RUNS}" \
    --num_threads "${ANTIFOLD_NUM_THREADS}" \
    --seed "${ANTIFOLD_SEED}" \
    ${ANTIFOLD_EXTRA_FLAGS[@]+"${ANTIFOLD_EXTRA_FLAGS[@]}"} \
    > "${log_path}" 2>&1
  rc=$?
  set -e
  popd >/dev/null
  deactivate || true
  end_ts="$(now_epoch)"
  duration="$(calc_duration "${start_ts}" "${end_ts}")"
  echo "${cycle_idx},${N_RUNS},${start_ts},${end_ts},${duration}" >> "${wave_root}/antifold_batches.csv"
  if [[ "${rc}" -ne 0 ]]; then
    tail -n 120 "${log_path}" >&2 || true
    die "Cycle-wave AntiFold batch failed for ${cycle_tag}."
  fi

  local run_root current_seq exact_positions exact_residues logits_csv temp seed
  local exact_fasta candidate guarded antifold_dir
  for run_index in $(seq 1 "${N_RUNS}"); do
    run_tag="$(printf "run_%03d" "${run_index}")"
    run_root="${EXPT_ROOT}/${run_tag}"
    cycle_dir="${run_root}/${cycle_tag}"
    current_seq="$(tr -d '[:space:]' < "${run_root}/state_current_seq.txt")"
    exact_positions="$(cat "${run_root}/nanobody_antifold_positions.txt")"
    exact_residues="$(cat "${run_root}/nanobody_exact_residues.txt")"
    logits_csv="$(find "${out_dir}" -maxdepth 1 -type f -name "${run_tag}_${cycle_tag}_*.csv" | sort | head -n 1 || true)"
    [[ -n "${logits_csv}" ]] || die "Cycle-wave AntiFold logits missing for ${run_tag}/${cycle_tag}."
    antifold_dir="${cycle_dir}/antifold"
    mkdir -p "${antifold_dir}" "${cycle_dir}/antifold_min"
    cp -f "${log_path}" "${antifold_dir}/antifold.log"
    cp -f "${logits_csv}" "${antifold_dir}/$(basename "${logits_csv}")"
    exact_fasta="${antifold_dir}/antifold_exact_positions.fasta"
    if [[ "${cycle_idx}" -eq 0 ]]; then
      temp="${LIGAND_TEMP_CYCLE01}"
    else
      temp="${LIGAND_TEMP_DEFAULT}"
    fi
    seed="$((ANTIFOLD_SEED + run_index * 1000 + cycle_idx))"
    candidate="$(
      "${ANTIFOLD_VENV}/bin/python" "${ANTIFOLD_EXACT_SAMPLER}" \
        --logits-csv "${logits_csv}" \
        --chain "${ANTIFOLD_NANOBODY_CHAIN}" \
        --base-sequence "${current_seq}" \
        --positions "${exact_positions}" \
        --temperature "${temp}" \
        --seed "${seed}" \
        --num-sequences "${ANTIFOLD_NUM_SEQ_PER_TARGET}" \
        --omit-aa C \
        --output-fasta "${exact_fasta}"
    )"
    guarded="$(apply_nanobody_redesign_guard "${current_seq}" "${candidate}" "${exact_residues}")"
    printf '%s\n' "${guarded}" > "${run_root}/state_current_seq.txt"
    cp -f "${exact_fasta}" "${cycle_dir}/antifold_min/seqs.fasta"
    cp -f "${logits_csv}" "${cycle_dir}/antifold_min/logits.csv"
  done
  echo "${cycle_idx},${N_RUNS},${start_ts},${end_ts},${duration},antifold" >> "${wave_root}/inverse_folding_batches.csv"
}

run_cycle_wave_mpnn_redesigns() {
  local cycle_idx="$1"
  local wave_root="${EXPT_ROOT}/_cycle_wave"
  local start_ts end_ts duration
  start_ts="$(now_epoch)"

  # Predictor batching amortizes the expensive structure-model load. MPNN
  # redesigns remain independent so every run retains its run/cycle seed.
  # Two concurrent MPNN jobs is a conservative Apple-Silicon default and can be
  # lowered without changing predictor batch size.
  local redesign_parallel="${MPNN_WAVE_MAX_PARALLEL}"
  if (( redesign_parallel > N_RUNS )); then
    redesign_parallel="${N_RUNS}"
  fi

  local run_index run_tag run_root cycle_tag cycle_dir struct current_seq
  local exact_residues exact_positions candidate
  local status_file run_rc
  local status_files=()
  local redesign_pids=()
  cycle_tag="$(printf "cycle_%02d" "${cycle_idx}")"
  for run_index in $(seq 1 "${N_RUNS}"); do
    if [[ "${DESIGN_SCHEDULER}" == "resident" ]]; then
      wait_for_slot "$((redesign_parallel + 1))"
    else
      wait_for_slot "${redesign_parallel}"
    fi
    run_tag="$(printf "run_%03d" "${run_index}")"
    status_file="${EXPT_ROOT}/${run_tag}/${cycle_tag}/mpnn_wave_exit_code.txt"
    printf 'running\n' > "${status_file}"
    status_files+=("${status_file}")
    (
      run_rc=1
      trap 'printf "%s\n" "${run_rc}" > "${status_file}"' EXIT
      run_tag="$(printf "run_%03d" "${run_index}")"
      run_root="${EXPT_ROOT}/${run_tag}"
      cycle_dir="${run_root}/${cycle_tag}"
      if [[ -f "${cycle_dir}/pred_min/model_0.cif" ]]; then
        struct="${cycle_dir}/pred_min/model_0.cif"
      else
        struct="${cycle_dir}/pred_min/model_0.pdb"
      fi
      [[ -f "${struct}" ]] || die "Cycle-wave redesign structure missing for ${run_tag}/${cycle_tag}."
      current_seq="$(tr -d '[:space:]' < "${run_root}/state_current_seq.txt")"
      exact_residues="$(cat "${run_root}/nanobody_exact_residues.txt")"
      exact_positions="$(cat "${run_root}/nanobody_antifold_positions.txt")"
      candidate="$(run_sequence_redesign \
        "${cycle_dir}" \
        "${struct}" \
        "${cycle_idx}" \
        "" \
        "${exact_residues}" \
        "${run_index}" \
        "${current_seq}" \
        "${exact_positions}")"
      printf '%s\n' "${candidate}" > "${run_root}/state_current_seq.txt"
      run_rc=0
    ) &
    redesign_pids+=("$!")
  done

  set +e
  local redesign_pid
  for redesign_pid in "${redesign_pids[@]}"; do
    wait "${redesign_pid}"
  done
  set -e
  local failed=0
  for status_file in "${status_files[@]}"; do
    run_rc="$(tr -d '[:space:]' < "${status_file}" 2>/dev/null || true)"
    if [[ "${run_rc}" != "0" ]]; then
      echo "ERROR: cycle-wave MPNN status ${status_file} is ${run_rc:-missing}" >&2
      failed=1
    fi
  done
  [[ "${failed}" -eq 0 ]] || die "One or more cycle-wave MPNN redesigns failed for ${cycle_tag}."

  end_ts="$(now_epoch)"
  duration="$(calc_duration "${start_ts}" "${end_ts}")"
  echo "${cycle_idx},${N_RUNS},${start_ts},${end_ts},${duration},${SEQUENCE_DESIGNER_LABEL}" >> "${wave_root}/inverse_folding_batches.csv"
}

# True when every run already has the next cycle's cycle-wave input YAML, i.e. the
# redesign wave after `cycle_idx` completed. Restores each run's state sequence
# from those YAMLs so the next wave continues from the recorded trajectory.
cycle_wave_redesign_recorded() {
  local cycle_idx="$1"
  local next_tag run_index run_tag run_root next_yaml seq
  next_tag="$(printf "cycle_%02d" $((cycle_idx + 1)))"
  for run_index in $(seq 1 "${N_RUNS}"); do
    run_tag="$(printf "run_%03d" "${run_index}")"
    next_yaml="${EXPT_ROOT}/${run_tag}/${next_tag}/${run_tag}_${next_tag}.yaml"
    binder_seq_from_cycle_yaml "${next_yaml}" >/dev/null || return 1
  done
  for run_index in $(seq 1 "${N_RUNS}"); do
    run_tag="$(printf "run_%03d" "${run_index}")"
    run_root="${EXPT_ROOT}/${run_tag}"
    next_yaml="${run_root}/${next_tag}/${run_tag}_${next_tag}.yaml"
    seq="$(binder_seq_from_cycle_yaml "${next_yaml}")"
    printf '%s\n' "${seq}" > "${run_root}/state_current_seq.txt"
  done
  return 0
}

run_designs_cycle_wave() {
  local target_msa_path="$1"
  local wave_root="${EXPT_ROOT}/_cycle_wave"
  mkdir -p "${wave_root}"
  if [[ "${RESUME}" -ne 1 || ! -s "${wave_root}/predictor_batches.csv" ]]; then
    echo "cycle,batch,batch_size,start_ts,end_ts,duration_sec" > "${wave_root}/predictor_batches.csv"
  fi
  if [[ "${RESUME}" -ne 1 || ! -s "${wave_root}/antifold_batches.csv" ]]; then
    echo "cycle,batch_size,start_ts,end_ts,duration_sec" > "${wave_root}/antifold_batches.csv"
  fi
  if [[ "${RESUME}" -ne 1 || ! -s "${wave_root}/inverse_folding_batches.csv" ]]; then
    echo "cycle,batch_size,start_ts,end_ts,duration_sec,sequence_designer" > "${wave_root}/inverse_folding_batches.csv"
  fi
  # Preserve the original wall-clock origin and measured batch rows on resume.
  # A no-work resume must not erase the timing provenance of the completed run.
  if [[ "${RESUME}" -ne 1 || ! -s "${wave_root}/campaign_start_epoch.txt" ]]; then
    printf '%s\n' "$(now_epoch)" > "${wave_root}/campaign_start_epoch.txt"
  fi
  if [[ "${DESIGN_SCHEDULER}" == "resident" ]]; then
    start_resident_predictor
  fi
  initialize_cycle_wave_designs

  local wave_batch_size
  if [[ "${WAVE_BATCH_SIZE}" == "all" ]]; then
    wave_batch_size="${N_RUNS}"
  else
    wave_batch_size="${WAVE_BATCH_SIZE}"
  fi
  if (( wave_batch_size > N_RUNS )); then
    wave_batch_size="${N_RUNS}"
  fi

  local cycle run_index first_run last_run batch_idx
  for cycle in $(seq 0 "${N_CYCLES}"); do
    echo ">>> Cycle-wave: preparing cycle $(printf '%02d' "${cycle}") for ${N_RUNS} runs"
    for run_index in $(seq 1 "${N_RUNS}"); do
      prepare_cycle_wave_input "${run_index}" "${cycle}" "${target_msa_path}" >/dev/null
    done

    batch_idx=0
    first_run=1
    local predictor_batch_status_files=()
    local predictor_batch_pids=()
    while (( first_run <= N_RUNS )); do
      batch_idx=$((batch_idx + 1))
      last_run=$((first_run + wave_batch_size - 1))
      if (( last_run > N_RUNS )); then
        last_run="${N_RUNS}"
      fi
      # Each background task is one native directory/query batch (one model
      # process). MAX_PARALLEL controls how many such persistent batches share
      # the MPS device; WAVE_BATCH_SIZE controls inputs amortized per model load.
      if [[ "${DESIGN_SCHEDULER}" != "resident" ]]; then
        wait_for_slot "${MAX_PARALLEL}"
      fi
      local predictor_batch_status="${wave_root}/$(printf 'cycle_%02d' "${cycle}")/$(printf 'batch_%02d' "${batch_idx}")/exit_code.txt"
      mkdir -p "$(dirname "${predictor_batch_status}")"
      printf 'running\n' > "${predictor_batch_status}"
      predictor_batch_status_files+=("${predictor_batch_status}")
      (
        local batch_rc=1
        trap 'printf "%s\n" "${batch_rc}" > "${predictor_batch_status}"' EXIT
        run_cycle_wave_predictor_batch "${cycle}" "${batch_idx}" "${first_run}" "${last_run}"
        batch_rc=0
      ) &
      predictor_batch_pids+=("$!")
      first_run=$((last_run + 1))
    done

    set +e
    local predictor_batch_pid
    for predictor_batch_pid in "${predictor_batch_pids[@]}"; do
      wait "${predictor_batch_pid}"
    done
    set -e
    local predictor_batch_failed=0 predictor_batch_status_value
    for predictor_batch_status in "${predictor_batch_status_files[@]}"; do
      predictor_batch_status_value="$(tr -d '[:space:]' < "${predictor_batch_status}" 2>/dev/null || true)"
      if [[ "${predictor_batch_status_value}" != "0" ]]; then
        echo "ERROR: cycle-wave predictor batch status ${predictor_batch_status} is ${predictor_batch_status_value:-missing}" >&2
        predictor_batch_failed=1
      fi
    done
    [[ "${predictor_batch_failed}" -eq 0 ]] || die "One or more cycle-wave predictor batches failed for cycle $(printf '%02d' "${cycle}")."

    record_cycle_wave_predictions "${cycle}"
    if (( cycle < N_CYCLES )); then
      # Resume: if every run already has the next cycle's input YAML, the whole
      # redesign wave was completed before the interruption. Adopt the recorded
      # sequences rather than re-sampling inverse folding for the entire wave.
      if [[ "${RESUME}" -eq 1 ]] && cycle_wave_redesign_recorded "${cycle}"; then
        echo ">>> Cycle-wave: reusing recorded cycle $(printf '%02d' "${cycle}") redesign for all ${N_RUNS} runs"
        continue
      fi
      if [[ "${SEQUENCE_DESIGNER}" == "antifold" ]]; then
        echo ">>> Cycle-wave: one AntiFold model load for all ${N_RUNS} cycle $(printf '%02d' "${cycle}") structures"
        run_cycle_wave_antifold_batch "${cycle}"
      else
        echo ">>> Cycle-wave: ${SEQUENCE_DESIGNER_LABEL} redesign for all ${N_RUNS} cycle $(printf '%02d' "${cycle}") structures"
        run_cycle_wave_mpnn_redesigns "${cycle}"
      fi
    fi
  done

  local campaign_end run_index run_tag run_root run_start run_duration
  campaign_end="$(now_epoch)"
  printf '%s\n' "${campaign_end}" > "${wave_root}/campaign_end_epoch.txt"
  for run_index in $(seq 1 "${N_RUNS}"); do
    run_tag="$(printf "run_%03d" "${run_index}")"
    run_root="${EXPT_ROOT}/${run_tag}"
    run_start="$(cat "${run_root}/run_start_epoch.txt")"
    run_duration="$(calc_duration "${run_start}" "${campaign_end}")"
    echo "run,start_ts,end_ts,duration_sec" > "${run_root}/timing_run.csv"
    echo "${run_tag},${run_start},${campaign_end},${run_duration}" >> "${run_root}/timing_run.csv"
  done
  if [[ "${DESIGN_SCHEDULER}" == "resident" ]]; then
    stop_resident_predictor
  fi
  echo "scheduler,wave_batch_size,start_ts,end_ts,duration_sec" > "${wave_root}/campaign_timing.csv"
  echo "${DESIGN_SCHEDULER},${wave_batch_size},$(cat "${wave_root}/campaign_start_epoch.txt"),${campaign_end},$(calc_duration "$(cat "${wave_root}/campaign_start_epoch.txt")" "${campaign_end}")" >> "${wave_root}/campaign_timing.csv"
}

run_one_design() {
  local run_index="$1"
  local target_msa_path="$2"

  local run_tag run_root state_seq metrics_csv rows_csv timing_cycle_csv timing_run_csv motif_cycle_csv
  run_tag="$(printf "run_%03d" "$run_index")"
  run_root="${EXPT_ROOT}/${run_tag}"
  mkdir -p "${run_root}"

  state_seq="${run_root}/state_current_seq.txt"
  metrics_csv="${run_root}/metrics_per_cycle.csv"
  rows_csv="${run_root}/rows.csv"
  timing_cycle_csv="${run_root}/timing_cycles.csv"
  timing_run_csv="${run_root}/timing_run.csv"
  motif_cycle_csv="${run_root}/motif_positions_by_cycle.csv"

  # Snapshot the previous rows before truncating, so a resumed cycle can re-record
  # the exact predictor paths it originally reported rather than the normalised
  # pred_min copies. Keeps resumed summaries byte-identical to uninterrupted ones.
  local rows_prev="${run_root}/.rows_prev.csv"
  if [[ "${RESUME}" -eq 1 && -s "${rows_csv}" ]]; then
    cp -f "${rows_csv}" "${rows_prev}"
  else
    rm -f "${rows_prev}"
  fi

  echo "cycle,iptm,complex_plddt,confidence_json,structure_path,binder_sequence" > "${metrics_csv}"
  echo "run,cycle,iptm,complex_plddt,binder_sequence,structure_path,confidence_json" > "${rows_csv}"
  echo "cycle,start_ts,end_ts,duration_sec" > "${timing_cycle_csv}"

  local run_start run_end run_dur
  run_start="$(now_epoch)"
  echo ">>> Starting ${run_tag}"

  local current_seq motif_fixed_residues motif_shifted_summary partial_redesigned_residues binder_seed
  local motif_shifted_positions motif_shifted_ranges motif_source_ranges
  local nanobody_exact_residues nanobody_antifold_positions
  motif_fixed_residues=""
  motif_shifted_summary=""
  partial_redesigned_residues=""
  motif_shifted_positions=""
  motif_shifted_ranges=""
  motif_source_ranges=""
  nanobody_exact_residues=""
  nanobody_antifold_positions=""
  binder_seed=""
  if [[ -n "${BINDER_RANDOM_SEED}" ]]; then
    binder_seed="$((BINDER_RANDOM_SEED + run_index))"
  fi
  if [[ "${MOTIF_SCAFFOLDING}" -eq 1 ]]; then
    local motif_bundle motif_bundle_file
    motif_bundle_file="${run_root}/motif_bundle.json"
    # Motif placement is randomised per run, and the fixed-residue mask derived
    # from it must be identical across a resume or the redesign would be allowed
    # to mutate motif positions. Persist the bundle and reuse it verbatim.
    if [[ "${RESUME}" -eq 1 && -s "${motif_bundle_file}" ]]; then
      motif_bundle="$(cat "${motif_bundle_file}")"
      echo ">>> ${run_tag}: resume reusing stored motif placement (${motif_bundle_file})"
    else
      motif_bundle="$(generate_motif_scaffold_bundle "${BINDER_MIN_LEN}" "${BINDER_MAX_LEN}")"
      printf '%s\n' "${motif_bundle}" > "${motif_bundle_file}"
    fi
    local motif_values
    motif_values="$(python3 - "${motif_bundle}" <<'PY'
import json, sys
data = json.loads(sys.argv[1])
init_sequence = str(data.get("init_sequence", "")).replace("\t", " ")
fixed_residues = str(data.get("fixed_residues", "")).replace("\t", " ")
shifted_summary = str(data.get("shifted_summary", "")).replace("\t", " ")
motifs = data.get("shifted_motifs", [])
positions = []
shifted_ranges = []
source_ranges = []
for m in motifs:
    ss = int(m["shifted_start"])
    se = int(m["shifted_end"])
    os = int(m["start_pos"])
    oe = int(m["end_pos"])
    positions.extend(range(ss + 1, se + 2))
    shifted_ranges.append(f"{ss + 1}-{se + 1}")
    source_ranges.append(f"{os + 1}-{oe + 1}")
shifted_positions = " ".join(str(x) for x in positions).replace("\t", " ")
shifted_ranges_s = ";".join(shifted_ranges).replace("\t", " ")
source_ranges_s = ";".join(source_ranges).replace("\t", " ")
print("\t".join([
    init_sequence,
    fixed_residues,
    shifted_summary,
    shifted_positions,
    shifted_ranges_s,
    source_ranges_s,
]))
PY
)"
    IFS=$'\t' read -r current_seq motif_fixed_residues motif_shifted_summary motif_shifted_positions motif_shifted_ranges motif_source_ranges <<< "${motif_values}"
    [[ -n "${current_seq}" ]] || die "Motif scaffolding produced an empty initial sequence."
    [[ -n "${motif_shifted_positions}" ]] || die "Motif scaffolding produced empty motif positions."
    echo "design,cycle,motif_positions_1based,motif_ranges_1based,source_motif_ranges_1based" > "${motif_cycle_csv}"
    echo ">>> ${run_tag}: motif scaffolding active (len=${#current_seq})"
    echo ">>> ${run_tag}: motif placements ${motif_shifted_summary}"
  elif [[ "${PARTIAL_REDESIGN}" -eq 1 ]]; then
    current_seq="$(generate_partial_redesign_seed_seq "${PARTIAL_BINDER_SEQ}" "${PARTIAL_REDESIGN_RANGES}" "${BINDER_PERCENT_X}" "${HELIX_KILL}" "${NEGATIVE_HELIX_CONSTANT}" "${LOOP_KILL}" "${PREDICTOR}" "${binder_seed}")"
    partial_redesigned_residues="${PARTIAL_REDESIGNED_RESIDUES}"
    [[ -n "${current_seq}" ]] || die "Partial redesign seeding produced an empty initial sequence."
    echo ">>> ${run_tag}: partial redesign active (len=${#current_seq}, ranges=${PARTIAL_REDESIGN_RANGES}, cycle_00 seeded in-range)"
  elif [[ "${SCAFFOLD_FROM_TEMPLATE}" -eq 1 ]]; then
    local scaffold_seq
    scaffold_seq="$(extract_binder_sequence_from_yaml "${TEMPLATE_YAML}" "${ANTIFOLD_NANOBODY_CHAIN}")"
    [[ -n "${scaffold_seq}" ]] || die "Template chain ${ANTIFOLD_NANOBODY_CHAIN} sequence is empty; --scaffold-from-template requires a concrete binder sequence."
    # Resolve exact scaffold-specific sequence positions for every inverse-folding
    # backend. AntiFold's named IMGT regions do not necessarily match sequential
    # residue numbering in these scaffold structures, so NanoHunter samples its
    # logits at these exact positions and restores all framework residues.
    if [[ "${WORKFLOW}" == "nanobody" ]] && { sequence_designer_uses_ligandmpnn || [[ "${SEQUENCE_DESIGNER}" == "antifold" ]]; }; then
      local cdr_explicit_flags=()
      if [[ "$(printf '%s' "${NANOBODY_SEED_CDR_RANGES}" | tr '[:upper:]' '[:lower:]')" != "auto" ]]; then
        cdr_explicit_flags=(--explicit "${NANOBODY_SEED_CDR_RANGES}")
      fi
      nanobody_exact_residues="$(python3 "${REPO_ROOT}/scripts/nanobody_cdrs.py" \
        --seq "${scaffold_seq}" \
        --chain "${ANTIFOLD_NANOBODY_CHAIN}" \
        --cdrs "${ANTIFOLD_REGIONS}" \
        --catalog "${REPO_ROOT}/examples/nanobody_scaffolds/catalog.tsv" \
        ${cdr_explicit_flags[@]+"${cdr_explicit_flags[@]}"} \
        --emit residues)" \
        || die "CDR detection failed for exact nanobody design positions (chain ${ANTIFOLD_NANOBODY_CHAIN}, cdrs ${ANTIFOLD_REGIONS})."
      [[ -n "${nanobody_exact_residues}" ]] || die "CDR detection returned no residues for --nanobody-cdrs ${ANTIFOLD_REGIONS}."
      nanobody_antifold_positions="$(residue_spec_to_positions "${nanobody_exact_residues}")"
      echo ">>> ${run_tag}: ${SEQUENCE_DESIGNER_LABEL} restricted to exact CDRs [${ANTIFOLD_REGIONS}] -> $(printf '%s' "${nanobody_exact_residues}" | wc -w | tr -d ' ') residues"
    fi
    if [[ "${WORKFLOW}" == "nanobody" && "${NANOBODY_SEED_MODE}" == "cdr-random" ]]; then
      local seed_report seed_value
      seed_report="${run_root}/nanobody_seed_cycle00.json"
      seed_value="$((ANTIFOLD_SEED + run_index * 1000))"
      current_seq="$(generate_nanobody_seed_seq "${scaffold_seq}" "${NANOBODY_SEED_CDRS}" "${seed_value}" "${seed_report}")"
      echo ">>> ${run_tag}: nanobody scaffold seed active (chain=${ANTIFOLD_NANOBODY_CHAIN}, len=${#current_seq}, randomized=${NANOBODY_SEED_CDRS})"
      echo ">>> ${run_tag}: seed constraints report ${seed_report}"
    else
      current_seq="${scaffold_seq}"
      if [[ "${WORKFLOW}" == "nanobody" ]]; then
        echo ">>> ${run_tag}: native nanobody scaffold seed active (chain=${ANTIFOLD_NANOBODY_CHAIN}, len=${#current_seq})"
      else
        echo ">>> ${run_tag}: fixed protein binder seed active (chain=${ANTIFOLD_NANOBODY_CHAIN}, len=${#current_seq})"
      fi
    fi
  else
    current_seq="$(generate_random_binder_seq "${BINDER_MIN_LEN}" "${BINDER_MAX_LEN}" "${BINDER_PERCENT_X}" "${HELIX_KILL}" "${NEGATIVE_HELIX_CONSTANT}" "${LOOP_KILL}" "${PREDICTOR}" "${binder_seed}")"
  fi
  echo "$current_seq" > "$state_seq"

  if [[ "${RESUME}" -eq 1 ]]; then
    local resume_last
    resume_last="$(last_complete_cycle "${run_root}" "${N_CYCLES}")"
    if (( resume_last >= 0 )); then
      echo ">>> ${run_tag}: resume found cycles 00-$(printf '%02d' "${resume_last}") already predicted"
    fi
  fi

  local cycle
  for cycle in $(seq 0 "${N_CYCLES}"); do
    local cycle_tag cycle_dir cycle_yaml qname
    cycle_tag="$(printf "cycle_%02d" "$cycle")"
    cycle_dir="${run_root}/${cycle_tag}"
    cycle_yaml="${cycle_dir}/boltz_input.yaml"
    qname="${run_tag}_${cycle_tag}"
    mkdir -p "${cycle_dir}"

    # Resume: a cycle is reusable only if both its prediction and the input YAML
    # that produced it survive, so the recorded sequence always matches the
    # recorded structure.
    local cycle_reused=0 recovered_seq
    if [[ "${RESUME}" -eq 1 ]] && cycle_prediction_complete "${cycle_dir}"; then
      if recovered_seq="$(binder_seq_from_cycle_yaml "${cycle_yaml}")"; then
        current_seq="${recovered_seq}"
        echo "$current_seq" > "$state_seq"
        cycle_reused=1
      else
        echo ">>> ${run_tag} ${cycle_tag}: prediction present but input YAML unusable; recomputing" >&2
      fi
    fi

    local cstart cend cdur result struct conf iptm plddt
    if [[ "${cycle_reused}" -eq 1 ]]; then
      struct="$(cycle_structure_path "${cycle_dir}")"
      conf="${cycle_dir}/pred_min/confidence.json"
      [[ -f "${conf}" ]] || conf=""
      # Prefer the paths this cycle originally reported, when they still resolve.
      if [[ -s "${rows_prev}" ]]; then
        local prev_struct prev_conf
        prev_struct="$(awk -F',' -v c="${cycle}" '$2==c {print $6; exit}' "${rows_prev}")"
        prev_conf="$(awk -F',' -v c="${cycle}" '$2==c {print $7; exit}' "${rows_prev}")"
        [[ -n "${prev_struct}" && -f "${prev_struct}" ]] && struct="${prev_struct}"
        [[ -n "${prev_conf}" && -f "${prev_conf}" ]] && conf="${prev_conf}"
      fi
      iptm="nan"
      plddt="nan"
      if [[ -n "${conf}" ]]; then
        IFS=',' read -r iptm plddt <<< "$(extract_metrics_from_conf_json "${conf}")"
      fi
      # Restore the original wall-clock so timing CSVs stay comparable; older
      # trees without the marker report a zero-duration reused cycle.
      if [[ -f "${cycle_dir}/pred_min/cycle_timing.txt" ]]; then
        IFS=',' read -r cstart cend cdur < "${cycle_dir}/pred_min/cycle_timing.txt"
      else
        cstart="$(now_epoch)"; cend="${cstart}"; cdur=0
      fi
      echo "$(printf '%02d' "$cycle"),${cstart},${cend},${cdur}" >> "${timing_cycle_csv}"
      echo ">>> ${run_tag} ${cycle_tag}: reusing existing prediction (iPTM=${iptm})"
    else
      local target_msa_for_pred
      target_msa_for_pred="$(pick_target_msa_for_predictor "${target_msa_path}" "${PREDICTOR}")"
      local binder_msa_for_pred
      binder_msa_for_pred="$(make_masked_nanobody_scaffold_msa "${current_seq}" "${cycle_dir}/nanobody_scaffold_masked.a3m" "${PREDICTOR}")"
      make_yaml_with_binder_sequence "${TEMPLATE_YAML}" "${cycle_yaml}" "${current_seq}" "${target_msa_for_pred}" "${PREDICTOR}" "${binder_msa_for_pred}" "design"

      cstart="$(now_epoch)"
      if [[ "${cycle}" -eq 0 && -n "${INITIAL_STRUCTURE}" ]]; then
        echo ">>> ${run_tag} ${cycle_tag}: importing exact archived structure..."
        result="$(import_initial_cycle_structure "${cycle_dir}" "${current_seq}")"
      else
        echo ">>> ${run_tag} ${cycle_tag}: ${PREDICTOR} predict..."
        result="$(run_predictor_once "${PREDICTOR}" "${cycle_yaml}" "${current_seq}" "${qname}" "${cycle_dir}" "${target_msa_for_pred}" "design")"
      fi
      result="$(normalize_predictor_result_line "${result}")"
      cend="$(now_epoch)"
      cdur="$(calc_duration "$cstart" "$cend")"
      echo "$(printf '%02d' "$cycle"),${cstart},${cend},${cdur}" >> "${timing_cycle_csv}"
      printf '%s,%s,%s\n' "${cstart}" "${cend}" "${cdur}" > "${cycle_dir}/pred_min/cycle_timing.txt" 2>/dev/null || true

      IFS='|' read -r struct conf iptm plddt <<< "$result"
    fi
    [[ -n "${iptm:-}" ]] || iptm="nan"
    [[ -n "${plddt:-}" ]] || plddt="nan"
    local conf_val struct_val
    conf_val="${conf:-}"
    struct_val="${struct:-}"

    echo "$(printf '%02d' "$cycle"),${iptm},${plddt},${conf_val},${struct_val},${current_seq}" >> "${metrics_csv}"
    echo "${run_index},${cycle},${iptm},${plddt},${current_seq},${struct_val},${conf_val}" >> "${rows_csv}"
    if [[ "${MOTIF_SCAFFOLDING}" -eq 1 ]]; then
      echo "${run_index},$(printf '%02d' "$cycle"),${motif_shifted_positions},${motif_shifted_ranges},${motif_source_ranges}" >> "${motif_cycle_csv}"
    fi
    if [[ "${cycle_reused}" -ne 1 ]]; then
      echo ">>> ${run_tag} ${cycle_tag}: done in ${cdur}s (iPTM=${iptm})"
    fi

    export_cif "$run_tag" "$cycle" "${cycle_dir}/pred_min" "$iptm"

    if (( cycle < N_CYCLES )); then
      # Resume: if the next cycle's YAML exists it already records the sequence
      # this redesign produced. Adopting it keeps a resumed trajectory identical
      # to the interrupted one instead of re-sampling the inverse-folding step.
      local next_cycle_yaml next_seq
      next_cycle_yaml="${run_root}/$(printf 'cycle_%02d' $((cycle + 1)))/boltz_input.yaml"
      if [[ "${RESUME}" -eq 1 && "${cycle_reused}" -eq 1 ]] \
         && next_seq="$(binder_seq_from_cycle_yaml "${next_cycle_yaml}")"; then
        current_seq="${next_seq}"
        echo "$current_seq" > "$state_seq"
        echo ">>> ${run_tag} ${cycle_tag}: reusing recorded redesign for next cycle"
        continue
      fi

      echo ">>> ${run_tag} ${cycle_tag}: ${SEQUENCE_DESIGNER_LABEL} redesign..."
      local redesign_struct
      if [[ -f "${cycle_dir}/pred_min/model_0.cif" ]]; then
        redesign_struct="${cycle_dir}/pred_min/model_0.cif"
      elif [[ -f "${cycle_dir}/pred_min/model_0.pdb" ]]; then
        redesign_struct="${cycle_dir}/pred_min/model_0.pdb"
      else
        die "Missing model_0.cif/model_0.pdb in ${cycle_dir}/pred_min"
      fi
      local redesign_redesigned_residues="${partial_redesigned_residues}"
      if [[ -z "${redesign_redesigned_residues}" ]]; then
        redesign_redesigned_residues="${nanobody_exact_residues}"
      fi
      current_seq="$(run_sequence_redesign \
        "${cycle_dir}" \
        "${redesign_struct}" \
        "$cycle" \
        "${motif_fixed_residues}" \
        "${redesign_redesigned_residues}" \
        "${run_index}" \
        "${current_seq}" \
        "${nanobody_antifold_positions}")"
      echo "$current_seq" > "$state_seq"
    fi
  done

  run_end="$(now_epoch)"
  run_dur="$(calc_duration "$run_start" "$run_end")"
  echo "run,start_ts,end_ts,duration_sec" > "${timing_run_csv}"
  echo "${run_tag},${run_start},${run_end},${run_dur}" >> "${timing_run_csv}"
  echo ">>> Finished ${run_tag} in ${run_dur}s"
}

run_post_task() {
  local predictor="$1"
  local run_index="$2"
  local cycle_index="$3"
  local binder_seq="$4"
  local target_msa_path="$5"

  local pred_safe run_tag cycle_tag post_root post_cycle_root input_yaml qname
  pred_safe="$(safe_predictor_name "$predictor")"
  run_tag="$(printf "run_%03d" "$run_index")"
  cycle_tag="$(printf "cycle_%02d" "$cycle_index")"

  post_root="${EXPT_ROOT}/${run_tag}/post_${pred_safe}"
  post_cycle_root="${post_root}/${cycle_tag}"
  mkdir -p "${post_cycle_root}"

  # Resume: a post-prediction is reusable when its recorded metrics row and its
  # normalised structure both survive.
  if [[ "${RESUME}" -eq 1 && -s "${post_cycle_root}/post_metrics_row.csv" ]] \
     && cycle_prediction_complete "${post_cycle_root}"; then
    echo ">>> ${run_tag} ${cycle_tag}: reusing existing ${predictor} post-prediction"
    return 0
  fi

  input_yaml="${post_cycle_root}/post_input.yaml"
  qname="${run_tag}_post_$(printf '%02d' "$cycle_index")"
  local target_msa_for_post
  target_msa_for_post="$(pick_target_msa_for_predictor "${target_msa_path}" "${predictor}")"
  local binder_msa_for_post
  binder_msa_for_post="$(make_masked_nanobody_scaffold_msa "${binder_seq}" "${post_cycle_root}/nanobody_scaffold_masked.a3m" "${predictor}")"
  make_yaml_with_binder_sequence "${TEMPLATE_YAML}" "${input_yaml}" "${binder_seq}" "${target_msa_for_post}" "${predictor}" "${binder_msa_for_post}" "post"

  local t0 t1 dt result struct conf iptm plddt
  t0="$(now_epoch)"
  result="$(run_predictor_once "${predictor}" "${input_yaml}" "${binder_seq}" "${qname}" "${post_cycle_root}" "${target_msa_for_post}" "post")"
  result="$(normalize_predictor_result_line "${result}")"
  t1="$(now_epoch)"
  dt="$(calc_duration "$t0" "$t1")"

  IFS='|' read -r struct conf iptm plddt <<< "$result"
  [[ -n "${iptm:-}" ]] || iptm="nan"
  [[ -n "${plddt:-}" ]] || plddt="nan"

  {
    echo "run,cycle,iptm,complex_plddt,binder_sequence,structure_path,confidence_json"
    echo "${run_index},${cycle_index},${iptm},${plddt},${binder_seq},${struct},${conf}"
  } > "${post_cycle_root}/post_metrics_row.csv"

  {
    echo "run,cycle,start_ts,end_ts,duration_sec"
    echo "${run_index},${cycle_index},${t0},${t1},${dt}"
  } > "${post_cycle_root}/post_timing_row.csv"
}

aggregate_post_predictor() {
  local predictor="$1"
  local pred_safe
  pred_safe="$(safe_predictor_name "$predictor")"

  local summary_csv summary_timing_csv
  summary_csv="${EXPT_ROOT}/summary_post_${pred_safe}.csv"
  summary_timing_csv="${EXPT_ROOT}/summary_post_${pred_safe}_timing.csv"

  echo "run,cycle,iptm,complex_plddt,binder_sequence,structure_path,confidence_json" > "${summary_csv}"
  echo "run,cycle,start_ts,end_ts,duration_sec" > "${summary_timing_csv}"

  local run_index run_tag post_root
  for run_index in $(seq 1 "${N_RUNS}"); do
    run_tag="$(printf "run_%03d" "$run_index")"
    post_root="${EXPT_ROOT}/${run_tag}/post_${pred_safe}"
    [[ -d "$post_root" ]] || continue

    local run_metrics run_timing
    run_metrics="${post_root}/post_metrics.csv"
    run_timing="${post_root}/post_timing.csv"
    echo "run,cycle,iptm,complex_plddt,binder_sequence,structure_path,confidence_json" > "${run_metrics}"
    echo "run,cycle,start_ts,end_ts,duration_sec" > "${run_timing}"

    local row
    while IFS= read -r row; do
      tail -n +2 "$row" >> "$run_metrics"
      tail -n +2 "$row" >> "$summary_csv"
    done < <(find "$post_root" -type f -name 'post_metrics_row.csv' | sort)

    while IFS= read -r row; do
      tail -n +2 "$row" >> "$run_timing"
      tail -n +2 "$row" >> "$summary_timing_csv"
    done < <(find "$post_root" -type f -name 'post_timing_row.csv' | sort)
  done
}

build_comparison_tables() {
  local cmp_scores cmp_timing
  cmp_scores="${EXPT_ROOT}/comparison_scores_long.csv"
  cmp_timing="${EXPT_ROOT}/comparison_timing_long.csv"

  echo "stage,predictor,run,cycle,iptm,complex_plddt,binder_sequence,structure_path,confidence_json" > "${cmp_scores}"
  echo "stage,predictor,run,phase,cycle,start_ts,end_ts,duration_sec" > "${cmp_timing}"

  local run_index run_tag
  for run_index in $(seq 1 "${N_RUNS}"); do
    run_tag="$(printf "run_%03d" "$run_index")"
    if [[ -f "${EXPT_ROOT}/${run_tag}/metrics_per_cycle.csv" ]]; then
      tail -n +2 "${EXPT_ROOT}/${run_tag}/metrics_per_cycle.csv" | awk -F',' -v p="$PREDICTOR" -v r="$run_index" 'BEGIN{OFS=","} {print "design",p,r,$1,$2,$3,$6,$5,$4}' >> "${cmp_scores}"
    fi
    if [[ -f "${EXPT_ROOT}/${run_tag}/timing_cycles.csv" ]]; then
      tail -n +2 "${EXPT_ROOT}/${run_tag}/timing_cycles.csv" | awk -F',' -v p="$PREDICTOR" -v r="$run_index" 'BEGIN{OFS=","} {print "design",p,r,"cycle",$1,$2,$3,$4}' >> "${cmp_timing}"
    fi
    if [[ -f "${EXPT_ROOT}/${run_tag}/timing_run.csv" ]]; then
      tail -n +2 "${EXPT_ROOT}/${run_tag}/timing_run.csv" | awk -F',' -v p="$PREDICTOR" -v r="$run_index" 'BEGIN{OFS=","} {print "design",p,r,"run","all",$2,$3,$4}' >> "${cmp_timing}"
    fi
  done

  if [[ "$(post_predictors_count)" -gt 0 ]]; then
    local pp
    for pp in "${POST_PREDICTORS[@]}"; do
      local psafe sfile tfile
      psafe="$(safe_predictor_name "$pp")"
      sfile="${EXPT_ROOT}/summary_post_${psafe}.csv"
      tfile="${EXPT_ROOT}/summary_post_${psafe}_timing.csv"

      if [[ -f "$sfile" ]]; then
        tail -n +2 "$sfile" | awk -F',' -v p="$pp" 'BEGIN{OFS=","} {print "post",p,$1,sprintf("%02d",$2),$3,$4,$5,$6,$7}' >> "${cmp_scores}"
      fi
      if [[ -f "$tfile" ]]; then
        tail -n +2 "$tfile" | awk -F',' -v p="$pp" 'BEGIN{OFS=","} {print "post",p,$1,"post_cycle",sprintf("%02d",$2),$3,$4,$5}' >> "${cmp_timing}"
      fi
    done
  fi
}

EXPT_ROOT="${BASE_RUN_ROOT}/${RUN_NAME}"
mkdir -p "${EXPT_ROOT}"

PASS_TAG="$(python3 - "$IPTM_THRESHOLD" <<'PY'
import sys
print(f"{float(sys.argv[1]):.2f}".replace(".","p"))
PY
)"

CIFS_ALL_DIR="${EXPT_ROOT}/cifs_all"
CIFS_PASS_DIR="${EXPT_ROOT}/cifs_iptm_ge_${PASS_TAG}"
mkdir -p "${CIFS_ALL_DIR}" "${CIFS_PASS_DIR}"

TARGET_SEQ="$(extract_target_sequence_from_yaml "${TEMPLATE_YAML}" || true)"
TARGET_CHAIN_ID="$(extract_target_chain_id_from_yaml "${TEMPLATE_YAML}" || true)"
if [[ -n "${TARGET_MSA_PATH_OVERRIDE}" ]]; then
  TARGET_MSA_PATH="${TARGET_MSA_PATH_OVERRIDE}"
else
  TARGET_MSA_PATH="$(extract_target_msa_from_yaml "${TEMPLATE_YAML}" "${TARGET_CHAIN_ID}" || true)"
  if [[ -n "${TARGET_MSA_PATH}" && "${TARGET_MSA_PATH}" != /* ]]; then
    TARGET_MSA_PATH="$(dirname "${TEMPLATE_YAML}")/${TARGET_MSA_PATH}"
  fi
fi
TARGET_CHAINS_TSV="${EXPT_ROOT}/target_chains.tsv"
extract_target_chains_from_yaml "${TEMPLATE_YAML}" > "${TARGET_CHAINS_TSV}" \
  || die "Could not read the target-chain map from ${TEMPLATE_YAML}."
TARGET_CHAIN_COUNT="$(awk 'NF {count += 1} END {print count + 0}' "${TARGET_CHAINS_TSV}")"
TARGET_TOTAL_SEQUENCE_LENGTH="$(awk -F'\t' 'NF >= 2 {total += length($2)} END {print total + 0}' "${TARGET_CHAINS_TSV}")"
if [[ "${TARGET_CHAIN_COUNT}" -gt 1 && "${TARGET_MSA_PATH_OVERRIDE_SET}" -eq 1 ]]; then
  die "--target-msa-path names only one alignment and is ambiguous for ${TARGET_CHAIN_COUNT} target chains. Put an exact msa: path on each target chain instead."
fi

# Resolve predictor padding buckets only after both the target and requested
# binder-length regime are known. Standard fixed-length campaigns therefore
# use one exact tensor shape; variable-length campaigns use their configured
# maximum and do not trigger a new shape when a shorter sequence is sampled.
MAX_REQUESTED_BINDER_LENGTH="${BINDER_MAX_LEN}"
if [[ "${PARTIAL_REDESIGN}" -eq 1 && "${PARTIAL_BINDER_LEN}" -gt 0 ]]; then
  MAX_REQUESTED_BINDER_LENGTH="${PARTIAL_BINDER_LEN}"
elif [[ "${SCAFFOLD_FROM_TEMPLATE}" -eq 1 ]]; then
  _bucket_scaffold_seq="$(extract_binder_sequence_from_yaml "${TEMPLATE_YAML}" "${ANTIFOLD_NANOBODY_CHAIN}" || true)"
  if [[ -n "${_bucket_scaffold_seq}" ]]; then
    MAX_REQUESTED_BINDER_LENGTH="${#_bucket_scaffold_seq}"
  fi
fi
MAX_REQUESTED_POLYMER_TOKENS="$((MAX_REQUESTED_BINDER_LENGTH + TARGET_TOTAL_SEQUENCE_LENGTH))"

validate_bucket_spec() {
  python3 - "$1" <<'PY'
import sys
parts = [item.strip() for item in sys.argv[1].split(",") if item.strip()]
try:
    values = [int(item) for item in parts]
except ValueError:
    raise SystemExit(1)
if not values or any(value <= 0 for value in values):
    raise SystemExit(1)
if any(left >= right for left, right in zip(values, values[1:])):
    raise SystemExit(1)
print(",".join(str(value) for value in values))
PY
}

if [[ "${INTELLIFOLD_EXTRA_CLI_STRING}" == *"--buckets"* ]]; then
  echo "==> IntelliFold buckets supplied through --intellifold-extra; automatic bucket selection disabled."
elif [[ "${INTELLIFOLD_BUCKETS}" != "default" ]]; then
  if [[ "${INTELLIFOLD_BUCKETS}" == "auto" ]]; then
    INTELLIFOLD_BUCKETS="${MAX_REQUESTED_POLYMER_TOKENS}"
  elif [[ "${INTELLIFOLD_BUCKETS}" == "length-aware" ]]; then
    # Experimental variable-length policy. A few 32-token bands reduce padded
    # work without creating one warm-up shape for every sampled binder length.
    # Fixed-scaffold campaigns still resolve to one exact shape.
    INTELLIFOLD_BUCKETS="$(python3 - \
      "${TARGET_TOTAL_SEQUENCE_LENGTH}" "${BINDER_MIN_LEN}" "${MAX_REQUESTED_BINDER_LENGTH}" <<'PY'
import math, sys
target, minimum, maximum = map(int, sys.argv[1:4])
low, high = target + minimum, target + maximum
if low >= high:
    print(high)
else:
    values = list(range(int(math.ceil(low / 32.0) * 32), high, 32))
    values.append(high)
    print(",".join(map(str, sorted(set(values)))))
PY
)"
  else
    INTELLIFOLD_BUCKETS="$(validate_bucket_spec "${INTELLIFOLD_BUCKETS}")" \
      || die "Invalid --intellifold-buckets specification."
  fi
  INTELLIFOLD_EXTRA_FLAGS+=("--buckets" "${INTELLIFOLD_BUCKETS}")
fi
echo "==> Predictor token buckets: IntelliFold=${INTELLIFOLD_BUCKETS}; campaign_max_polymer_tokens=${MAX_REQUESTED_POLYMER_TOKENS}"

OPENFOLD_TARGET_MSA_PATH=""
PEAK_RSS_MB=0
PEAK_FOOTPRINT_MB=0
PEAK_SYS_DELTA_MB=0
PEAK_EFFECTIVE_MB=0
MONITOR_PEAK_RSS_MB=0
MONITOR_PEAK_FOOTPRINT_MB=0
MONITOR_PEAK_SYS_DELTA_MB=0
MONITOR_PEAK_EFFECTIVE_MB=0
CAL_PRED_DONE=0
MSA_CACHE_DIR="${EXPT_ROOT}/msa_cache"
mkdir -p "${MSA_CACHE_DIR}"

# Default Boltz design behavior: use potentials when designing a binder
# against a protein partner or ligand partner.
if [[ "${BOLTZ_USE_POTENTIALS_MODE}" == "on" ]]; then
  BOLTZ_USE_POTENTIALS_DEFAULT=1
elif [[ "${BOLTZ_USE_POTENTIALS_MODE}" == "off" ]]; then
  BOLTZ_USE_POTENTIALS_DEFAULT=0
elif [[ "${PREDICTOR}" == "boltz" ]]; then
  if [[ -n "${TARGET_EPITOPE_RESIDUES}" ]]; then
    BOLTZ_USE_POTENTIALS_DEFAULT=1
  elif [[ "$(template_has_boltz_partner "${TEMPLATE_YAML}")" == "1" ]]; then
    BOLTZ_USE_POTENTIALS_DEFAULT=1
  fi
fi

# Target-MSA calibration/cache for all predictors.
if [[ -n "${TARGET_MSA_PATH}" ]]; then
  [[ -f "${TARGET_MSA_PATH}" ]] || die "Target MSA path does not exist: ${TARGET_MSA_PATH}"
  TARGET_MSA_PATH="$(cd "$(dirname "${TARGET_MSA_PATH}")" && pwd)/$(basename "${TARGET_MSA_PATH}")"
  if [[ -n "${TARGET_MSA_PATH_OVERRIDE}" ]]; then
    echo "==> Using explicit reusable target MSA: ${TARGET_MSA_PATH}"
  else
    echo "==> Using target MSA from template: ${TARGET_MSA_PATH}"
  fi
elif [[ "${TARGET_MSA_MODE}" == "off" ]]; then
  echo "==> Target MSA generation disabled (--target-msa-mode off)."
elif [[ -n "${TARGET_SEQ}" ]]; then
  [[ -n "${TARGET_CHAIN_ID}" ]] || TARGET_CHAIN_ID="B"
  TARGET_MSA_PATH="$(find_reusable_target_msa "${TARGET_SEQ}" "${TARGET_MSA_SEARCH_ROOTS}" || true)"
  if [[ -n "${TARGET_MSA_PATH}" ]]; then
    echo "==> Reusing exact target MSA from shared cache: ${TARGET_MSA_PATH}"
  else
    echo "==> Calibration: no exact cached target MSA; generating ${TARGET_MSA_GENERATOR} alignment through its native MSA-server path for chain ${TARGET_CHAIN_ID}..."
    case "${TARGET_MSA_GENERATOR}" in
    boltz)
      TARGET_MSA_PATH="$(generate_boltz_auto_msa_cache "${TARGET_SEQ}" "${TARGET_CHAIN_ID}" "target" "${MSA_CACHE_DIR}" || true)"
      ;;
    protenix)
      TARGET_MSA_PATH="$(generate_protenix_auto_msa_cache "${TARGET_SEQ}" "${TARGET_CHAIN_ID}" "target" "${MSA_CACHE_DIR}" || true)"
      ;;
      intellifold)
        TARGET_MSA_PATH="$(generate_intellifold_auto_msa_cache "${TARGET_SEQ}" "${TARGET_CHAIN_ID}" "target" "${MSA_CACHE_DIR}" || true)"
        ;;
      openfold)
        TARGET_MSA_PATH="$(generate_openfold_target_msa_cache "${TEMPLATE_YAML}" "${MSA_CACHE_DIR}" "${TARGET_SEQ}" "${TARGET_CHAIN_ID}" "target" || true)"
        ;;
    esac
  fi
  if [[ -n "${TARGET_MSA_PATH}" && -f "${TARGET_MSA_PATH}" ]]; then
    echo "==> Cached target MSA: ${TARGET_MSA_PATH}"
  elif [[ "${TARGET_MSA_REQUIRED}" -eq 1 ]]; then
    die "Required native target MSA generation failed (${TARGET_MSA_GENERATOR}); refusing single-sequence fallback."
  else
    TARGET_MSA_PATH="${MSA_CACHE_DIR}/target_single.a3m"
    write_single_seq_a3m "${TARGET_SEQ}" "${TARGET_MSA_PATH}"
    echo "WARNING: Native target MSA generation failed; using explicit single-sequence target A3M: ${TARGET_MSA_PATH}" >&2
  fi
else
  # Unconditional/monomer templates have no target protein chain; skip target-MSA calibration.
  echo "==> No target chain sequence found; skipping target-MSA calibration."
fi

if [[ "${TARGET_MSA_REQUIRED}" -eq 1 && -n "${TARGET_SEQ}" && -z "${TARGET_MSA_PATH}" ]]; then
  die "A real target MSA is required, but no target MSA path was produced."
fi
if [[ -n "${TARGET_MSA_PATH}" && -n "${TARGET_SEQ}" ]]; then
  TARGET_MSA_RECORDS="$(
    validate_target_msa_file "${TARGET_MSA_PATH}" "${TARGET_SEQ}" "${TARGET_MSA_REQUIRED}"
  )" || die "Target MSA validation failed: ${TARGET_MSA_PATH}"
  echo "==> Validated target MSA: ${TARGET_MSA_PATH} (records=${TARGET_MSA_RECORDS})"
  if [[ "${TARGET_MSA_PATH##*.}" == "a3m" && "${TARGET_MSA_RECORDS}" != "unknown" && "${TARGET_MSA_RECORDS}" -ge 2 ]]; then
    publish_target_msa_to_shared_cache "${TARGET_MSA_PATH}" "${TARGET_SEQ}"
  fi
fi

# Preserve chain identity at the predictor boundary. A multimer target needs a
# distinct query-matched alignment for every fixed subunit; reusing chain B's
# MSA for C/D is scientifically invalid even when the backend accepts the YAML.
TARGET_MSA_MANIFEST="${MSA_CACHE_DIR}/target_msa_manifest.tsv"
: > "${TARGET_MSA_MANIFEST}"
while IFS=$'\t' read -r _target_chain _target_sequence _embedded_msa; do
  [[ -n "${_target_chain}" ]] || continue
  _target_msa=""
  _embedded_msa_kind="$(printf '%s' "${_embedded_msa}" | tr '[:upper:]' '[:lower:]')"
  if [[ "${_target_chain}" == "${TARGET_CHAIN_ID}" ]]; then
    _target_msa="${TARGET_MSA_PATH}"
  elif [[ "${TARGET_MSA_MODE}" == "off" ]]; then
    _target_msa="empty"
  elif [[ -n "${_embedded_msa}" && "${_embedded_msa_kind}" != "auto" \
          && "${_embedded_msa_kind}" != "empty" && "${_embedded_msa_kind}" != "none" \
          && "${_embedded_msa_kind}" != "null" ]]; then
    _target_msa="${_embedded_msa}"
    if [[ "${_target_msa}" != /* ]]; then
      _target_msa="$(dirname "${TEMPLATE_YAML}")/${_target_msa}"
    fi
  else
    _target_msa="$(find_reusable_target_msa "${_target_sequence}" "${TARGET_MSA_SEARCH_ROOTS}" || true)"
    if [[ -z "${_target_msa}" ]]; then
      echo "==> No exact cached MSA for target chain ${_target_chain}; generating with ${TARGET_MSA_GENERATOR}..."
      case "${TARGET_MSA_GENERATOR}" in
        boltz)
          _target_msa="$(generate_boltz_auto_msa_cache "${_target_sequence}" "${_target_chain}" "target_${_target_chain}" "${MSA_CACHE_DIR}" || true)"
          ;;
        protenix)
          _target_msa="$(generate_protenix_auto_msa_cache "${_target_sequence}" "${_target_chain}" "target_${_target_chain}" "${MSA_CACHE_DIR}" || true)"
          ;;
        intellifold)
          _target_msa="$(generate_intellifold_auto_msa_cache "${_target_sequence}" "${_target_chain}" "target_${_target_chain}" "${MSA_CACHE_DIR}" || true)"
          ;;
        openfold)
          _target_msa="$(generate_openfold_target_msa_cache "${TEMPLATE_YAML}" "${MSA_CACHE_DIR}" "${_target_sequence}" "${_target_chain}" "target_${_target_chain}" || true)"
          ;;
      esac
    fi
    if [[ -z "${_target_msa}" ]]; then
      if [[ "${TARGET_MSA_REQUIRED}" -eq 1 ]]; then
        die "Required target MSA generation failed for chain ${_target_chain}; refusing to reuse another chain's alignment or fall back silently."
      fi
      _target_msa="${MSA_CACHE_DIR}/target_${_target_chain}_single.a3m"
      write_single_seq_a3m "${_target_sequence}" "${_target_msa}"
      echo "WARNING: Target chain ${_target_chain} is using an explicit single-sequence A3M." >&2
    fi
  fi

  if [[ "${_target_msa}" == "empty" || -z "${_target_msa}" ]]; then
    _target_msa="empty"
  else
    [[ -f "${_target_msa}" ]] || die "Target chain ${_target_chain} MSA does not exist: ${_target_msa}"
    _target_msa="$(cd "$(dirname "${_target_msa}")" && pwd)/$(basename "${_target_msa}")"
    _target_records="$(validate_target_msa_file "${_target_msa}" "${_target_sequence}" "${TARGET_MSA_REQUIRED}" "Target chain ${_target_chain}")" \
      || die "Target chain ${_target_chain} MSA validation failed: ${_target_msa}"
    echo "==> Validated target chain ${_target_chain} MSA: ${_target_msa} (records=${_target_records})"
    if [[ "${_target_msa##*.}" == "a3m" && "${_target_records}" != "unknown" && "${_target_records}" -ge 2 ]]; then
      publish_target_msa_to_shared_cache "${_target_msa}" "${_target_sequence}"
    fi
  fi
  printf '%s\t%s\n' "${_target_chain}" "${_target_msa}" >> "${TARGET_MSA_MANIFEST}"
done < "${TARGET_CHAINS_TSV}"

prepare_nanobody_scaffold_msa_cache
if [[ -n "${NANOBODY_SCAFFOLD_MSA_BASE_A3M}" ]]; then
  SCAFFOLD_MSA_REQUIRE_DEPTH=0
  if [[ "${NANOBODY_SCAFFOLD_MSA_MODE}" == "masked-cdr" ]]; then
    SCAFFOLD_MSA_REQUIRE_DEPTH=1
  fi
  SCAFFOLD_MSA_RECORDS="$(
    validate_target_msa_file \
      "${NANOBODY_SCAFFOLD_MSA_BASE_A3M}" \
      "$(extract_binder_sequence_from_yaml "${TEMPLATE_YAML}" "${ANTIFOLD_NANOBODY_CHAIN}")" \
      "${SCAFFOLD_MSA_REQUIRE_DEPTH}" \
      "Nanobody scaffold"
  )" || die "Nanobody scaffold MSA validation failed: ${NANOBODY_SCAFFOLD_MSA_BASE_A3M}"
  echo "==> Validated nanobody scaffold MSA: ${NANOBODY_SCAFFOLD_MSA_BASE_A3M} (records=${SCAFFOLD_MSA_RECORDS})"
fi

# Ensure an OpenFold-compatible target MSA cache exists whenever OpenFold is
# used in either design or post-prediction stages.
NEED_OPENFOLD_TARGET_MSA=0
if [[ "${PREDICTOR}" == "openfold-3-mlx" ]]; then
  NEED_OPENFOLD_TARGET_MSA=1
fi
if [[ "${NEED_OPENFOLD_TARGET_MSA}" -eq 0 ]]; then
  for _pp in "${POST_PREDICTORS[@]:-}"; do
    if [[ "${_pp}" == "openfold-3-mlx" ]]; then
      NEED_OPENFOLD_TARGET_MSA=1
      break
    fi
  done
fi

if [[ "${NEED_OPENFOLD_TARGET_MSA}" -eq 1 ]]; then
  if is_openfold_msa_path_compatible "${TARGET_MSA_PATH}"; then
    OPENFOLD_TARGET_MSA_PATH="${TARGET_MSA_PATH}"
  elif [[ -n "${TARGET_SEQ}" ]]; then
    [[ -n "${TARGET_CHAIN_ID}" ]] || TARGET_CHAIN_ID="B"
    echo "==> Preparing OpenFold-compatible target MSA cache for chain ${TARGET_CHAIN_ID}..."
    OPENFOLD_TARGET_MSA_PATH="$(generate_openfold_target_msa_cache "${TEMPLATE_YAML}" "${MSA_CACHE_DIR}" "${TARGET_SEQ}" "${TARGET_CHAIN_ID}")"
    echo "==> Cached OpenFold target MSA: ${OPENFOLD_TARGET_MSA_PATH}"
  else
    # Protein-ligand style inputs can have no target protein chain.
    OPENFOLD_TARGET_MSA_PATH=""
  fi

  if [[ "${PREDICTOR}" == "openfold-3-mlx" && -n "${OPENFOLD_TARGET_MSA_PATH}" ]]; then
    TARGET_MSA_PATH="${OPENFOLD_TARGET_MSA_PATH}"
  fi
fi

# Predictor-specific calibration uses the actual fixed scaffold length in
# nanobody/fixed-binder mode, or the configured maximum random-binder length.
if [[ "${SKIP_PREDICTOR_CALIBRATION}" -eq 1 ]]; then
  echo "==> Skipping predictor memory calibration (explicit --max-parallel ${MAX_PARALLEL_USER})."
elif [[ "${CAL_PRED_DONE}" -eq 0 ]]; then
  if [[ "${SCAFFOLD_FROM_TEMPLATE}" -eq 1 ]]; then
    CALIBRATION_LENGTH_HINT="$(
      extract_binder_sequence_from_yaml "${TEMPLATE_YAML}" "${ANTIFOLD_NANOBODY_CHAIN}" |
        tr -d '[:space:]' |
        awk '{print length($0)}'
    )"
  else
    CALIBRATION_LENGTH_HINT="${BINDER_MAX_LEN}"
  fi
  echo "==> Calibration: running one ${PREDICTOR} prediction at binder length ${CALIBRATION_LENGTH_HINT}..."
  run_predictor_calibration_once "${PREDICTOR}" "${TARGET_MSA_PATH}"
fi

CPU_CORES="$(sysctl -n hw.ncpu 2>/dev/null || echo 4)"
if [[ "${MAX_PARALLEL_USER}" == "auto" || "${CALIBRATE_ONLY}" -eq 1 ]]; then
  if [[ "${MEM_BUDGET_GB}" == "auto" ]]; then
    MEM_BUDGET_MB="$(default_mem_budget_mb)"
  else
    MEM_BUDGET_MB="$(python3 - "${MEM_BUDGET_GB}" <<'PY'
import sys
gb=float(sys.argv[1]); print(max(1024, int(gb*1024)))
PY
)"
  fi
  CONFIG_SAFE_MB="$(floor_mul "${MEM_BUDGET_MB}" "${MEM_SAFETY}")"
  SYSTEM_AVAILABLE_MB="$(python3 - "$(get_system_available_kb)" <<'PY'
import sys
try:
    kb = int(sys.argv[1])
except Exception:
    kb = 0
print(max(0, kb // 1024))
PY
)"
  MPS_LIVE_BUDGET_MB="${CONFIG_SAFE_MB}"
  if [[ "${MPS_AWARE}" -eq 1 && "${CPU_ONLY}" -eq 0 ]]; then
    # "total" basis uses a fraction of physical RAM instead of currently-available
    # memory (design gets more RAM; other apps may swap). Still capped by CONFIG_SAFE_MB.
    BUDGET_BASIS_MB="${SYSTEM_AVAILABLE_MB}"
    if [[ "${MEM_BASIS}" == "total" ]]; then
      BUDGET_BASIS_MB="$(python3 - "$(total_ram_bytes)" <<'PY'
import sys
try: print(int(int(sys.argv[1]) / 1024 / 1024))
except Exception: print(0)
PY
)"
    fi
    MPS_LIVE_BUDGET_MB="$(python3 - "${BUDGET_BASIS_MB}" "${MPS_MEMORY_RESERVE_GB}" "${MPS_MEM_FRACTION}" "${CONFIG_SAFE_MB}" <<'PY'
import sys
available_mb = max(0, int(sys.argv[1]))
reserve_mb = max(0, int(float(sys.argv[2]) * 1024))
fraction = max(0.05, min(1.0, float(sys.argv[3])))
config_safe_mb = max(1024, int(sys.argv[4]))
live_budget = int(max(0, available_mb - reserve_mb) * fraction)
if live_budget <= 0:
    live_budget = 1024
print(max(1024, min(config_safe_mb, live_budget)))
PY
)"
  fi
  SAFE_MB="${MPS_LIVE_BUDGET_MB}"
  if [[ -z "${PEAK_EFFECTIVE_MB}" || "${PEAK_EFFECTIVE_MB}" == "0" ]]; then
    if [[ -n "${PEAK_FOOTPRINT_MB}" && "${PEAK_FOOTPRINT_MB}" != "0" ]]; then
      PEAK_EFFECTIVE_MB="${PEAK_FOOTPRINT_MB}"
    elif [[ -n "${PEAK_RSS_MB}" && "${PEAK_RSS_MB}" != "0" ]]; then
      PEAK_EFFECTIVE_MB="${PEAK_RSS_MB}"
    else
      PEAK_EFFECTIVE_MB=4096
    fi
  fi
  AUTO_MAX_BY_MEM="$(python3 - "${SAFE_MB}" "${PEAK_EFFECTIVE_MB}" <<'PY'
import sys
safe=int(sys.argv[1]); peak=max(1,int(sys.argv[2]))
print(max(1, safe//peak))
PY
)"
  AUTO_MAX_BY_CPU="$(python3 - "${CPU_CORES}" "${MPS_CPU_CAP}" <<'PY'
import sys, math
cores=int(sys.argv[1]); cap_raw=sys.argv[2]
if cap_raw == "auto":
    cap=max(1,int(math.floor(cores*0.75)))
else:
    cap=max(1,int(float(cap_raw)))
print(max(1,min(cap,cores)))
PY
)"
  AUTO_MAX_BY_MPS="${N_RUNS}"
  if [[ "${MPS_AWARE}" -eq 1 && "${CPU_ONLY}" -eq 0 ]]; then
    case "${PREDICTOR}" in
      boltz|intellifold|openfold-3-mlx)
        AUTO_MAX_BY_MPS="$(python3 - "${MPS_MAX_PARALLEL}" "${N_RUNS}" <<'PY'
import sys
cap_raw=sys.argv[1]
runs=max(1,int(sys.argv[2]))
if cap_raw == "auto":
    cap=4
else:
    cap=max(1,int(float(cap_raw)))
print(max(1,min(cap,runs)))
PY
)"
        ;;
      protenix-v2|protenix-mini|protenix-constraint-v0.5)
        AUTO_MAX_BY_MPS=1
        ;;
    esac
  fi
  MAX_PARALLEL="$(python3 - "${AUTO_MAX_BY_MEM}" "${AUTO_MAX_BY_CPU}" "${AUTO_MAX_BY_MPS}" "${N_RUNS}" <<'PY'
import sys
print(max(1, min(int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]))))
PY
)"
else
  MAX_PARALLEL="${MAX_PARALLEL_USER}"
fi

# A device profile adds measured throughput information to the single-run live
# memory calibration above.  Memory remains a hard cap; the profile can only
# choose a lower process count and, for cycle-wave jobs, a native batch size.
THROUGHPUT_PROFILE_USED=""
THROUGHPUT_PROFILE_CONFIDENCE=""
THROUGHPUT_PROFILE_RECOMMENDED_BATCH=""
if [[ "${MAX_PARALLEL_USER}" == "auto" && "${THROUGHPUT_PROFILE}" != "off" ]] \
   && [[ "$(template_has_small_molecule_ligand "${TEMPLATE_YAML}")" != "1" ]]; then
  _profile_path="${THROUGHPUT_PROFILE}"
  if [[ "${_profile_path}" == "auto" ]]; then
    _profile_path="$(find "${BASE_RUN_ROOT}" -maxdepth 3 -type f -name 'device_profile.json' -path '*device_throughput_calibration*' 2>/dev/null | sort | tail -n 1 || true)"
  elif [[ -n "${_profile_path}" && "${_profile_path}" != /* ]]; then
    _profile_path="${REPO_ROOT}/${_profile_path}"
  fi
  if [[ -n "${_profile_path}" && -s "${_profile_path}" ]]; then
    _profile_predictor="${PREDICTOR}"
    [[ "${_profile_predictor}" == "openfold-3-mlx" ]] && _profile_predictor="openfold"
    _profile_potential_args=()
    if [[ "${PREDICTOR}" == "boltz" && "${BOLTZ_USE_POTENTIALS_DEFAULT}" -eq 1 ]]; then
      _profile_potential_args=(--potentials)
    fi
    _profile_target_msa_depth=0
    if [[ -n "${TARGET_MSA_PATH}" && -s "${TARGET_MSA_PATH}" ]]; then
      _profile_target_msa_depth="$(python3 - "${TARGET_MSA_PATH}" <<'PY'
import sys
from pathlib import Path
p = Path(sys.argv[1])
try:
    print(sum(line.startswith(">") for line in p.open(errors="ignore")))
except OSError:
    print(0)
PY
)"
    fi
    set +e
    _profile_choice="$(python3 "${REPO_ROOT}/scripts/compute_throughput_profile.py" recommend \
      --profile "${_profile_path}" \
      --predictor "${_profile_predictor}" \
      --binder-length "${CALIBRATION_LENGTH_HINT:-${BINDER_MAX_LEN}}" \
      --target-length "${#TARGET_SEQ}" \
      --binder-msa-depth 1 \
      --target-msa-depth "${_profile_target_msa_depth}" \
      --memory-budget-gb "$(python3 - "${SAFE_MB:-1024}" <<'PY'
import sys
print(max(1.0, float(sys.argv[1]) / 1024.0))
PY
)" \
      ${_profile_potential_args[@]+"${_profile_potential_args[@]}"} 2>"${EXPT_ROOT}/throughput_profile_warning.log")"
    _profile_rc=$?
    set -e
    if [[ "${_profile_rc}" -eq 0 && -n "${_profile_choice}" ]]; then
      IFS=$'\t' read -r _profile_processes _profile_batch _profile_confidence <<< "$(python3 - "${_profile_choice}" <<'PY'
import json, sys
x=json.loads(sys.argv[1])
print(f"{int(x.get('processes',1))}\t{int(x.get('native_batch_per_process',1))}\t{x.get('confidence','low')}")
PY
)"
      MAX_PARALLEL="$(python3 - "${MAX_PARALLEL}" "${_profile_processes}" <<'PY'
import sys
print(max(1, min(int(sys.argv[1]), int(sys.argv[2]))))
PY
)"
      if [[ "${DESIGN_SCHEDULER}" == "cycle-wave" && "${WAVE_BATCH_SIZE_USER_SET}" -eq 0 ]]; then
        WAVE_BATCH_SIZE="${_profile_batch}"
      fi
      THROUGHPUT_PROFILE_USED="${_profile_path}"
      THROUGHPUT_PROFILE_CONFIDENCE="${_profile_confidence}"
      THROUGHPUT_PROFILE_RECOMMENDED_BATCH="${_profile_batch}"
    else
      echo "WARNING: throughput profile could not be used; retaining live-calibration scheduling (see ${EXPT_ROOT}/throughput_profile_warning.log)." >&2
    fi
  elif [[ "${THROUGHPUT_PROFILE}" != "auto" ]]; then
    die "Throughput profile not found: ${_profile_path}"
  fi
elif [[ "${MAX_PARALLEL_USER}" == "auto" && "${THROUGHPUT_PROFILE}" != "off" ]] \
     && [[ "$(template_has_small_molecule_ligand "${TEMPLATE_YAML}")" == "1" ]]; then
  echo "WARNING: no ligand-atom device profile is installed; using live one-run memory calibration for this ligand workload." >&2
fi

if [[ "${NO_PARALLEL}" -eq 1 ]]; then
  MAX_PARALLEL=1
fi

if [[ "$MAX_PARALLEL" == "auto" ]]; then
  MAX_PARALLEL=1
fi
if (( MAX_PARALLEL < 1 )); then MAX_PARALLEL=1; fi
if (( MAX_PARALLEL > N_RUNS )); then MAX_PARALLEL="$N_RUNS"; fi
if [[ "${MAX_PARALLEL_USER}" == "auto" || "${CALIBRATE_ONLY}" -eq 1 ]]; then
  write_calibration_memory_metrics "${EXPT_ROOT}/calibration_memory_metrics.csv"
fi

# Calibration-only mode: measure peak memory at max, write the CSV, and stop
# before running any design cycles.
if [[ "${CALIBRATE_ONLY}" -eq 1 ]]; then
  echo "CALIBRATION_DONE ${EXPT_ROOT}/calibration_memory_metrics.csv suggested_max_parallel=${MAX_PARALLEL}"
  exit 0
fi

echo "========================================"
echo "${APP_NAME}"
echo "Repo root               : ${REPO_ROOT}"
echo "Workflow                : ${WORKFLOW}"
echo "Run name                : ${RUN_NAME}"
echo "Predictor               : ${PREDICTOR}"
if [[ "$(post_predictors_count)" -gt 0 ]]; then
  echo "Post predictor(s)       : ${POST_PREDICTORS[*]}"
else
  echo "Post predictor(s)       : none"
fi
echo "Runs                    : ${N_RUNS}"
echo "Optimization cycles     : ${N_CYCLES} (plus cycle_00 seed)"
echo "MAX_PARALLEL            : ${MAX_PARALLEL}"
echo "Design scheduler        : ${DESIGN_SCHEDULER}"
if [[ "${RESUME}" -eq 1 ]]; then
  echo "Resume                  : on (reusing completed cycle predictions)"
fi
if [[ "${SEQUENCE_DESIGNER}" =~ ^(proteinmpnn|solublempnn|ligandmpnn|abmpnn)$ ]]; then
  echo "MPNN seed scheme        : ${LIGANDMPNN_SEED} + run_index*1000 + redesign_cycle"
fi
if [[ "${SCAFFOLD_FROM_TEMPLATE}" -eq 0 && -n "${BINDER_RANDOM_SEED}" ]]; then
  echo "Cycle-00 seed scheme    : ${BINDER_RANDOM_SEED} + run_index"
fi
if [[ "${DESIGN_SCHEDULER}" == "cycle-wave" || "${DESIGN_SCHEDULER}" == "resident" ]]; then
  echo "Wave batch size         : ${WAVE_BATCH_SIZE}"
  if [[ "${SEQUENCE_DESIGNER}" != "antifold" ]]; then
    echo "Wave MPNN parallelism   : ${MPNN_WAVE_MAX_PARALLEL}"
  fi
fi
if [[ "${MOTIF_SCAFFOLDING}" -eq 1 ]]; then
  echo "Motif scaffolding       : on (Boltz-only design mode)"
  echo "Motif positions         : ${MOTIF_POSITIONS}"
  echo "Motif gap min           : ${MOTIF_GAP_BETWEEN}"
  if [[ -n "${MOTIF_FIXED_POSITIONS}" ]]; then
    echo "Motif fixed subset      : ${MOTIF_FIXED_POSITIONS}"
  else
    echo "Motif fixed subset      : (all motif residues)"
  fi
fi
if [[ "${PARTIAL_REDESIGN}" -eq 1 ]]; then
  echo "Partial redesign        : on"
  echo "Redesign ranges         : ${PARTIAL_REDESIGN_RANGES}"
  echo "Binder template length  : ${PARTIAL_BINDER_LEN}"
  echo "Cycle_00 seed mode      : standard randomization in redesign ranges only"
fi
if [[ "${SCAFFOLD_FROM_TEMPLATE}" -eq 1 ]]; then
  echo "Scaffold from template  : on (chain ${ANTIFOLD_NANOBODY_CHAIN})"
fi
if [[ -n "${INITIAL_STRUCTURE}" ]]; then
  echo "Imported cycle_00       : ${INITIAL_STRUCTURE}"
  echo "Imported confidence     : ${INITIAL_CONFIDENCE_JSON:-none}"
fi
if [[ "${WORKFLOW}" == "nanobody" ]]; then
  echo "Nanobody seed mode      : ${NANOBODY_SEED_MODE}"
  if [[ "${NANOBODY_SEED_MODE}" == "cdr-random" ]]; then
    echo "Nanobody seed CDRs      : ${NANOBODY_SEED_CDRS}"
    echo "Nanobody seed ranges    : ${NANOBODY_SEED_CDR_RANGES}"
    echo "Nanobody hard filters   : no Cys in seed CDRs, no N-X-S/T, no homopolymer>=4, no G>3, no P>2"
    if [[ "${NANOBODY_USE_SOFT_FILTERS}" -eq 1 ]]; then
      echo "Nanobody soft filters   : charge ${NANOBODY_CHARGE_MIN}..${NANOBODY_CHARGE_MAX}, hydrophobic<=${NANOBODY_HYDRO_MAX}"
    else
      echo "Nanobody soft filters   : off"
    fi
  fi
fi
if [[ "${MAX_PARALLEL_USER}" == "auto" ]]; then
  echo "Auto parallel (mem/cpu/mps): ${AUTO_MAX_BY_MEM:-na}/${AUTO_MAX_BY_CPU:-na}/${AUTO_MAX_BY_MPS:-na}"
  echo "Configured safe MB      : ${CONFIG_SAFE_MB:-na}"
  echo "System available MB     : ${SYSTEM_AVAILABLE_MB:-na}"
  echo "MPS live budget MB      : ${MPS_LIVE_BUDGET_MB:-na}"
  echo "MPS memory reserve GB   : ${MPS_MEMORY_RESERVE_GB}"
  echo "Calibration peak RSS MB : ${PEAK_RSS_MB:-na}"
  echo "Calibration peak phys MB: ${PEAK_FOOTPRINT_MB:-na}"
  echo "Calibration peak sys MB : ${PEAK_SYS_DELTA_MB:-na}"
  echo "Calibration effective MB: ${PEAK_EFFECTIVE_MB:-na}"
  if [[ -n "${THROUGHPUT_PROFILE_USED:-}" ]]; then
    echo "Throughput profile      : ${THROUGHPUT_PROFILE_USED}"
    echo "Profile confidence      : ${THROUGHPUT_PROFILE_CONFIDENCE}"
    echo "Profile native batch    : ${THROUGHPUT_PROFILE_RECOMMENDED_BATCH}"
  fi
fi
echo "CPU only                : ${CPU_ONLY}"
echo "Sequence designer       : ${SEQUENCE_DESIGNER_LABEL}"
echo "Design temp cycle_00->01: ${LIGAND_TEMP_CYCLE01}"
echo "Design temp other cycles: ${LIGAND_TEMP_DEFAULT}"
if [[ "${SEQUENCE_DESIGNER}" == "antifold" ]]; then
  echo "AntiFold CDR regions    : ${ANTIFOLD_REGIONS}"
  echo "AntiFold nanobody chain : ${ANTIFOLD_NANOBODY_CHAIN}"
  echo "AntiFold antigen chain  : ${ANTIFOLD_ANTIGEN_CHAIN}"
  echo "AntiFold base seed      : ${ANTIFOLD_SEED}"
else
  echo "MPNN redesign model     : ${LIGANDMPNN_MODEL_LABEL}"
  echo "MPNN bias cycle_00->01  : ${LIGAND_BIAS_AA_CYCLE01:-none}"
  echo "MPNN bias other cycles  : ${LIGAND_BIAS_AA_DEFAULT:-none}"
fi
echo "Loop-kill constant      : ${LOOP_KILL}"
if [[ "${PREDICTOR}" == "boltz" ]]; then
  echo "Boltz design potentials : ${BOLTZ_USE_POTENTIALS_DEFAULT} (mode=${BOLTZ_USE_POTENTIALS_MODE})"
  if [[ -n "${TARGET_EPITOPE_RESIDUES}" ]]; then
    echo "Boltz epitope residues  : ${TARGET_EPITOPE_RESIDUES}"
    echo "Boltz contact mode      : ${BOLTZ_CONTACT_MODE}"
    echo "Boltz contact distance  : ${BOLTZ_CONTACT_DISTANCE} A"
    echo "Boltz contact force     : ${BOLTZ_CONTACT_FORCE}"
  else
    echo "Boltz epitope residues  : none"
  fi
fi
echo "Target chains           : ${TARGET_CHAIN_COUNT}"
echo "Target sequence length  : ${TARGET_TOTAL_SEQUENCE_LENGTH} aa total"
echo "Target MSA generator    : ${TARGET_MSA_GENERATOR}"
if [[ -n "${TARGET_MSA_PATH}" ]]; then
  echo "Target MSA path         : ${TARGET_MSA_PATH}"
elif [[ "${TARGET_MSA_MODE}" == "off" ]]; then
  echo "Target MSA path         : disabled"
else
  echo "Target MSA path         : none (no target chain sequence found)"
fi
if [[ -n "${OPENFOLD_TARGET_MSA_PATH:-}" ]]; then
  echo "OpenFold target MSA     : ${OPENFOLD_TARGET_MSA_PATH}"
fi
if [[ -s "${TARGET_MSA_MANIFEST:-}" ]]; then
  echo "Target MSA chain map    : ${TARGET_MSA_MANIFEST}"
fi
if [[ "${WORKFLOW}" == "nanobody" && "${SCAFFOLD_FROM_TEMPLATE}" -eq 1 ]]; then
  echo "Scaffold MSA mode       : ${NANOBODY_SCAFFOLD_MSA_MODE}"
  if [[ "${NANOBODY_SCAFFOLD_MSA_MODE}" != "off" ]]; then
    echo "Scaffold MSA mask CDRs  : ${NANOBODY_SCAFFOLD_MSA_MASK_CDRS}"
    echo "Scaffold MSA source     : ${NANOBODY_SCAFFOLD_MSA_BASE_A3M:-not prepared}"
  fi
fi
echo "========================================"

if [[ "${DESIGN_SCHEDULER}" == "cycle-wave" || "${DESIGN_SCHEDULER}" == "resident" ]]; then
  run_designs_cycle_wave "${TARGET_MSA_PATH}"
else
  DESIGN_PIDS=()
  DESIGN_STATUS_FILES=()
  for run_index in $(seq 1 "${N_RUNS}"); do
    wait_for_slot "${MAX_PARALLEL}"
    run_tag="$(printf "run_%03d" "${run_index}")"
    run_status_file="${EXPT_ROOT}/${run_tag}/run_exit_code.txt"
    mkdir -p "${EXPT_ROOT}/${run_tag}"
    printf 'running\n' > "${run_status_file}"
    (
      run_rc=1
      trap 'printf "%s\n" "${run_rc}" > "${run_status_file}"' EXIT
      run_one_design "${run_index}" "${TARGET_MSA_PATH}"
      run_rc=0
    ) &
    DESIGN_PIDS+=("$!")
    DESIGN_STATUS_FILES+=("${run_status_file}")
  done
  # Bash 3.2 can discard statuses for early jobs after a long queue, making a
  # later `wait PID` report that a successfully completed PID is no longer a
  # child. Wait for jobs still tracked, then use durable per-run exit markers.
  set +e
  wait
  set -e
  DESIGN_FAILED=0
  for run_status_file in "${DESIGN_STATUS_FILES[@]}"; do
    run_rc="$(tr -d '[:space:]' < "${run_status_file}" 2>/dev/null || true)"
    if [[ "${run_rc}" != "0" ]]; then
      echo "ERROR: design status ${run_status_file} is ${run_rc:-missing}" >&2
      DESIGN_FAILED=1
    fi
  done
  if [[ "${DESIGN_FAILED}" -ne 0 ]]; then
    die "One or more design runs failed; summaries were not finalized."
  fi
fi

echo "run,cycle,iptm,complex_plddt,binder_sequence,structure_path,confidence_json" > "${EXPT_ROOT}/summary_all_runs.csv"
for run_index in $(seq 1 "${N_RUNS}"); do
  run_tag="$(printf "run_%03d" "$run_index")"
  if [[ -f "${EXPT_ROOT}/${run_tag}/metrics_per_cycle.csv" ]]; then
    tail -n +2 "${EXPT_ROOT}/${run_tag}/metrics_per_cycle.csv" | awk -F',' -v r="$run_index" 'BEGIN{OFS=","} {print r,$1,$2,$3,$6,$5,$4}' >> "${EXPT_ROOT}/summary_all_runs.csv"
  fi
done

echo "run,start_ts,end_ts,duration_sec" > "${EXPT_ROOT}/summary_timing_design.csv"
for run_index in $(seq 1 "${N_RUNS}"); do
  run_tag="$(printf "run_%03d" "$run_index")"
  if [[ -f "${EXPT_ROOT}/${run_tag}/timing_run.csv" ]]; then
    tail -n +2 "${EXPT_ROOT}/${run_tag}/timing_run.csv" >> "${EXPT_ROOT}/summary_timing_design.csv"
  fi
done

if [[ "${MOTIF_SCAFFOLDING}" -eq 1 ]]; then
  echo "design,cycle,motif_positions_1based,motif_ranges_1based,source_motif_ranges_1based" > "${EXPT_ROOT}/motif_positions_by_cycle.csv"
  for run_index in $(seq 1 "${N_RUNS}"); do
    run_tag="$(printf "run_%03d" "$run_index")"
    if [[ -f "${EXPT_ROOT}/${run_tag}/motif_positions_by_cycle.csv" ]]; then
      tail -n +2 "${EXPT_ROOT}/${run_tag}/motif_positions_by_cycle.csv" >> "${EXPT_ROOT}/motif_positions_by_cycle.csv"
    fi
  done
fi

if [[ "$(post_predictors_count)" -gt 0 ]]; then
  for post_pred in "${POST_PREDICTORS[@]}"; do
    pred_safe="$(safe_predictor_name "$post_pred")"
    task_tsv="${EXPT_ROOT}/post_${pred_safe}_tasks.tsv"

    python3 "${POST_TASK_SELECTOR}" \
      --summary "${EXPT_ROOT}/summary_all_runs.csv" \
      --mode "${POST_MODE}" \
      --threshold "${POST_IPTM_THRESHOLD}" \
      --include-cycle00 "${POST_INCLUDE_CYCLE00}" \
      --output "${task_tsv}"

    if [[ -s "$task_tsv" ]]; then
      POST_STATUS_FILES=()
      while IFS=$'\t' read -r run_i cyc_i bseq; do
        wait_for_slot "${MAX_PARALLEL}"
        post_run_tag="$(printf "run_%03d" "${run_i}")"
        post_cycle_tag="$(printf "cycle_%02d" "${cyc_i}")"
        post_status_file="${EXPT_ROOT}/${post_run_tag}/post_${pred_safe}/${post_cycle_tag}/post_exit_code.txt"
        mkdir -p "$(dirname "${post_status_file}")"
        printf 'running\n' > "${post_status_file}"
        (
          post_rc=1
          trap 'printf "%s\n" "${post_rc}" > "${post_status_file}"' EXIT
          run_post_task "$post_pred" "$run_i" "$cyc_i" "$bseq" "$TARGET_MSA_PATH"
          post_rc=0
        ) &
        POST_STATUS_FILES+=("${post_status_file}")
      done < "$task_tsv"
      set +e
      wait
      set -e
      POST_FAILED=0
      for post_status_file in "${POST_STATUS_FILES[@]}"; do
        post_rc="$(tr -d '[:space:]' < "${post_status_file}" 2>/dev/null || true)"
        if [[ "${post_rc}" != "0" ]]; then
          echo "ERROR: post-prediction status ${post_status_file} is ${post_rc:-missing}" >&2
          POST_FAILED=1
        fi
      done
      if [[ "${POST_FAILED}" -ne 0 ]]; then
        die "One or more ${post_pred} post-prediction tasks failed."
      fi
    fi

    aggregate_post_predictor "$post_pred"
  done
fi

build_comparison_tables

echo
echo "Done."
echo "Output root: ${EXPT_ROOT}"
echo "Design summary: ${EXPT_ROOT}/summary_all_runs.csv"
if [[ "${MOTIF_SCAFFOLDING}" -eq 1 ]]; then
  echo "Motif positions: ${EXPT_ROOT}/motif_positions_by_cycle.csv"
fi
if [[ "$(post_predictors_count)" -gt 0 ]]; then
  for pp in "${POST_PREDICTORS[@]}"; do
    psafe="$(safe_predictor_name "$pp")"
    echo "Post summary (${pp}): ${EXPT_ROOT}/summary_post_${psafe}.csv"
  done
fi
