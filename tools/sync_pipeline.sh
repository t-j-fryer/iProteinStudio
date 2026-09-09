#!/usr/bin/env bash
# Stage an upstream refresh without overwriting Studio-authored policy.
# Usage: tools/sync_pipeline.sh /path/to/upstream
# After review: tools/sync_pipeline.sh --apply build/vendor-review-...
set -euo pipefail
STUDIO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "${STUDIO_ROOT}/tools/vendor_pipeline.py" "$@"
