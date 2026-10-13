"""Bridge tests use simulated Service only; never operate on host disks."""
import io
import json
import os
import stat
import tempfile
from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout
from ntfs_ready import core, __version__
from ntfs_ready import gui_bridge


class SimulatedService:
    def __init__(self):
        self.target = core.Device('disk12s1', 123456, 'SIMULATED-UUID',
                                  'Simulated SSD', True, '/Volumes/Simulated SSD', True)
        self.entry = core.MountEntry('/dev/disk12s1', self.target.live_mountpoint, 'ntfs', ('ntfs', 'read-only'))
        self.metadata = dict(DeviceIdentifier='disk12s1', FreeSpace=0, VolumeSize=100000)
        self.calls = []
        self.failure = None
    def guard(self):
        pass
    def doctor(self):
        return {'simulated': True}
    def list_devices(self):
        return [dict(device='disk12s1', eligible=True), dict(device='disk13s1', eligible=False, reason='simulated unsupported')]
    def inspect(self, identifier):
        core.validate_identifier(identifier)
        if self.failure:
            raise core.SafetyError(self.failure)
        return self.target
    def recheck(self, target):
        fresh = self.inspect(target.device)
        if fresh.identity != target.identity:
            raise core.SafetyError('Target changed')
        return fresh
    def state(self, target):
        return self.recheck(target), self.entry, {}
    def mount(self, identifier, **kwargs):
        self.calls.append(('simulated mount', identifier, kwargs))
        self.recheck(kwargs['expected'])
        return {'simulated': True, 'write_probe_performed': False}
    def unmount(self, identifier, **kwargs):
        self.calls.append(('simulated unmount', identifier, kwargs))
        self.recheck(kwargs['expected'])
        return {'simulated': True}
    def verify(self, identifier, **kwargs):
        self.calls.append(('simulated verify', identifier, kwargs))
        self.recheck(kwargs['expected'])
        return {'simulated': True, 'write_probe_performed': True}
    def plist(self, argv):
        self.calls.append(argv)
        return dict(self.metadata)


class SnapshotTests(unittest.TestCase):
    def test_real_service_contract_enriched_without_writes(self):
        service = SimulatedService()
        result = gui_bridge.Bridge(service=service).snapshot()
        self.assertEqual(result['schema'], 1)
        self.assertEqual(result['version'], __version__)
        self.assertEqual(result['doctor'], {'simulated': True})
        self.assertEqual(result['unsupported'], [{'device': 'disk13s1', 'reason': 'simulated unsupported'}])
        self.assertEqual(result['warnings'], [])
        self.assertEqual(result['devices'], [dict(device='disk12s1', name='Simulated SSD', size=123456,
                         uuid='SIMULATED-UUID', mounted=True, mountpoint='/Volumes/Simulated SSD',
                         readonly=True, driver='ntfs', status='readOnly', identity=list(service.target.identity),
                         freeBytes=0, capacityBytes=100000)])
        self.assertEqual(service.calls, [[core.DISKUTIL, 'info', '-plist', 'disk12s1']])

    def test_writable_requires_expected_macfuse_mountpoint(self):
        service = SimulatedService()
        service.target = replace(service.target, readonly_volume=False, live_mountpoint='/Volumes/Other')
        service.entry = core.MountEntry('/dev/disk12s1', '/Volumes/Other', 'macfuse', ('macfuse', 'local'))
        row = gui_bridge.Bridge(service).snapshot()['devices'][0]
        self.assertEqual(row['status'], 'unknown')

    def test_confirmed_writable_unmounted_and_unknown_states(self):
        service = SimulatedService()
        service.target = replace(service.target, readonly_volume=False)
        service.entry = core.MountEntry('/dev/disk12s1', service.target.live_mountpoint, 'macfuse', ('macfuse', 'local'))
        self.assertEqual(gui_bridge.Bridge(service).snapshot()['devices'][0]['status'], 'writable')
        service.target = replace(service.target, readonly_volume=None)
        self.assertEqual(gui_bridge.Bridge(service).snapshot()['devices'][0]['status'], 'unknown')
        service.target = replace(service.target, mounted=False, live_mountpoint='')
        service.entry = None
        row = gui_bridge.Bridge(service).snapshot()['devices'][0]
        self.assertEqual(row['status'], 'unmounted')
        self.assertIsNone(row['driver'])
        self.assertIsNone(row['readonly'])

    def test_metadata_failure_does_not_hide_eligible_device(self):
        service = SimulatedService()
        service.plist = lambda argv: (_ for _ in ()).throw(core.SafetyError('simulated metadata failure'))
        report = gui_bridge.Bridge(service).snapshot()
        self.assertEqual(len(report['devices']), 1)
        self.assertIsNone(report['devices'][0]['freeBytes'])
        self.assertIn('simulated metadata failure', report['warnings'][0])

    def test_stats_unknown_and_exact_driver_status(self):
        for capacity, free in ((None, 0), (True, 0), (123457, 0), (100000, -1), (100000, True), (100000, 100001)):
            service = SimulatedService()
            service.metadata.update(VolumeSize=capacity, FreeSpace=free)
            service.entry = core.MountEntry('/dev/disk12s1', service.target.live_mountpoint, 'macfuse-impostor', ())
            row = gui_bridge.Bridge(service).snapshot()['devices'][0]
            self.assertIsNone(row['freeBytes'])
            self.assertEqual(row['status'], 'unknown')

    def test_per_device_failure_is_warning(self):
        service = SimulatedService()
        service.failure = 'simulated disconnect'
        result = gui_bridge.Bridge(service).snapshot()
        self.assertEqual(result['devices'], [])
        self.assertIn('simulated disconnect', result['warnings'][0])

    def test_global_failure_cli_is_single_json(self):
        service = SimulatedService()
        service.doctor = lambda: (_ for _ in ()).throw(core.SafetyError('simulated global failure'))
        output = io.StringIO()
        with redirect_stdout(output):
            code = gui_bridge.main(['snapshot'], bridge=gui_bridge.Bridge(service))
        self.assertNotEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())['error'], 'simulated global failure')


class TrustedPathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.executable = self.base / 'simulated-python'
        self.executable.write_text('SIMULATED PATH ONLY; NOT AN INTERPRETER\n')
        self.executable.chmod(0o700)

    def stats(self, node):
        from types import SimpleNamespace
        return SimpleNamespace(st_uid=os.getuid(), st_mode=0o755)

    def test_known_owned_nonwritable_ancestry_pins_canonical_executable(self):
        with patch.object(Path, 'lstat', autospec=True, side_effect=self.stats):
            self.assertEqual(gui_bridge.trusted_path(self.executable, executable=True), str(self.executable))

    def test_world_writable_executable_is_refused_without_policy_mock(self):
        self.executable.chmod(0o777)
        with self.assertRaises(core.SafetyError):
            gui_bridge.trusted_path(self.executable, executable=True)

    def test_group_writable_parent_is_refused(self):
        def stats(node):
            value = self.stats(node)
            if node == self.base:
                value.st_mode = 0o775
            return value
        with patch.object(Path, 'lstat', autospec=True, side_effect=stats):
            with self.assertRaises(core.SafetyError):
                gui_bridge.trusted_path(self.executable, executable=True)

    def test_foreign_owner_is_refused(self):
        def stats(node):
            value = self.stats(node)
            if node == self.executable:
                value.st_uid = os.getuid() + 10000
            return value
        with patch.object(Path, 'lstat', autospec=True, side_effect=stats):
            with self.assertRaises(core.SafetyError):
                gui_bridge.trusted_path(self.executable, executable=True)


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        # macOS temporary directories can have symlink ancestors; use canonical home.
        self.home = Path(self.temp.name).resolve()
        # Job protocol tests simulate OS boundaries. CI's interpreter/workspace
        # permissions are not shipping runtime prerequisites; policy is tested
        # independently in TrustedPathTests. Generated commands are never run.
        runtime_policy = patch('ntfs_ready.gui_bridge.trusted_path',
                               side_effect=lambda path, **kwargs: str(Path(path).resolve()))
        runtime_policy.start()
        self.addCleanup(runtime_policy.stop)
        self.service = SimulatedService()
        self.bridge = gui_bridge.Bridge(self.service, home=self.home)

    def prepare(self, action='mount'):
        return self.bridge.prepare_action(action, 'disk12s1', list(self.service.target.identity))

    def test_simulated_jobs_are_independent_of_host_runtime_permissions(self):
        # This is never executed: CI can install a group/world-writable Python.
        simulated_python = self.home / 'simulated-ci-python'
        simulated_python.write_text('SIMULATED PATH ONLY; NOT AN INTERPRETER\n')
        simulated_python.chmod(0o777)
        with patch.object(gui_bridge.sys, 'executable', str(simulated_python)):
            result = self.prepare()
        self.assertTrue(Path(result['command_path']).is_file())
        self.assertEqual(self.service.calls, [])

    def test_terminal_handoff_cannot_write_bytecode_into_signed_bundle(self):
        result = self.prepare()
        command = Path(result['command_path']).read_text()
        self.assertIn(' -B -s -m ntfs_ready.gui_bridge run-action ', command)

    def test_prepare_private_job_without_volume_mutations(self):
        result = self.prepare()
        self.assertEqual(set(result), {'schema', 'nonce', 'command_path', 'result_path'})
        self.assertRegex(result['nonce'], r'^[0-9a-f]{32}$')
        job = Path(result['command_path']).parent
        self.assertEqual(job.name, result['nonce'])
        self.assertEqual(job.parent, self.home / 'Library/Caches/NTFS Ready Desktop/actions')
        self.assertEqual(stat.S_IMODE(job.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(Path(result['command_path']).stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((job / 'request.json').stat().st_mode), 0o600)
        request = json.loads((job / 'request.json').read_text())
        self.assertEqual(request['nonce'], result['nonce'])
        self.assertEqual(request['identity'], list(self.service.target.identity))
        command = Path(result['command_path']).read_text()
        self.assertTrue(command.startswith('#!/bin/bash\n'))
        self.assertIn('ntfs_ready.gui_bridge run-action --request', command)
        self.assertFalse(Path(result['result_path']).exists())
        self.assertEqual(self.service.calls, [])

    def test_prepare_rejects_invalid_selection_before_cache_creation(self):
        for action, device, identity in (
                ('erase', 'disk12s1', list(self.service.target.identity)),
                ('mount', 'disk12s1;id', list(self.service.target.identity)),
                ('mount', 'disk12s1', ['disk12s1', True, 'SIMULATED-UUID', 'Simulated SSD']),
                ('mount', 'disk12s1', ['disk12s1', 1, 'SIMULATED-UUID', 'Simulated SSD'])):
            with self.subTest(action=action, device=device, identity=identity):
                with self.assertRaises((core.SafetyError, ValueError)):
                    self.bridge.prepare_action(action, device, identity)
        self.assertFalse((self.home / 'Library').exists())

    def test_prepare_rejects_symlink_or_public_cache(self):
        root = self.home / 'Library/Caches/NTFS Ready Desktop'
        root.parent.mkdir(parents=True)
        elsewhere = self.home / 'elsewhere'
        elsewhere.mkdir()
        root.symlink_to(elsewhere, target_is_directory=True)
        with self.assertRaises((core.SafetyError, OSError)):
            self.prepare()
        root.unlink()
        root.mkdir(mode=0o755)
        with self.assertRaises(core.SafetyError):
            self.prepare()


class RunTests(PrepareTests):
    def setUp(self):
        super().setUp()
        self.bridge = gui_bridge.Bridge(self.service, home=self.home, terminal_ready=lambda: True, uid=lambda: 501)

    def request_path(self, prepared):
        return str(Path(prepared['command_path']).parent / 'request.json')

    def test_simulated_actions_are_explicit_and_result_private(self):
        for action in ('mount', 'unmount', 'verify'):
            prepared = self.prepare(action)
            result = self.bridge.run_action(self.request_path(prepared))
            self.assertTrue(result['ok'])
            self.assertEqual(result['nonce'], prepared['nonce'])
            self.assertEqual(result['action'], action)
            self.assertEqual(result['device'], 'disk12s1')
            self.assertEqual(result['result']['simulated'], True)
            path = Path(prepared['result_path'])
            self.assertEqual(json.loads(path.read_text()), result)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            call = self.service.calls[-1]
            self.assertTrue(call[2]['yes'])
            self.assertEqual(call[2]['expected'], self.service.target)
            if action == 'mount':
                self.assertFalse(call[2]['verify'])
            if action == 'unmount':
                self.assertNotIn('force', call[2])
            with self.assertRaises((core.SafetyError, FileExistsError)):
                self.bridge.run_action(self.request_path(prepared))

    def test_tty_root_and_identity_refusals_write_failure_without_actions(self):
        for mode in ('notty', 'root', 'changed'):
            prepared = self.prepare()
            bridge = gui_bridge.Bridge(self.service, home=self.home,
                        terminal_ready=lambda: mode != 'notty', uid=lambda: 0 if mode == 'root' else 501)
            original = self.service.target
            if mode == 'changed':
                self.service.target = replace(original, uuid='SIMULATED-REPLACEMENT')
            result = bridge.run_action(self.request_path(prepared))
            self.assertFalse(result['ok'])
            self.assertIsInstance(result['error'], str)
            self.assertEqual(result['result'], {})
            self.assertEqual(json.loads(Path(prepared['result_path']).read_text()), result)
            self.assertEqual(self.service.calls, [])
            self.service.target = original

    def test_invalid_request_payload_writes_owned_failure(self):
        mutations = [lambda r: r.update(action='erase'), lambda r: r.update(nonce='0' * 32),
                     lambda r: r['identity'].__setitem__(1, True),
                     lambda r: r['device'].update(device='disk12s1;id'),
                     lambda r: r['device'].update(mounted='yes'),
                     lambda r: r['device'].update(readonly_volume=1),
                     lambda r: r.update(version='old'), lambda r: r.update(extra='bad')]
        for mutate in mutations:
            prepared = self.prepare()
            request = Path(self.request_path(prepared))
            data = json.loads(request.read_text())
            mutate(data)
            request.write_text(json.dumps(data))
            result = self.bridge.run_action(str(request))
            self.assertFalse(result['ok'])
            self.assertEqual(result['nonce'], prepared['nonce'])
            self.assertTrue(Path(prepared['result_path']).is_file())
            self.assertEqual(self.service.calls, [])

    def test_untrusted_files_and_result_collision_never_write_or_run(self):
        for mode in ('request-symlink', 'request-public', 'job-public', 'result-file', 'result-symlink', 'request-hardlink'):
            prepared = self.prepare()
            request = Path(self.request_path(prepared))
            result_path = Path(prepared['result_path'])
            outsider = self.home / ('outside-' + mode)
            outsider.write_text('untouched')
            if mode == 'request-symlink':
                request.unlink()
                request.symlink_to(outsider)
            elif mode == 'request-public':
                request.chmod(0o644)
            elif mode == 'job-public':
                request.parent.chmod(0o755)
            elif mode == 'result-file':
                result_path.write_text('untouched')
            elif mode == 'result-symlink':
                result_path.symlink_to(outsider)
            elif mode == 'request-hardlink':
                os.link(request, self.home / 'request-copy')
            with self.subTest(mode=mode), self.assertRaises((core.SafetyError, OSError)):
                self.bridge.run_action(str(request))
            self.assertEqual(outsider.read_text(), 'untouched')
            self.assertEqual(self.service.calls, [])
            if mode == 'result-file':
                self.assertEqual(result_path.read_text(), 'untouched')
            elif mode != 'result-symlink':
                self.assertFalse(result_path.exists())

    def test_real_service_with_simulated_os_boundary_never_probes_user_files(self):
        from test_core import SimulatedRunner, service
        runner = SimulatedRunner()
        app = service(runner, prober=lambda *a: (_ for _ in ()).throw(AssertionError('unexpected user-file probe')))
        bridge = gui_bridge.Bridge(app, home=self.home, terminal_ready=lambda: True, uid=lambda: 501)
        target = app.inspect('disk12s1')
        prepared = bridge.prepare_action('mount', target.device, list(target.identity))
        result = bridge.run_action(self.request_path(prepared))
        self.assertTrue(result['ok'])
        self.assertFalse(result['result']['write_probe_performed'])
        self.assertEqual(result['result']['driver'], 'macfuse')
        self.assertTrue(any(call[0][0] == '/usr/bin/sudo' for call in runner.calls))
        # Every command above was intercepted by SimulatedRunner.

    def test_run_rejects_symlink_parent(self):
        prepared = self.prepare()
        cache = self.home / 'Library/Caches/NTFS Ready Desktop'
        moved = cache.with_name('moved-private-cache')
        cache.rename(moved)
        cache.symlink_to(moved, target_is_directory=True)
        with self.assertRaises((core.SafetyError, OSError)):
            self.bridge.run_action(self.request_path(prepared))
        self.assertEqual(self.service.calls, [])
        self.assertFalse((moved / 'actions' / prepared['nonce'] / 'result.json').exists())

    def test_command_pins_import_directory(self):
        prepared = self.prepare()
        command = Path(prepared['command_path']).read_text()
        self.assertIn('cd -- ', command)
        self.assertLess(command.index('cd -- '), command.index('exec '))

    def test_foreign_owner_refused_before_trusting_result_path(self):
        prepared = self.prepare()
        actual = os.fstat
        def foreign(fd):
            value = actual(fd)
            if stat.S_ISREG(value.st_mode):
                fields = list(value)
                fields[4] = value.st_uid + 1
                return os.stat_result(fields)
            return value
        with patch.object(gui_bridge.os, 'fstat', side_effect=foreign):
            with self.assertRaisesRegex(core.SafetyError, 'ownership'):
                self.bridge.run_action(self.request_path(prepared))
        self.assertFalse(Path(prepared['result_path']).exists())
        self.assertEqual(self.service.calls, [])

    def test_malformed_json_and_duplicate_keys_write_failure(self):
        for raw in ('not json', '{"schema":1,"schema":1}', 'x' * 65537):
            prepared = self.prepare()
            Path(self.request_path(prepared)).write_text(raw)
            result = self.bridge.run_action(self.request_path(prepared))
            self.assertFalse(result['ok'])
            self.assertTrue(Path(prepared['result_path']).exists())
            self.assertEqual(self.service.calls, [])

    def test_result_staging_permission_failure_precedes_service_action(self):
        prepared = self.prepare()
        actual = os.open
        def deny(name, *args, **kwargs):
            if name == 'result.pending':
                raise PermissionError('simulated no write permission')
            return actual(name, *args, **kwargs)
        with patch.object(gui_bridge.os, 'open', side_effect=deny):
            with self.assertRaises(PermissionError):
                self.bridge.run_action(self.request_path(prepared))
        self.assertEqual(self.service.calls, [])
        self.assertFalse(Path(prepared['result_path']).exists())

    def test_service_failure_is_reported(self):
        prepared = self.prepare()
        self.service.mount = lambda *a, **kw: (_ for _ in ()).throw(core.SafetyError('simulated denied'))
        result = self.bridge.run_action(self.request_path(prepared))
        self.assertFalse(result['ok'])
        self.assertEqual(result['error'], 'simulated denied')
        self.assertEqual(json.loads(Path(prepared['result_path']).read_text()), result)

    def test_cli_prepare_and_run_failure_exit_codes(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = gui_bridge.main(['prepare-action', '--action', 'mount', '--device', 'disk12s1',
                    '--identity-json', json.dumps(list(self.service.target.identity))], bridge=self.bridge)
        self.assertEqual(code, 0)
        prepared = json.loads(output.getvalue())
        self.bridge.terminal_ready = lambda: False
        output = io.StringIO()
        with redirect_stdout(output):
            code = gui_bridge.main(['run-action', '--request', self.request_path(prepared)], bridge=self.bridge)
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(output.getvalue())['ok'])
        self.assertEqual(self.service.calls, [])

    def test_cli_rejects_unknown_options_as_json(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = gui_bridge.main(['prepare-action', '--cache-root', str(self.home)], bridge=self.bridge)
        self.assertEqual(code, 1)
        self.assertIsInstance(json.loads(output.getvalue())['error'], str)

    def test_wrong_location_or_filename_refused(self):
        prepared = self.prepare()
        path = Path(self.request_path(prepared))
        for bad in (str(path.parent / 'other.json'), str(self.home / 'request.json'), str(path.parent / '..' / path.parent.name / 'request.json')):
            with self.assertRaises((core.SafetyError, OSError)):
                self.bridge.run_action(bad)
        self.assertEqual(self.service.calls, [])


if __name__ == '__main__':
    unittest.main()
