#!/bin/bash
set -euo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
source "$HERE/scripts/runtime.sh"
resolve_python
cd -- "$HERE"
exec "$PYTHON" -m ntfs_ready menu
