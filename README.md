# NTFS Ready

**A free, open-source setup and safe-mounting tool for NTFS on macOS.**

Choose the native desktop preview below, or the separately packaged v0.1 terminal installer. No copy-paste network installer, no hardcoded disk number, no password storage.

> **Early beta, not a filesystem driver.** Our orchestration code is MIT licensed. It invokes separately installed NTFS-3G and macFUSE; modern macFUSE includes closed-source components. This is **not a fully open-source driver stack**, a Paragon clone, or a claim of equivalent performance/reliability. macOS security approvals and restarts cannot be automated away.

## Native desktop preview — v0.2.0-preview

[Download the Apple Silicon desktop preview](https://github.com/Diadawnfly/ntfs-ready/releases/tag/v0.2.0-preview): extract `NTFS-Ready-Desktop-0.2.0-preview-arm64.zip` and open **NTFS Ready.app**. This is a native SwiftUI window with a drive sidebar, real status/capacity, explicit actions, diagnostics and menu-bar entry. It uses an installed Python 3.9+ runtime and separately installed macFUSE/NTFS-3G.

![Actual native application with disposable NTFS test volume](docs/screenshots/desktop-light.png)

**Preview limitations:** ad-hoc signed, not Developer-ID signed/notarized. Authorization still opens system Terminal. Live read-only discovery/display and package signatures have been checked; the GUI confirmation → Terminal authorization → writable mount/verification lifecycle has **not** completed end-to-end validation. Do not use valuable data as a test fixture. See [desktop build and validation](docs/DESKTOP.md).

The `Install.command` instructions below apply to the **separate v0.1 terminal package**, not the desktop ZIP.

## Why this exists

A minimal NTFS mount can pass a plain file-write test yet fail in Finder with **error 100102**. The verified workflow includes macFUSE `auto_xattr`, and checks extended attributes and a metadata-preserving copy, not just creating a file.

NTFS Ready is independent of Mounty. It does not copy, bundle, mirror, or require the Mounty application. It uses the same underlying driver family through its own installer, diagnostics and command-line menu.

## Install

1. Download `NTFS-Ready-0.1.0-beta.zip` and `SHA256SUMS.txt` from [Releases](https://github.com/Diadawnfly/ntfs-ready/releases).
2. Optionally verify: `shasum -a 256 -c SHA256SUMS.txt` with both files in the same folder.
3. Extract the ZIP and double-click **Install.command**.
4. Follow the native installer and authorization prompts. If Command Line Tools are absent, finish their installation and rerun the launcher.
5. On Apple Silicon, the macFUSE **kernel backend** requires Reduced Security with identified-developer kernel-extension management in Recovery, developer approval, and a restart. See [security setup](docs/SECURITY_SETUP.md). **Do not disable SIP or Gatekeeper.**

“Double-click install” means one entry point, **not zero permissions or zero restarts**. This beta is not Developer-ID signed/notarized. If macOS declines to open the script, review the source and run `bash Install.command` from Terminal in the extracted folder; do not globally disable system protections.

Dependencies are downloaded from their own upstream sources, not vendored in our release. The initial bootstrap pins and checks Homebrew and macFUSE downloads. NTFS-3G is obtained through the explicitly identified community Homebrew tap; its version can change independently of this project.

## Use

Open the installed launcher, select a drive, and confirm the operation. Close files and cancel pending copies before remounting. Disk identifiers are discovered live: they can change after reconnecting or restarting.

For developers, from the repository root:

```sh
python3 -m ntfs_ready list
python3 -m ntfs_ready doctor
python3 -m ntfs_ready menu
```

Advanced commands accept a partition identifier returned by `list`:

```text
python3 -m ntfs_ready mount <partition> --dry-run
python3 -m ntfs_ready mount <partition> --yes
python3 -m ntfs_ready verify <partition> --yes
python3 -m ntfs_ready unmount <partition>
```

- Only confirmed **external NTFS partitions** are eligible.
- Never formats, repairs, removes hibernation files, forces unmounts, replaces Apple's drivers, or edits `fstab`.
- Uses `norecover`; unsuitable volumes are refused rather than forcibly repaired.
- Normally unmounts before probing exclusive write mountability.
- Verifies the real mount state; a successful process exit is insufficient.
- Restores native read-only mounting after post-unmount errors, and reports restoration errors.
- `verify` creates only uniquely named temporary test files. It checks contents, extended attributes, metadata-preserving copy, rename and cleanup; existing user files are not test fixtures.
- Uses interactive system/Terminal authorization; no stored password, permanent privileged daemon, or setuid helper.

## Compatibility and limitations

The underlying workflow has been exercised on **Apple Silicon, macOS 27.0.1, macFUSE 5.4.0, NTFS-3G 2026.9.28** with a physical NTFS SSD and confirmed Finder copying. The project CLI and installer receive separate tests; see [validation](docs/VALIDATION.md) for what was actually exercised.

Other hardware/macOS releases, fresh-machine end-to-end installation, performance, Windows-side filesystem checks, power loss and interrupted writes are **not established by that result**. Keep backups. The v0.1 terminal package has no native interface. The separate v0.2 desktop preview adds a native window and menu-bar entry, with its own [validation boundaries](docs/DESKTOP.md). Background automounting and a direct fully open FSKit engine remain future work.

## Development

Python 3.9+, standard library only. No Python runtime dependencies.

```sh
python3 -m unittest discover -s tests -v
python3 tools/build_release.py --output dist
```

Tests of OS command sequencing use clearly identified fixtures/injected runners; they do not prove real kernel behavior. Integration verification requires macOS and an explicitly selected test volume.

## License and credits

Our source: [MIT](LICENSE). Dependencies retain their own licenses: [notices](THIRD_PARTY_NOTICES.md). Please read [security policy](SECURITY.md) and [contributing](CONTRIBUTING.md). This project is not endorsed by Apple, Paragon, Tuxera, macFUSE or Mounty.

[中文说明](README.zh-CN.md)
