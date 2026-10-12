"""Installer tests run only in disposable homes; never install dependencies."""
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    def run_script(self, *args, script=None, home=None):
        env = os.environ.copy()
        env.pop('PYTHONDONTWRITEBYTECODE', None)
        if home:
            env['HOME'] = str(home)
        return subprocess.run(['/bin/bash', str(script or ROOT / 'scripts/install.sh'), *args],
                              env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    @unittest.skipUnless(platform.system() == 'Darwin' and os.getuid() != 0, 'macOS normal-user installation')
    def test_no_deps_installs_whitelist_in_home_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix='ntfs ready test ') as temp:
            root = Path(temp).resolve() / 'source with spaces'
            home = Path(temp).resolve() / 'home with spaces'
            home.mkdir()
            root.mkdir()
            shutil.copytree(ROOT / 'scripts', root / 'scripts')
            shutil.copy2(ROOT / 'Install.command', root / 'Install.command')
            package = root / 'ntfs_ready'
            package.mkdir()
            (package / '__init__.py').write_text('')
            (package / '__main__.py').write_text("print('FIXTURE menu')\n")
            (root / 'secret.txt').write_text('must not copy')
            result = self.run_script('--no-deps', script=root / 'Install.command', home=home)
            self.assertEqual(result.returncode, 0, result.stdout)
            dest = home / 'Library/Application Support/NTFS Ready'
            self.assertTrue((dest / 'ntfs_ready/__main__.py').is_file())
            self.assertFalse((dest / 'secret.txt').exists())
            self.assertTrue(os.access(dest / 'Launcher.command', os.X_OK))
            launch = self.run_script(script=dest / 'Launcher.command', home=home)
            self.assertEqual(launch.returncode, 0, launch.stdout)
            self.assertIn('FIXTURE menu', launch.stdout)
            self.assertFalse((dest / 'ntfs_ready/__pycache__').exists())
            user_file = dest / 'personal.txt'
            user_file.write_text('keep me')
            again = self.run_script('--no-deps', script=root / 'Install.command', home=home)
            self.assertEqual(again.returncode, 0, again.stdout)
            self.assertEqual(user_file.read_text(), 'keep me')
            uninstall = self.run_script(script=dest / 'scripts/uninstall.sh', home=home)
            self.assertEqual(uninstall.returncode, 0, uninstall.stdout)
            self.assertEqual(user_file.read_text(), 'keep me')
            self.assertFalse((dest / 'ntfs_ready').exists())
            self.assertTrue((root / 'ntfs_ready').exists())

    def test_payload_preserves_unknown_modified_and_symlink_targets(self):
        import sys
        helper = ROOT / 'scripts/install_payload.py'
        with tempfile.TemporaryDirectory(prefix='ntfs ready test ') as temp:
            base = Path(temp).resolve()
            root = base / 'source'
            shutil.copytree(ROOT / 'scripts', root / 'scripts')
            (root / 'ntfs_ready').mkdir()
            (root / 'ntfs_ready/__main__.py').write_text('pass\n')
            dest = base / 'payload'
            dest.mkdir()
            unknown = dest / 'Launcher.command'
            unknown.write_text('unowned')
            def operation(action):
                args = [sys.executable, str(helper), action, str(root), str(dest)] if action == 'install' else [sys.executable, str(helper), action, str(dest)]
                return subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            rejected = operation('install')
            self.assertNotEqual(rejected.returncode, 0)
            self.assertEqual(unknown.read_text(), 'unowned')
            self.assertFalse((dest / 'ntfs_ready').exists())
            unknown.unlink()
            outside = base / 'outside'
            outside.mkdir()
            (dest / 'ntfs_ready').symlink_to(outside, target_is_directory=True)
            self.assertNotEqual(operation('install').returncode, 0)
            self.assertEqual(list(outside.iterdir()), [])
            (dest / 'ntfs_ready').unlink()
            installed = operation('install')
            self.assertEqual(installed.returncode, 0, installed.stdout)
            modified = dest / 'ntfs_ready/__main__.py'
            modified.write_text('user edited this')
            rejected = operation('install')
            self.assertNotEqual(rejected.returncode, 0)
            self.assertEqual(modified.read_text(), 'user edited this')
            removed = operation('uninstall')
            self.assertEqual(removed.returncode, 0, removed.stdout)
            self.assertEqual(modified.read_text(), 'user edited this')
            self.assertFalse((dest / 'Launcher.command').exists())

    def test_missing_clt_requests_install_once_and_stops(self):
        command = '''source "$1"
        xcode-select() {
            case "$1" in -p) return 1 ;; --install) printf 'CLT_REQUESTED\\n'; return 0 ;; esac
        }
        resolve_python() { printf 'UNEXPECTED_PYTHON_CHECK\\n'; return 1; }
        install_dependencies
        '''
        result = subprocess.run(['/bin/bash', '-c', command, 'test', str(ROOT / 'scripts/dependencies.sh')],
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout.count('CLT_REQUESTED'), 1)
        self.assertNotIn('UNEXPECTED_PYTHON_CHECK', result.stdout)
        self.assertIn('rerun', result.stdout)

    def test_non_macos_is_rejected(self):
        command = 'uname() { printf "Linux\\n"; }; export -f uname; /bin/bash "$1" --dry-run'
        result = subprocess.run(['/bin/bash', '-c', command, 'test', str(ROOT / 'scripts/install.sh')],
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('macOS only', result.stdout)

    def test_uninstall_without_marker_removes_nothing(self):
        import sys
        with tempfile.TemporaryDirectory(prefix='ntfs ready test ') as temp:
            dest = Path(temp).resolve()
            personal = dest / 'personal.txt'
            personal.write_text('keep me')
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/install_payload.py'), 'uninstall', str(dest)],
                                    text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(personal.read_text(), 'keep me')

    def test_payload_preflight_does_not_write(self):
        import sys
        with tempfile.TemporaryDirectory(prefix='ntfs ready test ') as temp:
            root = Path(temp).resolve() / 'source'
            shutil.copytree(ROOT / 'scripts', root / 'scripts')
            (root / 'ntfs_ready').mkdir()
            (root / 'ntfs_ready/__main__.py').write_text('pass\n')
            dest = Path(temp).resolve() / 'not created'
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/install_payload.py'), 'check', str(root), str(dest)],
                                    text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertFalse(dest.exists())

    def test_default_install_wires_dependency_checks(self):
        content = (ROOT / 'scripts/install.sh').read_text()
        self.assertIn('source "$HERE/dependencies.sh"', content)
        self.assertIn('install_dependencies', content)
        self.assertLess(content.index('install_dependencies'), content.index('install_payload.py'))

    def test_root_is_rejected_before_dry_run(self):
        # Simulate the identity command only; do not run sudo on the host.
        command = 'id() { printf "0\\n"; }; export -f id; /bin/bash "$1" --dry-run'
        result = subprocess.run(['/bin/bash', '-c', command, 'test', str(ROOT / 'scripts/install.sh')],
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertNotEqual(result.returncode, 0)
        if platform.system() == 'Darwin':
            self.assertIn('Do not run as root', result.stdout)

    def test_shell_entrypoints_are_executable_and_valid(self):
        for path in (ROOT / 'Install.command', *(ROOT / 'scripts' / n for n in
                     ('install.sh', 'uninstall.sh', 'Launcher.command', 'runtime.sh', 'dependencies.sh'))):
            with self.subTest(path=path.name):
                self.assertTrue(os.access(path, os.X_OK), str(path))
                check = subprocess.run(['/bin/bash', '-n', str(path)], capture_output=True, text=True)
                self.assertEqual(check.returncode, 0, check.stderr)

    def test_dependency_checksum_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as temp:
            payload = Path(temp) / 'download.pkg'
            payload.write_bytes(b'tampered')
            command = 'source "$1"; verify_checksum "$2" "0000000000000000000000000000000000000000000000000000000000000000"'
            result = subprocess.run(['/bin/bash', '-c', command, 'test', str(ROOT / 'scripts/dependencies.sh'), str(payload)],
                                    text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('SHA-256', result.stdout)

    def test_package_signature_is_fail_closed(self):
        helper = ROOT / 'scripts/dependencies.sh'
        # Test doubles are shell functions, never installed in the live PATH.
        for signature_status, signature, gate_status, expected in (
                (0, 'Developer ID Installer: Patrick Linnane (927JGANW46)', 0, 0),
                (1, 'Developer ID Installer: Patrick Linnane (927JGANW46)', 0, 1),
                (0, 'Developer ID Installer: Attacker (AAAAAAAAAA)', 0, 1),
                (0, 'Developer ID Installer: Patrick Linnane (927JGANW46)', 1, 1)):
            with self.subTest(signature=signature, status=signature_status, gate=gate_status):
                command = '''source "$1"
                pkgutil() { printf '%s\\n' "$3"; return "$2"; }
                spctl() { return "$4"; }
                # Freeze arguments for the test doubles before invoking helpers.
                SIG_STATUS="$2"; SIGNATURE="$3"; GATE_STATUS="$4"
                pkgutil() { printf '%s\\n' "$SIGNATURE"; return "$SIG_STATUS"; }
                spctl() { return "$GATE_STATUS"; }
                verify_package fixture.pkg 'Patrick Linnane' '927JGANW46'
                '''
                result = subprocess.run(['/bin/bash', '-c', command, 'test', str(helper), str(signature_status), signature, str(gate_status)],
                                        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                self.assertEqual(result.returncode == 0, expected == 0, result.stdout)

    def test_dependency_metadata_uses_requested_pins(self):
        helper = ROOT / 'scripts/dependencies.sh'
        self.assertTrue(helper.is_file(), 'dependency verification helper missing')
        content = helper.read_text()
        for value in ('Homebrew-7.0.9.pkg', 'macfuse-5.4.0.dmg',
                      'e021295947a4a9b7ca1a8eff310c9ea1db14d923c5acf7d79e325b60a81f1a15',
                      '861814f0ac7fa8f6547ea40cdd49a36ac84bcc7d34f38a1fa74e8cf68b0401c5',
                      '3T5GSNBU6W', '927JGANW46', 'Extras/macFUSE5.4.0.pkg'):
            self.assertIn(value, content)

    def test_dry_run_has_plan_and_leaves_home_untouched(self):
        with tempfile.TemporaryDirectory(prefix='ntfs ready test ') as temp:
            home = Path(temp) / 'home with spaces'
            home.mkdir()
            result = self.run_script('--dry-run', home=home)
            if platform.system() != 'Darwin' or os.getuid() == 0:
                self.assertNotEqual(result.returncode, 0)
            else:
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertIn('Homebrew 7.0.9', result.stdout)
                self.assertIn('macFUSE 5.4.0', result.stdout)
                self.assertIn('manual', result.stdout)
            self.assertEqual(list(home.iterdir()), [])

    def test_unknown_option_is_rejected(self):
        result = self.run_script('--not-an-option')
        self.assertEqual(result.returncode, 2)

    def test_help_explains_safe_options(self):
        result = self.run_script('--help')
        self.assertEqual(result.returncode, 0, result.stdout)
        for option in ('--dry-run', '--no-deps'):
            self.assertIn(option, result.stdout)


if __name__ == '__main__':
    unittest.main()
