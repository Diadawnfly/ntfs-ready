# Security policy

This is early-beta filesystem orchestration software. Keep verified backups. No warranty of data integrity is implied by a passed temporary-file test.

## Boundaries

- No passwords/tokens stored by the application; authorization stays in Terminal/system dialogs.
- No setuid binaries, persistent root helper, formatting, forced unmount, forced recovery, hibernation removal, SIP/Gatekeeper disabling, fstab edits or system-driver replacement.
- Device identity and external NTFS eligibility are checked before actions. Names must not inject mount options or escape /Volumes.
- UUID-less MBR partitions use a freshly read, unique IOMedia BSD-name match and positive IORegistryEntryID (`ioreg:ID`). This is an attachment incarnation within the live boot, not a persistent GUID; it is rechecked for selected-session actions and must not be persisted for reconnect/automount.
- Downloads must use HTTPS plus pinned hashes; installer packages must match expected upstream developer identity. Never execute an unverified download.
- Mount failure after unmount must attempt safe native read-only recovery and report recovery failure.
- Logs for public reports must redact volume names, usernames, personal paths and copied filenames.

A third-party kernel extension runs with broad system privilege. Choosing Reduced Security is a material security decision by the user, not a cosmetic install step. FSKit is a possible future alternative, not a hidden fallback in this beta.

## Reporting

Do not publish credentials, private files or raw personal logs in issues. For non-sensitive bugs use GitHub issues with macOS/architecture/component versions, redacted doctor output and exact error. For sensitive vulnerabilities contact the repository owner privately through a suitable GitHub channel; do not assume confidential reporting has been configured until GitHub explicitly shows it.
