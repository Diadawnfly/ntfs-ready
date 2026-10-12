"""Simulated OS fixtures; no empirical NTFS/Finder claims."""
import unittest
from ntfs_ready import core


def info(**changes):
    value = dict(DeviceIdentifier='disk12s1', Internal=False,
                 FileSystemPersonality='NTFS', ReadOnlyMedia=False,
                 TotalSize=123456, DiskUUID='SIMULATED-UUID',
                 VolumeName='测试 SSD', Mounted=False)
    value.update(changes)
    return value


# Fields observed on the parent's disposable macOS 27 MBR NTFS image.
# Deliberately no ReadOnly*, Mounted, DiskUUID, or VolumeUUID aliases.
def macos27_info(**changes):
    value = dict(DeviceIdentifier='disk5s1', Internal=False,
                 FilesystemType='ntfs', TotalSize=67108864,
                 VolumeName='NTFS Ready Test', ParentWholeDisk='disk5',
                 WritableMedia=True, WritableVolume=False, MountPoint='')
    value.update(changes)
    return value


class DeviceTests(unittest.TestCase):
    def test_physical_size_aliases_require_matching_positive_exact_integers(self):
        for key in ('IOKitSize', 'Size'):
            for invalid in (0, -1, True, False, '66060288', 66060288.0, None):
                for companion in ({}, {('Size' if key == 'IOKitSize' else 'IOKitSize'): 66060288}):
                    with self.subTest(key=key, invalid=invalid, companion=companion):
                        with self.assertRaises(core.SafetyError):
                            core.Device.from_info('disk12s1', info(**dict(companion, **{key: invalid})))
        with self.assertRaises(core.SafetyError):
            core.Device.from_info('disk12s1', info(IOKitSize=66060288, Size=66056192))
        for sizes in ({'IOKitSize': 66060288}, {'Size': 66060288},
                      {'IOKitSize': 66060288, 'Size': 66060288}):
            data = info(**sizes)
            data.pop('TotalSize')
            with self.subTest(sizes=sizes):
                self.assertEqual(core.Device.from_info('disk12s1', data).size, 66060288)

    def test_legacy_total_size_fallback_remains_conservative(self):
        target = core.Device.from_info('disk12s1', info())
        changed = core.Device.from_info('disk12s1', info(TotalSize=123457))
        self.assertNotEqual(changed.identity, target.identity)
        for invalid in (0, -1, True, False, '123456', 123456.0, None):
            with self.subTest(invalid=invalid), self.assertRaises(core.SafetyError):
                core.Device.from_info('disk12s1', info(TotalSize=invalid))

    def test_macos27_writable_aliases_and_mountpoint_normalize(self):
        data = macos27_info(DiskUUID='FIXTURE-GUID')
        target = core.Device.from_info('disk5s1', data)
        self.assertFalse(target.mounted)
        self.assertTrue(target.readonly_volume)
        data.update(MountPoint='/Volumes/NTFS Ready Test', WritableVolume=True)
        target = core.Device.from_info('disk5s1', data)
        self.assertTrue(target.mounted)
        self.assertFalse(target.readonly_volume)
        self.assertEqual(target.live_mountpoint, data['MountPoint'])

    def test_mount_state_requires_explicit_validated_evidence(self):
        cases = ({'MountPoint': None}, {'MountPoint': False},
                 {'MountPoint': 'relative'}, {'MountPoint': '/Volumes/bad\n'},
                 {'Mounted': 'yes'}, {'Mounted': 1},
                 {'Mounted': False, 'MountPoint': '/Volumes/SSD'})
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(core.SafetyError):
                core.Device.from_info('disk5s1', macos27_info(DiskUUID='GUID', **changes))
        data = macos27_info(DiskUUID='GUID')
        data.pop('MountPoint')
        with self.assertRaises(core.SafetyError):
            core.Device.from_info('disk5s1', data)

    def test_boolean_aliases_reject_contradictions_and_nonbooleans(self):
        for readonly, writable in (('ReadOnlyMedia', 'WritableMedia'),
                                   ('ReadOnlyVolume', 'WritableVolume')):
            for changes in ({readonly: True, writable: True},
                            {readonly: False, writable: False},
                            {readonly: 0}, {writable: 1}, {readonly: None}):
                with self.subTest(changes=changes), self.assertRaises(core.SafetyError):
                    core.Device.from_info('disk5s1', macos27_info(DiskUUID='GUID', **changes))
        target = core.Device.from_info('disk5s1', macos27_info(
            DiskUUID='GUID', ReadOnlyMedia=False, ReadOnlyVolume=True))
        self.assertTrue(target.readonly_volume)

    def test_missing_volume_state_stays_unknown(self):
        data = macos27_info(DiskUUID='GUID', MountPoint='/Volumes/NTFS Ready Test')
        data.pop('WritableVolume')
        self.assertIsNone(core.Device.from_info('disk5s1', data).readonly_volume)

    def test_valid_external_ntfs_preserves_identity(self):
        target = core.Device.from_info('disk12s1', info())
        self.assertEqual(target.mountpoint, '/Volumes/测试 SSD')
        self.assertEqual(target.identity, ('disk12s1', 123456, 'SIMULATED-UUID', '测试 SSD'))

    def test_rejects_malicious_identifier_without_normalizing(self):
        for value in ('/dev/disk12s1', ' disk12s1', 'disk12s1\n', 'disk12', 'disk1s1;whoami', 'disk١s1'):
            with self.subTest(value=value), self.assertRaises(core.SafetyError):
                core.Device.from_info(value, info())

    def test_rejects_unsafe_names(self):
        for name in ('', '.', '..', '../escape', 'a/b', 'a,b', 'a\n', 'a\x00', 'a\x7f'):
            with self.subTest(name=name), self.assertRaises(core.SafetyError):
                core.Device.from_info('disk12s1', info(VolumeName=name))

    def test_rejects_unproven_or_unsafe_identity(self):
        for changes in ({'Internal': True}, {'Internal': None}, {'ReadOnlyMedia': True},
                        {'FileSystemPersonality': 'ExFAT'}, {'TotalSize': 0},
                        {'DiskUUID': ''}, {'DeviceIdentifier': 'disk13s1'}):
            with self.subTest(changes=changes), self.assertRaises(core.SafetyError):
                core.Device.from_info('disk12s1', info(**changes))

    def test_filesystem_type_ntfs_is_supported(self):
        self.assertEqual(core.Device.from_info('disk12s1', info(FileSystemPersonality='', FilesystemType='ntfs')).device, 'disk12s1')


class SimulatedRunner:
    """A stateful simulated macOS command boundary, never touches disks."""
    def __init__(self):
        self.calls = []
        self.data = info(Mounted=True, MountPoint='/Volumes/测试 SSD', ReadOnlyVolume=True)
        self.driver = 'ntfs'
        self.fail_probe = False
        self.fail_mount = False
        self.mount_no_state = False
        self.stale_on = None
        self.info_count = 0
        self.external = {'AllDisksAndPartitions': [{'DeviceIdentifier': 'disk12', 'Partitions': [{'DeviceIdentifier': 'disk12s1'}]}]}

    def __call__(self, argv, *, interactive=False, timeout=30):
        import plistlib
        import subprocess
        self.calls.append((list(argv), interactive))
        output, code = b'', 0
        if argv[:3] == ['/usr/sbin/diskutil', 'info', '-plist']:
            self.info_count += 1
            data = dict(self.data)
            if self.stale_on and self.info_count >= self.stale_on:
                data['DiskUUID'] = 'SIMULATED-REPLACEMENT'
            output = plistlib.dumps(data)
        elif argv[:3] == ['/usr/sbin/diskutil', 'list', '-plist']:
            output = plistlib.dumps(self.external)
        elif argv == ['/sbin/mount']:
            if self.data.get('Mounted'):
                opts = self.driver + (', read-only' if self.data.get('ReadOnlyVolume') else ', local')
                output = ('/dev/disk12s1 on /Volumes/测试 SSD (' + opts + ')\n').encode()
        elif argv[:2] == ['/usr/sbin/diskutil', 'unmount']:
            self.data.update(Mounted=False, MountPoint='')
        elif argv[:3] == ['/usr/sbin/diskutil', 'mount', 'readOnly']:
            self.driver = 'ntfs'
            self.data.update(Mounted=True, MountPoint='/Volumes/测试 SSD', ReadOnlyVolume=True)
        elif 'ntfs-3g.probe' in argv[1]:
            code = 14 if self.fail_probe else 0
        elif argv[0] == '/usr/bin/sudo' and argv[1].endswith('/ntfs-3g'):
            code = 1 if self.fail_mount else 0
            if not code and not self.mount_no_state:
                self.driver = 'macfuse'
                self.data.update(Mounted=True, MountPoint='/Volumes/测试 SSD', ReadOnlyVolume=False)
        elif argv[:2] == ['/usr/bin/kmutil', 'showloaded']:
            output = b'io.macfuse.filesystems.macfuse'
        return subprocess.CompletedProcess(argv, code, output, b'simulated error' if code else b'')


def service(runner, **kwargs):
    return core.Service(runner=runner, uid=501, gid=20, platform='darwin',
                        exists=lambda p: p.startswith('/opt/homebrew/bin/') or p == core.MACFUSE_HELPER,
                        lexists=lambda p: False, sleep=lambda n: None,
                        terminal_ready=lambda: True,
                        directory_token=lambda p: ('SIMULATED-DEV', 'SIMULATED-INODE'), **kwargs)


IOREG_COMMAND = ['/usr/sbin/ioreg', '-a', '-r', '-c', 'IOMedia']


class MBRRunner:
    """Read-only literal macOS field fixture; no command reaches the host."""
    def __init__(self):
        self.data = macos27_info()
        self.registry = [{'BSD Name': 'disk5', 'IORegistryEntryID': 100,
                          'IORegistryEntryChildren': [
                              {'BSD Name': 'disk5s1', 'IORegistryEntryID': 101}]}]
        self.calls = []
        self.registry_bytes = None

    def __call__(self, argv, **kwargs):
        import plistlib
        import subprocess
        self.calls.append(list(argv))
        if argv == [core.DISKUTIL, 'info', '-plist', 'disk5s1']:
            output = plistlib.dumps(self.data)
        elif argv == [core.DISKUTIL, 'list', '-plist', 'external']:
            output = plistlib.dumps({'AllDisksAndPartitions': [
                {'DeviceIdentifier': 'disk5', 'Partitions': [{'DeviceIdentifier': 'disk5s1'}]}]})
        elif argv == IOREG_COMMAND:
            output = self.registry_bytes if self.registry_bytes is not None else plistlib.dumps(self.registry)
        elif argv == ['/sbin/mount']:
            path = self.data['MountPoint']
            output = ('/dev/disk5s1 on ' + path + ' (macfuse, local)\n').encode() if path else b''
        else:
            raise AssertionError('Unexpected command: ' + repr(argv))
        return subprocess.CompletedProcess(argv, 0, output, b'')


class MBRIdentityTests(unittest.TestCase):
    def test_selected_identity_survives_native_mount_volume_size_change(self):
        runner = MBRRunner()
        runner.data.update(IOKitSize=66060288, Size=66060288, TotalSize=66060288)
        app = service(runner)
        selected = app.inspect('disk5s1')
        runner.data.update(MountPoint='/Volumes/NTFS Ready Test',
                           TotalSize=66056192, VolumeSize=66056192)
        mounted = app.recheck(selected)
        self.assertTrue(mounted.mounted)
        self.assertEqual(mounted.identity, selected.identity)
        self.assertEqual(mounted.size, 66060288)
        runner.data.update(MountPoint='', TotalSize=66060288)
        runner.data.pop('VolumeSize')
        self.assertEqual(app.recheck(selected).identity, selected.identity)
        runner.data.update(IOKitSize=66064384, Size=66064384)
        with self.assertRaisesRegex(core.SafetyError, 'Target changed'):
            app.recheck(selected)

    def test_uuidless_macos27_partition_uses_exact_live_incarnation(self):
        runner = MBRRunner()
        app = service(runner)
        target = app.inspect('disk5s1')
        self.assertEqual(target.uuid, 'ioreg:101')
        self.assertEqual(target.identity, ('disk5s1', 67108864, 'ioreg:101', 'NTFS Ready Test'))
        self.assertFalse(target.mounted)
        self.assertTrue(target.readonly_volume)
        self.assertIn(IOREG_COMMAND, runner.calls)
        self.assertTrue(app.list_devices()[0]['eligible'])


    def test_recheck_reads_registry_again_and_refuses_reinserted_disk_number(self):
        runner = MBRRunner()
        app = service(runner)
        selected = app.inspect('disk5s1')
        self.assertEqual(app.recheck(selected), selected)
        runner.registry[0]['IORegistryEntryChildren'][0]['IORegistryEntryID'] = 102
        with self.assertRaisesRegex(core.SafetyError, 'Target changed'):
            app.mount('disk5s1', yes=True, expected=selected)
        self.assertEqual(runner.calls.count(IOREG_COMMAND), 3)
        self.assertTrue(all(call in (IOREG_COMMAND, [core.DISKUTIL, 'info', '-plist', 'disk5s1'])
                            for call in runner.calls))

    def test_registry_disappearance_refuses_selected_target(self):
        runner = MBRRunner()
        app = service(runner)
        selected = app.inspect('disk5s1')
        runner.registry = []
        with self.assertRaises(core.SafetyError):
            app.recheck(selected)

    def test_registry_requires_unique_exact_bsd_name_and_positive_integer_id(self):
        invalid = [[], {}, [{'BSD Name': 'disk5s10', 'IORegistryEntryID': 101}],
                   [{'IORegistryEntryID': 101}], [{'BSD Name': 'disk5s1'}]]
        # Keep each tree separate; a matching child cannot hide a duplicate.
        invalid += [[{'BSD Name': 'disk5s1', 'IORegistryEntryID': value}]
                    for value in (0, -1, True, '101')]
        node = {'BSD Name': 'disk5s1', 'IORegistryEntryID': 101}
        invalid += [[dict(node), dict(node)],
                    [dict(node, IORegistryEntryChildren=[dict(node)])],
                    [dict(node, IORegistryEntryChildren={})], [17]]
        for registry in invalid:
            runner = MBRRunner()
            runner.registry = registry
            with self.subTest(registry=registry), self.assertRaises(core.SafetyError):
                service(runner).inspect('disk5s1')

    def test_invalid_or_failed_registry_output_is_not_an_identity(self):
        import subprocess
        runner = MBRRunner()
        runner.registry_bytes = b'not a plist'
        with self.assertRaises(core.SafetyError):
            service(runner).inspect('disk5s1')
        def failed(argv, **kwargs):
            if argv == IOREG_COMMAND:
                return subprocess.CompletedProcess(argv, 1, b'', b'fixture failure')
            return runner(argv, **kwargs)
        with self.assertRaises(core.SafetyError):
            service(failed).inspect('disk5s1')

    def test_private_attachment_field_from_diskutil_is_never_trusted(self):
        runner = MBRRunner()
        runner.data['NTFSReadyAttachmentID'] = 999
        self.assertEqual(service(runner).inspect('disk5s1').uuid, 'ioreg:101')
        runner.registry = []
        with self.assertRaises(core.SafetyError):
            service(runner).inspect('disk5s1')

    def test_guid_identity_does_not_query_registry(self):
        for changes in ({'DiskUUID': 'DISK-GUID'}, {'VolumeUUID': 'VOLUME-GUID'},
                        {'DiskUUID': '', 'VolumeUUID': 'VOLUME-GUID'},
                        {'DiskUUID': 'DISK-GUID', 'VolumeUUID': 'VOLUME-GUID'}):
            runner = MBRRunner()
            runner.data.update(changes)
            target = service(runner).inspect('disk5s1')
            with self.subTest(changes=changes):
                self.assertEqual(target.uuid, changes.get('DiskUUID') or changes['VolumeUUID'])
                self.assertNotIn(IOREG_COMMAND, runner.calls)

    def test_direct_device_info_requires_guid_or_trusted_positive_attachment(self):
        data = macos27_info()
        with self.assertRaises(core.SafetyError):
            core.Device.from_info('disk5s1', data)
        for invalid in (0, -1, True, '101', None):
            with self.subTest(invalid=invalid), self.assertRaises(core.SafetyError):
                core.Device.from_info('disk5s1', dict(data, NTFSReadyAttachmentID=invalid))
        self.assertEqual(core.Device.from_info('disk5s1', dict(data, NTFSReadyAttachmentID=101)).uuid,
                         'ioreg:101')
        for size in (0, -1, True, '67108864', None):
            with self.subTest(size=size), self.assertRaises(core.SafetyError):
                core.Device.from_info('disk5s1', dict(data, NTFSReadyAttachmentID=101, TotalSize=size))

    def test_incarnation_does_not_weaken_external_filesystem_or_media_gates(self):
        for changes in ({'Internal': True}, {'Internal': 0}, {'WritableMedia': False},
                        {'FilesystemType': 'exfat'}):
            runner = MBRRunner()
            runner.data.update(changes)
            with self.subTest(changes=changes), self.assertRaises(core.SafetyError):
                service(runner).inspect('disk5s1')
        runner = MBRRunner()
        runner.data.pop('WritableMedia')
        with self.assertRaises(core.SafetyError):
            service(runner).inspect('disk5s1')

    def test_macos27_macfuse_state_normalizes_writable_volume(self):
        runner = MBRRunner()
        app = service(runner)
        target = app.inspect('disk5s1')
        runner.data.update(MountPoint='/Volumes/NTFS Ready Test', WritableVolume=True)
        result = app.writable_state(target)
        self.assertTrue(result['writable'])
        self.assertEqual(result['mountpoint'], '/Volumes/NTFS Ready Test')
        runner.data.pop('WritableVolume')
        with self.assertRaises(core.SafetyError):
            app.writable_state(target)


class DiscoveryTests(unittest.TestCase):
    def test_list_uses_external_plist_and_fresh_partition_info(self):
        runner = SimulatedRunner()
        result = service(runner).list_devices()
        self.assertEqual(result[0]['device'], 'disk12s1')
        self.assertTrue(result[0]['eligible'])
        self.assertEqual(runner.calls[0][0], ['/usr/sbin/diskutil', 'list', '-plist', 'external'])

    def test_list_never_queries_malicious_identifier(self):
        runner = SimulatedRunner()
        runner.external['AllDisksAndPartitions'][0]['Partitions'].append({'DeviceIdentifier': 'disk12s1;id'})
        self.assertEqual(len(service(runner).list_devices()), 1)
        self.assertFalse(any('disk12s1;id' in call for call, _ in runner.calls))

    def test_mount_table_parser_matches_exact_source_and_escaped_spaces(self):
        entries = core.parse_mounts('/dev/disk12s1 on /Volumes/My\\040SSD (macfuse, local)\n/dev/disk12s10 on /Volumes/other (ntfs, read-only)\n')
        self.assertEqual(entries['disk12s1'].mountpoint, '/Volumes/My SSD')
        self.assertTrue(entries['disk12s10'].readonly)

    def test_doctor_is_read_only_and_reports_kernel(self):
        runner = SimulatedRunner()
        result = service(runner).doctor()
        self.assertTrue(result['dependencies_ready'])
        self.assertTrue(result['kernel_loaded'])
        self.assertFalse(any('sudo' in ' '.join(call) or core.MACFUSE_HELPER in call for call, _ in runner.calls))


class MountTests(unittest.TestCase):
    def test_native_unmount_precedes_probe_and_mount_is_verified(self):
        runner = SimulatedRunner()
        result = service(runner).mount('disk12s1', yes=True)
        calls = [a for a, _ in runner.calls]
        unmount = calls.index([core.DISKUTIL, 'unmount', 'disk12s1'])
        probe = calls.index(['/usr/bin/sudo', '/opt/homebrew/bin/ntfs-3g.probe', '--readwrite', '/dev/disk12s1'])
        self.assertLess(unmount, probe)
        command = next(a for a in calls if a[:2] == ['/usr/bin/sudo', '/opt/homebrew/bin/ntfs-3g'])
        self.assertEqual(command[-2], '-o')
        self.assertEqual(command[-1], 'norecover,local,noatime,windows_names,allow_other,auto_xattr,uid=501,gid=20,volname=测试 SSD')
        self.assertTrue(result['writable'])
        self.assertFalse(result['write_probe_performed'])
        self.assertIn([core.MACFUSE_HELPER, 'kernel-extension', 'load'], calls)

    def test_mount_refuses_without_confirmation(self):
        runner = SimulatedRunner()
        with self.assertRaises(core.SafetyError):
            service(runner).mount('disk12s1')
        self.assertEqual(runner.calls, [])

    def test_dry_run_has_no_mutating_commands(self):
        runner = SimulatedRunner()
        result = service(runner).mount('disk12s1', dry_run=True)
        self.assertTrue(result['dry_run'])
        self.assertFalse(any(a[0] == '/usr/bin/sudo' or 'unmount' in a or core.MACFUSE_HELPER in a for a, _ in runner.calls))

    def test_stale_target_rejected_before_unmount(self):
        runner = SimulatedRunner()
        runner.stale_on = 2
        with self.assertRaises(core.SafetyError):
            service(runner).mount('disk12s1', yes=True)
        self.assertFalse(any('unmount' in a for a, _ in runner.calls))

    def test_failures_after_unmount_restore_native_readonly(self):
        for kind in ('fail_probe', 'fail_mount', 'mount_no_state'):
            runner = SimulatedRunner()
            setattr(runner, kind, True)
            with self.subTest(kind=kind), self.assertRaises(core.SafetyError):
                service(runner).mount('disk12s1', yes=True)
            self.assertIn(([core.DISKUTIL, 'mount', 'readOnly', 'disk12s1'], False), runner.calls)
            self.assertTrue(runner.data['ReadOnlyVolume'])

    def test_replaced_target_after_unmount_is_never_restored_or_probed(self):
        runner = SimulatedRunner()
        runner.stale_on = 4
        with self.assertRaises(core.SafetyError):
            service(runner).mount('disk12s1', yes=True)
        self.assertTrue(any('unmount' in a for a, _ in runner.calls))
        self.assertFalse(any('readOnly' in a or '--readwrite' in a for a, _ in runner.calls))

    def test_existing_writable_macfuse_is_idempotent(self):
        runner = SimulatedRunner()
        runner.driver = 'macfuse'
        runner.data['ReadOnlyVolume'] = False
        self.assertTrue(service(runner).mount('disk12s1', yes=True)['already_mounted'])
        self.assertFalse(any('unmount' in a or a[0] == '/usr/bin/sudo' for a, _ in runner.calls))

    def test_existing_directory_is_refused_without_unmount(self):
        runner = SimulatedRunner()
        app = service(runner)
        app.lexists = lambda p: True
        # Native current mountpoint may exist; it must disappear after normal unmount.
        with self.assertRaises(core.SafetyError):
            app.mount('disk12s1', yes=True)
        self.assertFalse(any(a[:2] == ['/usr/bin/sudo', '/opt/homebrew/bin/ntfs-3g'] for a, _ in runner.calls))

    def test_other_driver_mount_is_refused(self):
        runner = SimulatedRunner()
        runner.driver = 'somevendor'
        with self.assertRaises(core.SafetyError):
            service(runner).mount('disk12s1', yes=True)
        self.assertFalse(any('unmount' in a for a, _ in runner.calls))

    def test_unmount_is_normal_and_reads_back_state(self):
        runner = SimulatedRunner()
        self.assertTrue(service(runner).unmount('disk12s1', yes=True)['unmounted'])
        self.assertIn(([core.DISKUTIL, 'unmount', 'disk12s1'], False), runner.calls)
        self.assertFalse(any('force' in a for a, _ in runner.calls))

    def test_root_and_nonmacos_are_refused_before_commands(self):
        for uid, platform in ((0, 'darwin'), (501, 'linux')):
            runner = SimulatedRunner()
            with self.subTest(uid=uid), self.assertRaises(core.SafetyError):
                core.Service(runner=runner, uid=uid, gid=20, platform=platform).mount('disk12s1', yes=True)
            self.assertEqual(runner.calls, [])


class VerifyTests(unittest.TestCase):
    def test_confirmation_and_driver_checked_before_prober(self):
        runner = SimulatedRunner()
        probes = []
        app = service(runner, prober=lambda *a: probes.append(a))
        with self.assertRaises(core.SafetyError):
            app.verify('disk12s1')
        with self.assertRaises(core.SafetyError):
            app.verify('disk12s1', yes=True)
        self.assertEqual(probes, [])

    def test_verify_uses_exact_validated_macfuse_mount(self):
        runner = SimulatedRunner()
        runner.driver = 'macfuse'
        runner.data['ReadOnlyVolume'] = False
        probes = []
        def prober(path, command, guard):
            guard()
            probes.append(path)
            return {'payload_sha256': 'SIMULATED', 'xattr_preserved': True}
        result = service(runner, prober=prober).verify('disk12s1', yes=True)
        self.assertEqual(probes, ['/Volumes/测试 SSD'])
        self.assertTrue(result['write_probe_performed'])

    def test_real_probe_io_on_local_temp_only_with_simulated_metadata(self):
        import tempfile
        import pathlib
        import subprocess
        import shutil
        import os
        attributes = {}
        def key(path):
            st = os.stat(path)
            return (st.st_dev, st.st_ino)
        def command(argv, **kwargs):
            path = argv[-1]
            if argv[0] == '/usr/bin/ditto':
                shutil.copyfile(argv[-2], path)
                attributes[key(path)] = dict(attributes[key(argv[-2])])
                return subprocess.CompletedProcess(argv, 0, b'', b'')
            if argv[1] == '-w':
                attributes.setdefault(key(path), {})[argv[2]] = argv[3]
                return subprocess.CompletedProcess(argv, 0, b'', b'')
            value = attributes.get(key(path), {}).get(argv[2])
            return subprocess.CompletedProcess(argv, 0 if value is not None else 1,
                                               (value or '').encode(), b'No such xattr' if value is None else b'')
        with tempfile.TemporaryDirectory(prefix='ntfs-ready-SIMULATED-') as directory:
            sentinel = pathlib.Path(directory, 'user-file')
            sentinel.write_text('untouched')
            result = core.probe_volume(directory, command, lambda: None)
            self.assertTrue(result['xattr_preserved'])
            self.assertEqual(result['finder_info'], 'absent (expected on new file)')
            self.assertEqual(len(result['payload_sha256']), 64)
            self.assertEqual(sorted(p.name for p in pathlib.Path(directory).iterdir()), ['user-file'])
            self.assertEqual(sentinel.read_text(), 'untouched')

    def test_errno102_is_not_misreported_as_missing_finderinfo(self):
        import tempfile
        import subprocess
        def command(argv, **kwargs):
            if argv[1:3] == ['-p', 'com.apple.FinderInfo']:
                return subprocess.CompletedProcess(argv, 1, b'', b'[Errno 102] Operation not supported')
            return subprocess.CompletedProcess(argv, 0, b'ntfs-ready-metadata', b'')
        with tempfile.TemporaryDirectory(prefix='ntfs-ready-SIMULATED-') as directory:
            with self.assertRaisesRegex(core.SafetyError, '102'):
                core.probe_volume(directory, command, lambda: None)
            import os
            self.assertEqual(os.listdir(directory), [])

    def test_mount_verify_requires_explicit_flag(self):
        runner = SimulatedRunner()
        probes = []
        app = service(runner, prober=lambda *args: probes.append(args) or {'simulated': True})
        result = app.mount('disk12s1', yes=True, verify=True)
        self.assertTrue(result['write_probe_performed'])
        self.assertEqual(len(probes), 1)


class AdditionalSafetyTests(unittest.TestCase):
    def test_missing_readonly_state_cannot_be_treated_as_writable(self):
        runner = SimulatedRunner()
        runner.driver = 'macfuse'
        runner.data.pop('ReadOnlyVolume')
        with self.assertRaises(core.SafetyError):
            service(runner).mount('disk12s1', yes=True)

    def test_parenthesis_in_volume_name_does_not_confuse_mount_parser(self):
        entry = core.parse_mounts('/dev/disk12s1 on /Volumes/SSD (work) (macfuse, local)\n')['disk12s1']
        self.assertEqual(entry.mountpoint, '/Volumes/SSD (work)')

    def test_postunmount_identity_rechecks_size_and_name_not_only_uuid(self):
        for field, new in (('TotalSize', 987), ('VolumeName', 'Replacement')):
            runner = SimulatedRunner()
            app = service(runner)
            selected = app.inspect('disk12s1')
            runner.data[field] = new
            with self.subTest(field=field), self.assertRaises(core.SafetyError):
                app.mount('disk12s1', yes=True, expected=selected)
            self.assertFalse(any('unmount' in a or a[0] == '/usr/bin/sudo' for a, _ in runner.calls))

    def test_failed_normal_unmount_never_uses_force(self):
        import subprocess
        runner = SimulatedRunner()
        def fail(argv, **kwargs):
            if argv[1:2] == ['unmount']:
                runner.calls.append((argv, False))
                return subprocess.CompletedProcess(argv, 1, b'', b'SIMULATED busy')
            return runner(argv, **kwargs)
        with self.assertRaises(core.SafetyError):
            service(fail).unmount('disk12s1', yes=True)
        self.assertFalse(any('force' in a for a, _ in runner.calls))

    def test_nonterminal_mount_refused_before_unmount_or_helper(self):
        runner = SimulatedRunner()
        app = service(runner)
        app.terminal_ready = lambda: False
        with self.assertRaises(core.SafetyError):
            app.mount('disk12s1', yes=True)
        self.assertFalse(any('unmount' in a or core.MACFUSE_HELPER in a for a, _ in runner.calls))

    def test_generated_mountpoint_is_rechecked_before_ntfs3g(self):
        runner = SimulatedRunner()
        app = service(runner)
        def unsafe(path):
            raise core.SafetyError('SIMULATED mountpoint replaced by symlink')
        app.directory_token = unsafe
        with self.assertRaises(core.SafetyError):
            app.mount('disk12s1', yes=True)
        self.assertFalse(any(a[:2] == ['/usr/bin/sudo', '/opt/homebrew/bin/ntfs-3g'] for a, _ in runner.calls))
        self.assertIn(([core.DISKUTIL, 'mount', 'readOnly', 'disk12s1'], False), runner.calls)

    def test_real_mount_directory_token_refuses_nonroot_and_symlink(self):
        import os
        import tempfile
        from unittest.mock import patch
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory(prefix='ntfs-ready-SIMULATED-') as directory:
            if os.getuid() != 0:
                with self.assertRaises(core.SafetyError):
                    core.mount_directory_token(directory)
            link = directory + '/link'
            os.symlink(directory, link)
            with self.assertRaises(core.SafetyError):
                core.mount_directory_token(link)
        with patch('ntfs_ready.core.os.lstat', return_value=SimpleNamespace(st_mode=0o40755, st_uid=0, st_dev=12, st_ino=34)):
            self.assertEqual(core.mount_directory_token('/SIMULATED'), (12, 34))

    def test_driver_changed_during_helper_load_is_not_unmounted(self):
        runner = SimulatedRunner()
        def changed(argv, **kwargs):
            result = runner(argv, **kwargs)
            if argv == [core.MACFUSE_HELPER, 'kernel-extension', 'load']:
                runner.driver = 'SIMULATED-other-driver'
            return result
        with self.assertRaises(core.SafetyError):
            service(changed).mount('disk12s1', yes=True)
        self.assertFalse(any('unmount' in a for a, _ in runner.calls))

    def test_command_runner_rejects_nonterminal_sudo(self):
        from unittest.mock import patch
        with patch('ntfs_ready.core.sys.stdin.isatty', return_value=False):
            with self.assertRaises(core.SafetyError):
                core.run_command(['/usr/bin/sudo', '/usr/bin/true'], interactive=True)


if __name__ == '__main__':
    unittest.main()
