#!/bin/bash
# Source-only helpers; dependencies are downloaded, never bundled.
readonly HOMEBREW_VERSION='7.0.9'
readonly HOMEBREW_URL='https://github.com/Homebrew/brew/releases/download/7.0.9/Homebrew.pkg'
readonly HOMEBREW_SHA256='e021295947a4a9b7ca1a8eff310c9ea1db14d923c5acf7d79e325b60a81f1a15'
readonly MACFUSE_VERSION='5.4.0'
readonly MACFUSE_URL='https://github.com/macfuse/macfuse/releases/download/macfuse-5.4.0/macfuse-5.4.0.dmg'
readonly MACFUSE_SHA256='861814f0ac7fa8f6547ea40cdd49a36ac84bcc7d34f38a1fa74e8cf68b0401c5'
readonly MACFUSE_RECEIPT='io.macfuse.installer.components.core'
DEP_WORK=''
DEP_MOUNT=''

dep_fail() { printf 'NTFS Ready dependencies: %s\n' "$*" >&2; exit 1; }
verify_checksum() {
    local actual
    actual="$(shasum -a 256 "$1")" || dep_fail 'Cannot compute SHA-256.'
    actual="${actual%% *}"
    [[ "$actual" == "$2" ]] || dep_fail "SHA-256 mismatch: $1; refusing to open downloaded installer."
}
verify_package() {
    local signature
    signature="$(pkgutil --check-signature "$1" 2>&1)" || dep_fail "Apple package signature validation failed: $signature"
    printf '%s\n' "$signature"
    case "$signature" in
        *"Developer ID Installer: $2 ($3)"*) ;;
        *) dep_fail "Unexpected installer signer; expected $2 ($3)." ;;
    esac
    spctl --assess --type install --verbose=2 "$1" || dep_fail 'Gatekeeper package assessment failed; do not bypass it.'
}
cleanup_dependencies() {
    if [[ -n "$DEP_MOUNT" ]]; then
        if ! hdiutil detach "$DEP_MOUNT" >/dev/null 2>&1; then
            printf 'Could not detach own installer image: %s; preserving download folder.\n' "$DEP_MOUNT" >&2
            return
        fi
    fi
    [[ -z "$DEP_WORK" ]] || rm -rf -- "$DEP_WORK"
}
dep_workspace() {
    if [[ -z "$DEP_WORK" ]]; then
        DEP_WORK="$(mktemp -d "${TMPDIR:-/tmp}/ntfs-ready-install.XXXXXXXX")" || dep_fail 'Cannot create private download folder.'
        trap cleanup_dependencies EXIT
    fi
}
download_verified() {
    curl --fail --location --proto '=https' --proto-redir '=https' --tlsv1.2 \
        --retry 3 --connect-timeout 30 --max-time 600 --output "$2" "$1" || dep_fail 'Download failed; rerun to retry.'
    verify_checksum "$2" "$3"
}
find_brew() {
    BREW=''
    local candidate
    for candidate in /opt/homebrew/bin/brew /usr/local/bin/brew; do
        if [[ -x "$candidate" ]]; then BREW="$candidate"; return 0; fi
    done
    return 1
}
macfuse_version() {
    local info line
    info="$(pkgutil --pkg-info "$MACFUSE_RECEIPT" 2>/dev/null)" || return 1
    while IFS= read -r line; do
        case "$line" in version:\ *) printf '%s\n' "${line#version: }"; return 0 ;; esac
    done <<< "$info"
    return 1
}
version_at_least() {
    "$PYTHON" -c 'import sys
try:
 a,b=(tuple(int(x) for x in v.split(".")) for v in sys.argv[1:])
 sys.exit(0 if a >= b else 1)
except ValueError: sys.exit(2)' "$1" "$2"
}
install_dependencies() {
    # The Apple Python shim may prompt for CLT; never invoke it before this check.
    if ! xcode-select -p >/dev/null 2>&1; then
        printf '%s\n' 'Command Line Tools are missing. Complete the Apple installation dialog, then rerun Install.command.'
        xcode-select --install || dep_fail 'Could not open Command Line Tools installer; install CLT manually and rerun.'
        exit 1
    fi
    resolve_python
    # Validate our own destination before opening any dependency installer.
    "$PYTHON" "$HERE/install_payload.py" check "$SOURCE" "$DEST" || dep_fail 'Own-file preflight failed; dependencies were not changed.'
    if ! find_brew; then
        dep_workspace
        download_verified "$HOMEBREW_URL" "$DEP_WORK/Homebrew-7.0.9.pkg" "$HOMEBREW_SHA256"
        verify_package "$DEP_WORK/Homebrew-7.0.9.pkg" 'Patrick Linnane' '927JGANW46'
        printf '%s\n' 'Complete Homebrew installation in native Installer; close it when finished.'
        open -W -a Installer "$DEP_WORK/Homebrew-7.0.9.pkg" || dep_fail 'Could not open native Installer.'
        find_brew || dep_fail 'Homebrew installation was cancelled or incomplete; rerun when ready.'
    fi
    "$BREW" --version || dep_fail 'Existing Homebrew is not functional.'
    local existing pkg
    existing="$(macfuse_version || true)"
    if [[ -n "$existing" ]] && version_at_least "$existing" "$MACFUSE_VERSION" && [[ -d /Library/Filesystems/macfuse.fs ]]; then
        printf 'Reusing macFUSE %s (tested release: %s); run doctor for compatibility.\n' "$existing" "$MACFUSE_VERSION"
    else
        if [[ -z "$existing" && -e /Library/Filesystems/macfuse.fs ]]; then
            dep_fail 'Unrecognized macFUSE installation without receipt; inspect manually before rerunning.'
        fi
        dep_workspace
        download_verified "$MACFUSE_URL" "$DEP_WORK/macfuse-5.4.0.dmg" "$MACFUSE_SHA256"
        DEP_MOUNT="$DEP_WORK/macfuse"
        mkdir -- "$DEP_MOUNT"
        hdiutil attach -readonly -nobrowse -mountpoint "$DEP_MOUNT" "$DEP_WORK/macfuse-5.4.0.dmg" || dep_fail 'Could not mount verified macFUSE image.'
        pkg="$DEP_MOUNT/Install macFUSE.pkg"
        [[ -e "$pkg" ]] || pkg="$DEP_MOUNT/Extras/macFUSE5.4.0.pkg"
        [[ -e "$pkg" ]] || pkg="$DEP_MOUNT/Extras/macFUSE 5.4.0.pkg"
        [[ -e "$pkg" ]] || dep_fail 'Expected official macFUSE package was not found.'
        verify_package "$pkg" 'Benjamin Fleischer' '3T5GSNBU6W'
        printf '%s\n' 'Complete macFUSE installation in native Installer; close it when finished.'
        open -W -a Installer "$pkg" || dep_fail 'Could not open native Installer.'
        existing="$(macfuse_version || true)"
        [[ "$existing" == "$MACFUSE_VERSION" && -d /Library/Filesystems/macfuse.fs ]] || dep_fail 'macFUSE receipt/files not verified; installation may have been cancelled. Rerun after completing it.'
    fi
    if ! "$BREW" list --versions gromgit/fuse/ntfs-3g-mac >/dev/null 2>&1; then
        printf '%s\n' 'Installing NTFS-3G from THIRD-PARTY community tap gromgit/fuse (not Apple/Homebrew core). This grants Homebrew trust to that tap.'
        "$BREW" tap gromgit/fuse || dep_fail 'Could not add community tap.'
        if "$BREW" help trust >/dev/null 2>&1; then
            "$BREW" trust --tap gromgit/fuse || dep_fail 'Could not trust the community tap.'
        fi
        "$BREW" install gromgit/fuse/ntfs-3g-mac || dep_fail 'NTFS-3G installation failed; no NTFS Ready payload installed.'
    fi
    "$BREW" list --versions gromgit/fuse/ntfs-3g-mac || dep_fail 'NTFS-3G installation could not be verified.'
    printf '%s\n' 'macFUSE kernel authorization is manual. Follow official macFUSE Getting Started instructions, approve its developer in Privacy & Security and restart if requested.' \
        'Apple Silicon startup-security changes require your explicit decision in Recovery. This installer never disables SIP or Gatekeeper or changes startup security.' \
        'NTFS Ready is open-source orchestration; the macFUSE kernel component is not a fully open-source stack.'
}
