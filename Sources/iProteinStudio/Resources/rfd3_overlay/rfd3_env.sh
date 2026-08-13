#!/usr/bin/env bash
# Source this file before official Foundry/RFD3 commands.
export DEBUG=false
export TOKENIZERS_PARALLELISM=false
export CCD_MIRROR_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/assets/fluorescein/ccd"
