#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIXTURE="$(mktemp -d "${TMPDIR:-/tmp}/iproteinstudio-snapshot.XXXXXX")"
trap 'rm -rf "${FIXTURE}"' EXIT

swiftc -emit-library -static -emit-module -module-name StudioCore \
  "${ROOT}"/Sources/StudioCore/*.swift \
  -emit-module-path "${FIXTURE}/StudioCore.swiftmodule" -o "${FIXTURE}/libStudioCore.a"

swiftc -I "${FIXTURE}" -L "${FIXTURE}" -lStudioCore \
  "${ROOT}/Sources/iProteinStudio/Core/AppPaths.swift" \
  "${ROOT}/Sources/iProteinStudio/Core/InstalledRuntime.swift" \
  "${ROOT}/Tests/PipelineSnapshotContractHarness.swift" \
  -o "${FIXTURE}/snapshot-contract"

IPROTEINSTUDIO_RESOURCE_ROOT="${ROOT}/Sources/iProteinStudio/Resources" \
IPROTEINSTUDIO_TEST_SUPPORT_ROOT="${FIXTURE}/support" \
  "${FIXTURE}/snapshot-contract"

python3 "${ROOT}/Sources/iProteinStudio/Resources/pipeline/scripts/stage_assets.py" \
  --resources "${ROOT}/Sources/iProteinStudio/Resources" --root "${FIXTURE}/headless"
python3 - "${FIXTURE}/support" "${FIXTURE}/headless" <<'PY'
import hashlib, json, sys
from pathlib import Path
gui, cli = map(Path, sys.argv[1:])
inventory = json.loads((cli/'receipts/headless-assets.json').read_text())['files']
seeds = json.loads((cli/'receipts/headless-assets.json').read_text())['created_msa_seeds']
inventory.update(seeds)
for name, expected in inventory.items():
    assert (gui/name).is_file(), 'GUI did not stage '+name
    assert hashlib.sha256((gui/name).read_bytes()).hexdigest()==expected, 'GUI/CLI asset differs: '+name
    assert hashlib.sha256((cli/name).read_bytes()).hexdigest()==expected, 'CLI receipt differs: '+name
print('PASS actual GUI/headless asset parity:',len(inventory),'files, including overlays/examples/MSAs/launchers')
PY
