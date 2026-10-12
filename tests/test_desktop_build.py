import importlib.util
import os
import subprocess
import sys
import pathlib
import plistlib
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
BUILDER=ROOT/'tools/build_desktop.py'

class DesktopBundleTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == 'darwin' and pathlib.Path('/Library/Developer/CommandLineTools/usr/bin/python3').is_file(), 'Requires the installed macOS CLT Python')
    def test_build_entrypoint_help_uses_installed_python_not_active_sdk_shim(self):
        env = dict(os.environ, DEVELOPER_DIR='/nonexistent-ntfs-ready-sdk')
        result = subprocess.run(['/bin/bash', str(ROOT/'Build Desktop.command'), '--help'], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('usage:', result.stdout)

    def test_copy_refuses_symlink_destination_without_touching_other_file(self):
        self.assertTrue(BUILDER.is_file())
        spec=importlib.util.spec_from_file_location('desktop_builder_symlink',BUILDER)
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            base=pathlib.Path(tmp).resolve()
            src=base/'source.py'
            victim=base/'unrelated.txt'
            destination=base/'target.py'
            src.write_text('new source')
            victim.write_text('unchanged')
            destination.symlink_to(victim)
            with self.assertRaises(ValueError):
                module.copy_file(src,destination)
            self.assertEqual(victim.read_text(),'unchanged')

    def test_resources_bundle_real_backend_and_safe_installer_only(self):
        self.assertTrue(BUILDER.is_file(), 'Desktop bundle builder is missing')
        spec=importlib.util.spec_from_file_location('desktop_builder',BUILDER)
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            base=pathlib.Path(tmp).resolve()
            root=base/'source'
            (root/'ntfs_ready').mkdir(parents=True)
            (root/'scripts').mkdir()
            for name in ('__init__.py','__main__.py','core.py','cli.py','gui_bridge.py'):
                (root/'ntfs_ready'/name).write_text('# synthetic packaging fixture only\n')
            for name in ('install.sh','dependencies.sh','runtime.sh','Launcher.command','uninstall.sh','install_payload.py'):
                (root/'scripts'/name).write_text('# synthetic packaging fixture only\n')
            for name in ('Install.command','LICENSE','THIRD_PARTY_NOTICES.md'):
                (root/name).write_text('Synthetic test fixture\n')
            (root/'ntfs_ready'/'private.log').write_text('DO_NOT_PACKAGE')
            (root/'.env').write_text('DO_NOT_PACKAGE')
            app=base/'NTFS Ready.app'
            module.stage_resources(root,app)
            resources=app/'Contents/Resources'
            self.assertTrue((resources/'backend/ntfs_ready/gui_bridge.py').is_file())
            self.assertTrue((resources/'installer/scripts/install_payload.py').is_file())
            self.assertTrue((resources/'installer/Install.command').stat().st_mode & 0o111)
            self.assertFalse(any(p.name in ('.env','private.log') for p in app.rglob('*')))
            info=plistlib.loads((app/'Contents/Info.plist').read_bytes())
            self.assertEqual(info['CFBundleIdentifier'],'io.github.diadawnfly.ntfsready')
            self.assertEqual(info['CFBundleExecutable'],'NTFSReady')
            self.assertEqual(info['LSMinimumSystemVersion'],'13.0')

if __name__=='__main__':
    unittest.main()
