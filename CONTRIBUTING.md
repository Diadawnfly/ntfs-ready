# Contributing

Start with a reproducible failing test. Use disposable NTFS images/test disks, not valuable user data. Do not add forced repairs as a convenience fix.

Run `python3 -m unittest discover -s tests -v` and `bash -n Install.command scripts/*.sh` (expand commands individually if needed). Clearly label injected-runner fixtures; they cannot substitute for integration evidence.

Pull requests should include a safety analysis, failing/passing tests, changed external dependencies and an honest tested/untested matrix. Keep the stdlib-only Python 3.9 baseline. Preserve subprocess argument arrays and strict partition validation. Never add embedded secrets or public personal drive logs.

For driver-level changes, test xattrs, resource forks, rename/delete, Unicode/Windows naming constraints, failure/read-only recovery and Windows-side integrity separately. Do not claim Paragon equivalence without repeatable benchmarks and data-integrity evidence.

The roadmap is native UI, clean-machine installation CI, removable-drive integration tests, and a separately licensed fully open FSKit + NTFS engine implementation after feasibility and signing checks.
