# macFUSE kernel approval on Apple Silicon

These are manual Apple security decisions. The installer never changes them for you. Save work before shutting down. Do not run `csrutil disable`; SIP and Gatekeeper remain enabled.

1. After macFUSE installation/load attempt, open System Settings → Privacy & Security.
2. If "Enable System Extensions" appears, use the native prompt and shut down.
3. Hold the power button until startup options appear; choose Options → Continue.
4. In Recovery open Startup Security Utility, choose the **macOS startup disk**, then Security Policy.
5. Select Reduced Security and **Allow user management of kernel extensions from identified developers**. Confirm and restart.
6. Back in Privacy & Security approve the macFUSE developer **Benjamin Fleischer**, when prompted, and restart again if macOS requires it.
7. Rerun the launcher/doctor. A file-system-extension toggle for the FSKit backend is different from kernel approval; this version uses the kernel backend.

Do not select or erase the external NTFS disk in Recovery. If organizational policy forbids these changes, stop: this backend is unsuitable. Use another filesystem/user-space solution rather than bypass policy.

Official source, consult for current screenshots/instructions: https://github.com/macfuse/macfuse/wiki/Getting-Started
