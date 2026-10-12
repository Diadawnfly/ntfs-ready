import unittest, tempfile, pathlib, subprocess, sys, zipfile, hashlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
BUILDER = ROOT / 'tools' / 'build_release.py'
RUNTIME_INPUTS = (
    'Install.command', 'scripts/install.sh', 'scripts/dependencies.sh',
    'scripts/runtime.sh', 'scripts/Launcher.command', 'scripts/uninstall.sh',
    'scripts/install_payload.py', 'ntfs_ready/__init__.py',
    'ntfs_ready/__main__.py', 'ntfs_ready/cli.py', 'ntfs_ready/core.py',
    'README.md', 'LICENSE',
)


def fixture_source(src, missing=None):
    """Synthetic builder inputs only; not runnable project/install payloads."""
    for relative in RUNTIME_INPUTS:
        if relative == missing:
            continue
        destination = src / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.suffix == '.py':
            content = '# Synthetic release-builder fixture; not production code.\n'
        elif destination.suffix in ('.sh', '.command'):
            content = '#!/bin/bash\n# Synthetic builder fixture; never install.\nexit 1\n'
        else:
            content = 'Synthetic release-builder fixture; not a production install.\n'
        destination.write_text(content)


class ReleaseTests(unittest.TestCase):
    def test_release_refuses_each_missing_runtime_input(self):
        for missing in RUNTIME_INPUTS:
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as tmp:
                src = pathlib.Path(tmp) / 'source'
                out = pathlib.Path(tmp) / 'out'
                fixture_source(src, missing=missing)
                result = subprocess.run([sys.executable, str(BUILDER), '--source', str(src),
                                         '--output', str(out)], capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Missing required release input: ' + missing, result.stderr)
                self.assertFalse(out.exists())

    def test_release_packages_only_project_sources_and_executable_launcher(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = pathlib.Path(tmp) / 'source'
            out = pathlib.Path(tmp) / 'out'
            fixture_source(src)
            (src / '.env').write_text('DO_NOT_PUBLISH=secret\n')
            (src / 'drive-log.txt').write_text('PRIVATE_DEVICE_LOG\n')
            p = subprocess.run([sys.executable, str(BUILDER), '--source', str(src), '--output', str(out)], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            archives = list(out.glob('*.zip'))
            self.assertEqual(len(archives), 1)
            with zipfile.ZipFile(archives[0]) as z:
                names = z.namelist()
                for relative in RUNTIME_INPUTS:
                    self.assertIn('NTFS-Ready/' + relative, names)
                self.assertFalse(any('.env' in n or 'drive-log' in n for n in names))
                for relative in RUNTIME_INPUTS:
                    mode = z.getinfo('NTFS-Ready/' + relative).external_attr >> 16
                    self.assertEqual(bool(mode & 0o111), pathlib.Path(relative).suffix in ('.sh', '.command'))
                self.assertEqual(z.read('NTFS-Ready/scripts/install_payload.py'),
                                 (src / 'scripts/install_payload.py').read_bytes())
            digest = hashlib.sha256(archives[0].read_bytes()).hexdigest()
            self.assertIn(digest, (out / 'SHA256SUMS.txt').read_text())

if __name__ == '__main__':
    unittest.main()
