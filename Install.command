#!/bin/bash
set -euo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
exec /bin/bash "$HERE/scripts/install.sh" "$@"
