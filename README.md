# NTFS Ready

**A free, open-source setup and safe-mounting tool for NTFS on macOS.**

Download the release ZIP, extract it, and double-click **Install.command**. The installer guides you through prerequisites and installs a local launcher. No copy-paste network installer, no hardcoded disk number, no password storage.

> **Early beta, not a filesystem driver.** Our orchestration code is MIT licensed. It invokes separately installed NTFS-3G and macFUSE; modern macFUSE includes closed-source components. This is **not a fully open-source driver stack**, a Paragon clone, or a claim of equivalent performance/reliability. macOS security approvals and restarts cannot be automated away.

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

Other hardware/macOS releases, fresh-machine end-to-end installation, performance, Windows-side filesystem checks, power loss and interrupted writes are **not established by that result**. Keep backups. This beta does not provide background automounting, a native menu-bar app, or a direct FSKit backend. UI and fully open FSKit-engine integration are future work, not implemented claims.

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
