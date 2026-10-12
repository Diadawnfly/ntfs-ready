# Third-party dependencies

The release contains our orchestration source, **not dependency binaries or dependency source code**. MIT applies only to our independently written source; it does not relicense installed dependencies.

| Component | Role | Upstream / license |
| --- | --- | --- |
| Homebrew | Dependency package manager | https://github.com/Homebrew/brew ; BSD-2-Clause |
| gromgit/homebrew-fuse | Community-maintained macOS NTFS-3G formula | https://github.com/gromgit/homebrew-fuse ; consult its current upstream license |
| NTFS-3G | NTFS engine, invoked as a separate executable | https://github.com/tuxera/ntfs-3g ; GPL-2.0-or-later / component-specific notices |
| macFUSE | User-space filesystem bridge plus kernel backend | https://github.com/macfuse/macfuse ; upstream custom/BSD-style license, with additional component notices |
| Apple macOS tools | diskutil, Installer, Terminal, xattr, ditto | Provided by macOS; not redistributed |

**macFUSE is not a fully open-source package.** Its public repository provides some libraries; its kernel extension and other components are closed source. Its license restricts binary bundling/automated installation in commercial software without written permission. This project is free and does not mirror or redistribute its binaries. Anyone commercially redistributing or incorporating this installer must independently review those terms and obtain permission where required. The project's MIT license does not override dependency licenses.

Current upstream terms: https://github.com/macfuse/macfuse/blob/master/LICENSE.txt

Mounty helped inform the original troubleshooting, but its application/code/artwork is **not included**. NTFS Ready neither requires nor claims affiliation with Mounty.

If a future version links to libntfs-3g, its license obligations must be reviewed before choosing the resulting project's license. The current tool invokes a separately installed executable.
