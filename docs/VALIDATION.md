# Validation record

This record separates executed system checks from simulated unit tests. It is not a benchmark or a promise of data integrity.

## Environment

- Apple Silicon, macOS 27.0.1
- System Python 3.9.6
- macFUSE 5.4.0; NTFS-3G 2026.9.28

## Executed checks

- Source-only ZIP built, extracted, and its installer run with `--no-deps`: own payload installed successfully.
- Own-file installation exercised with existing dependencies, including ownership-manifest checks and repeat installation. No vendor package needed to be reinstalled on this host.
- Installer `--dry-run`, CLI help/version, read-only doctor, and malformed-device rejection exercised directly.
- A newly generated **disposable MBR NTFS disk image**, not a user data disk, was attached. Real diskutil/IOMedia output verified UUID-less identity discovery and mount dry-run.
- This live check caught macOS 27's writable-key aliases, absence of UUID fields, and mounted/unmounted `TotalSize` changes. Regression coverage uses stable physical-size fields and live attachment identity rather than guessing a persistent UUID.
- The underlying original workflow was separately confirmed on a physical NTFS SSD, with basic operations, xattrs and metadata-preserving ditto plus a user-confirmed successful Finder copy. That earlier result is **not equivalent to testing every new CLI path**.

## Final CLI integration

The full installed-CLI disposable-image test must be recorded separately after execution. A prior attempt timed out awaiting interactive sudo authorization and is **not a pass**.

## Automated tests

The final local `python3 -m unittest discover -s tests -v` run passed **82 tests** on the environment above. The final source ZIP was rebuilt, extracted, and its `Install.command --no-deps` successfully installed the actual payload. Independent reviews passed after the compatibility and release-completeness fixes.

Tests include simulated diskutil/IOKit records, injected command runners, disposable local file I/O, installer staging under temporary homes, signature failure test doubles, and release completeness checks. They do not silently mount real disks in CI.

## Not established

- Fresh-machine end-to-end vendor-package GUI installation.
- Other macOS releases/hardware and long-term repeated unplug/reconnect behavior.
- Paragon performance/feature equivalence.
- Windows-side filesystem checks, sudden power loss, interrupted writes or recovery guarantees.
- Direct FSKit integration, background automounting, Developer-ID signing/notarization, or a native menu-bar application.

Use verified backups and keep this release marked beta.
