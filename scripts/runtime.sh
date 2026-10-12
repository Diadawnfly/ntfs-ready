#!/bin/bash
# Shared by launchers: never invoke an unprovisioned Apple Python shim.
resolve_python() {
    PYTHON=''
    local candidate
    for candidate in /usr/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
        [[ -x "$candidate" ]] || continue
        if [[ "$candidate" == /usr/bin/python3 ]] && ! /usr/bin/xcode-select -p >/dev/null 2>&1; then
            continue
        fi
        if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
            PYTHON="$candidate"
            return 0
        fi
    done
    printf '%s\n' 'Python 3.9+ is required. Install Command Line Tools or Homebrew Python and rerun.' >&2
    return 1
}
