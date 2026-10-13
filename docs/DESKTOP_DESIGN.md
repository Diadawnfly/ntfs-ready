# NTFS Ready desktop design

## Surface: Operate

A real macOS utility for selecting and operating on a storage volume—not a marketing dashboard or a fabricated drive monitor.

The general volume-selection / mount-status / action model is a familiar storage-tool pattern. The composition, copy and styling here are original; no Paragon artwork, branding or proprietary interface assets are copied.

## Composition

- Native macOS window and toolbar, plus menu-bar entry.
- Compact sidebar: actual NTFS volumes, diagnostics, about.
- Detail pane: selected volume, explicit mount state, capacity only when actually reported, and primary action.
- Progressive disclosure for implementation details and troubleshooting.
- Empty and unknown states explain what is missing rather than displaying sample metrics.

## Visual vocabulary

- Native San Francisco typography, chosen for macOS legibility and text sizing.
- Neutral window/content surfaces, restrained separation, one emerald interaction accent.
- Semantic success/warning/error colors convey state; no decorative rainbow or glossy gradients.
- System appearance adapts light/dark colors.
- Native SF Symbols only where they improve navigation/action scanning.

## Safety and honest states

- Read-only, writable-mounted, unmounted and unknown are different states.
- A writable mount is not a promise of data integrity or a successful Finder GUI test.
- Every mutation requires explicit confirmation; verification mentions temporary files.
- Passwords are never entered or stored in the app. Privileged actions hand off to a private, validated script opened in system Terminal, then report a nonce-checked result back to the GUI.
- No formatting, forced repair, system-security bypass or automatic drive mutation on refresh.
- Private operation results stay in the user's own cache; do not publish raw drive logs.

## Build and distribution

`Build Desktop.command` builds an app using available developer tools without changing global xcode-select or accepting a license on the user's behalf. The local bundle contains only our source backend and installer, not vendor driver binaries or a Python interpreter.

This desktop build targets macOS 13+. Local builds receive ad-hoc signing, not Developer-ID signing or notarization. The Python/backend prerequisites and third-party macFUSE licensing still apply.

## Primary references

- Apple sidebars: https://developer.apple.com/design/human-interface-guidelines/sidebars
- Apple MenuBarExtra: https://developer.apple.com/documentation/swiftui/menubarextra
- General storage-tool workflow: https://kb.paragon-software.com/article/727
