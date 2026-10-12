#!/bin/bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PYTHON="/Library/Developer/CommandLineTools/usr/bin/python3"
if [[ ! -x "$PYTHON" ]]; then
    PYTHON="/usr/bin/python3"
fi
exec "$PYTHON" -B "$ROOT/tools/build_desktop.py" "$@"
