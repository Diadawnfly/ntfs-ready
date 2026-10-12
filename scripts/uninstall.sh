#!/bin/bash
set -euo pipefail
case "${1:-}" in
    --help|-h) printf '%s\n' 'Remove only unchanged NTFS Ready owned files. Preserve user files and all dependencies.'; exit 0 ;;
    '') ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; exit 2 ;;
esac
[[ "$(uname -s)" == Darwin && "$(id -u)" != 0 ]] || { printf '%s\n' 'Run on macOS as your normal user.' >&2; exit 1; }
[[ "${HOME:-}" == /* && "$HOME" != / ]] || exit 1
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
source "$HERE/runtime.sh"
resolve_python
exec "$PYTHON" "$HERE/install_payload.py" uninstall "$HOME/Library/Application Support/NTFS Ready"
