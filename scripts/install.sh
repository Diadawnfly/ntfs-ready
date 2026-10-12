#!/bin/bash
set -euo pipefail
# Finder's environment is sparse; use only system tools and explicit brew paths.
export PATH=/usr/bin:/bin:/usr/sbin:/sbin
umask 077
usage() {
    printf '%s\n' 'NTFS Ready installer (macOS, run as your normal user)' \
        'Usage: Install.command [--dry-run] [--no-deps] [--help]' \
        '--dry-run: print plan without writing, downloading or installing anything' \
        '--no-deps: install only NTFS Ready; leave Homebrew/macFUSE/NTFS-3G alone'
}
DRY_RUN=0
NO_DEPS=0
for arg in "$@"; do
    case "$arg" in
        --help|-h) usage; exit 0 ;;
        --dry-run) DRY_RUN=1 ;;
        --no-deps) NO_DEPS=1 ;;
        *) printf 'Unknown option: %s\n' "$arg" >&2; exit 2 ;;
    esac
done
fail() { printf 'NTFS Ready: %s\n' "$*" >&2; exit 1; }
[[ "$(uname -s)" == Darwin ]] || fail 'This installer supports macOS only.'
[[ "$(id -u)" != 0 ]] || fail 'Do not run as root or with sudo; Homebrew requires your normal user.'
[[ "${HOME:-}" == /* && "$HOME" != / ]] || fail 'HOME must be an absolute user home directory.'
DEST="$HOME/Library/Application Support/NTFS Ready"
if [[ "$DRY_RUN" == 1 ]]; then
    printf 'DRY RUN: install owned Python package and launchers in %s\n' "$DEST"
    if [[ "$NO_DEPS" == 0 ]]; then
        printf '%s\n' 'Check CLT and Python 3.9+; missing CLT opens xcode-select --install then stops.' \
            'Install missing Homebrew 7.0.9 and macFUSE 5.4.0 with pinned HTTPS downloads, SHA-256, Apple signature and Gatekeeper checks, via native Installer.' \
            'Reuse existing newer dependencies; trust third-party community gromgit/fuse tap and install ntfs-3g-mac.' \
            'Kernel authorization/startup security approval is manual; never disable SIP or Gatekeeper.'
    else
        printf '%s\n' 'Own files only; check Python 3.9+; do not change dependencies.'
    fi
    exit 0
fi
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
SOURCE="$(cd -- "$HERE/.." && pwd -P)"
source "$HERE/runtime.sh"
[[ -f "$SOURCE/ntfs_ready/__main__.py" ]] || fail 'Source package is missing; use a complete NTFS Ready release.'
if [[ "$NO_DEPS" == 0 ]]; then
    source "$HERE/dependencies.sh"
    install_dependencies
else
    resolve_python
fi
"$PYTHON" "$HERE/install_payload.py" install "$SOURCE" "$DEST"
printf '%s\n' 'Open Launcher.command in the installed folder to start the menu.'
# --no-deps is useful for unattended own-file staging; do not open a GUI then.
if [[ "$NO_DEPS" == 0 ]]; then
    open -R "$DEST/Launcher.command" || printf 'Open this folder manually: %s\n' "$DEST"
fi
