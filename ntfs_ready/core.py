"""Safety checks and injectable operating-system boundary (Python 3.9+)."""
import os
import plistlib
import re
import subprocess
import sys
import time
import unicodedata
from dataclasses import dataclass


class SafetyError(RuntimeError):
    """Refused an unproven or unsafe operation."""


def validate_identifier(identifier):
    if not isinstance(identifier, str) or re.fullmatch(r'disk[0-9]+s[0-9]+', identifier) is None:
        raise SafetyError('Invalid device / 设备标识无效: use diskNsN exactly')
    return identifier


def validate_name(name):
    if (not isinstance(name, str) or not name or not name.strip() or name in ('.', '..')
            or '/' in name or ',' in name
            or any(unicodedata.category(c).startswith('C') for c in name)):
        raise SafetyError('Unsafe volume name / 卷名不安全')
    return name


def readonly_flag(data, readonly, writable):
    """Accept explicit boolean aliases only; never guess from truthiness."""
    for key in (readonly, writable):
        if key in data and type(data[key]) is not bool:
            raise SafetyError('Invalid boolean state: ' + key)
    if readonly in data and writable in data and data[readonly] == data[writable]:
        raise SafetyError('Contradictory read-only/writable state')
    if readonly in data:
        return data[readonly]
    if writable in data:
        return not data[writable]
    return None


def stable_uuid(data):
    for key in ('DiskUUID', 'VolumeUUID'):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def attachment_id(registry, identifier):
    """Match a single live IOMedia incarnation, not a persistent disk GUID."""
    matches = []
    def visit(nodes):
        if not isinstance(nodes, list):
            raise SafetyError('Invalid IOMedia registry tree')
        for node in nodes:
            if not isinstance(node, dict):
                raise SafetyError('Invalid IOMedia registry node')
            if node.get('BSD Name') == identifier:
                matches.append(node.get('IORegistryEntryID'))
            if 'IORegistryEntryChildren' in node:
                visit(node['IORegistryEntryChildren'])
    visit(registry)
    if len(matches) != 1 or type(matches[0]) is not int or matches[0] <= 0:
        raise SafetyError('Missing or ambiguous live IOMedia identity')
    return matches[0]


@dataclass(frozen=True)
class Device:
    device: str
    size: int
    uuid: str
    name: str
    mounted: bool
    live_mountpoint: str
    readonly_volume: object

    @property
    def mountpoint(self):
        return '/Volumes/' + self.name

    @property
    def identity(self):
        return (self.device, self.size, self.uuid, self.name)

    @classmethod
    def from_info(cls, identifier, data):
        validate_identifier(identifier)
        if not isinstance(data, dict) or data.get('DeviceIdentifier') != identifier:
            raise SafetyError('Device identity mismatch / 设备身份不匹配')
        if data.get('Internal') is not False or readonly_flag(data, 'ReadOnlyMedia', 'WritableMedia') is not False:
            raise SafetyError('Only writable external media / 仅支持可写外置介质')
        if not (data.get('FileSystemPersonality') == 'NTFS' or data.get('FilesystemType') == 'ntfs'):
            raise SafetyError('Not a confirmed NTFS filesystem / 未确认 NTFS 文件系统')
        # Physical partition size stays stable when NTFS volume geometry changes
        # on mount. Legacy packets lacking both physical keys conservatively use
        # TotalSize; any change then still refuses the selected target.
        physical_sizes = [data[key] for key in ('IOKitSize', 'Size') if key in data]
        if any(type(value) is not int or value <= 0 for value in physical_sizes):
            raise SafetyError('Invalid physical size')
        if physical_sizes and any(value != physical_sizes[0] for value in physical_sizes):
            raise SafetyError('Contradictory physical size aliases')
        size = physical_sizes[0] if physical_sizes else data.get('TotalSize')
        uuid = stable_uuid(data)
        incarnation = data.get('NTFSReadyAttachmentID')
        if uuid is None and type(incarnation) is int and incarnation > 0:
            uuid = 'ioreg:' + str(incarnation)
        if type(size) is not int or size <= 0 or uuid is None:
            raise SafetyError('Missing stable size/UUID or live attachment / 缺少大小或稳定身份')
        name = validate_name(data.get('VolumeName'))
        mountpoint = data.get('MountPoint', '')
        if (not isinstance(mountpoint, str)
                or (mountpoint and not mountpoint.startswith('/'))
                or any(unicodedata.category(c).startswith('C') for c in mountpoint)):
            raise SafetyError('Invalid mountpoint state')
        if 'Mounted' in data:
            mounted = data['Mounted']
            if type(mounted) is not bool or ('MountPoint' in data and mounted != bool(mountpoint)):
                raise SafetyError('Invalid or contradictory mounted state')
        elif 'MountPoint' in data:
            mounted = bool(mountpoint)
        else:
            raise SafetyError('Missing mounted state')
        return cls(identifier, size, uuid, name, mounted, mountpoint,
                   readonly_flag(data, 'ReadOnlyVolume', 'WritableVolume'))


MACFUSE_HELPER = '/Library/Filesystems/macfuse.fs/Contents/Resources/macfuse.app/Contents/MacOS/macfuse'
DISKUTIL = '/usr/sbin/diskutil'


def run_command(argv, *, interactive=False, timeout=30):
    """Run argv without a shell; sudo inherits Terminal, never stdin secrets."""
    if interactive and not sys.stdin.isatty():
        raise SafetyError('Interactive Terminal required / 请在终端交互授权 sudo')
    try:
        return subprocess.run(list(argv), stdin=None if interactive else subprocess.DEVNULL,
                              stdout=None if interactive else subprocess.PIPE,
                              stderr=None if interactive else subprocess.PIPE,
                              timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SafetyError('Command failed / 命令失败: ' + str(exc)) from exc


@dataclass(frozen=True)
class MountEntry:
    source: str
    mountpoint: str
    driver: str
    options: tuple

    @property
    def readonly(self):
        return any(flag in self.options for flag in ('read-only', 'ro', 'rdonly'))


def parse_mounts(text):
    entries = {}
    for line in text.splitlines():
        match = re.fullmatch(r'(.+) on (.+) \(([^\n]+)\)', line)
        if not match:
            continue
        source, path, options = match.groups()
        path = re.sub(r'\\([0-7]{3})', lambda m: chr(int(m.group(1), 8)), path)
        flags = tuple(part.strip() for part in options.split(','))
        key = source[5:] if source.startswith('/dev/') else source
        if key in entries:
            raise SafetyError('Ambiguous mount source / 挂载源不明确')
        entries[key] = MountEntry(source, path, flags[0], flags)
    return entries


def mount_directory_token(path):
    """An empty mountpoint created by sudo must be a root-owned real directory."""
    import stat
    value = os.lstat(path)
    if not stat.S_ISDIR(value.st_mode) or value.st_uid != 0:
        raise SafetyError('Mountpoint is not a root-owned real directory / 挂载目录不安全')
    return (value.st_dev, value.st_ino)


class Service:
    """Inject runner and local boundaries for simulated OS tests."""
    def __init__(self, runner=run_command, *, uid=None, gid=None, platform=None,
                 exists=None, lexists=os.path.lexists, sleep=time.sleep, prober=None,
                 terminal_ready=None, directory_token=mount_directory_token):
        self.runner = runner
        self.uid = os.getuid() if uid is None else uid
        self.gid = os.getgid() if gid is None else gid
        self.platform = sys.platform if platform is None else platform
        self.exists = exists or (lambda p: os.path.isfile(p) and os.access(p, os.X_OK))
        self.lexists = lexists
        self.sleep = sleep
        self.prober = prober
        self.terminal_ready = terminal_ready or (lambda: sys.stdin.isatty())
        self.directory_token = directory_token

    def guard(self):
        if self.platform != 'darwin':
            raise SafetyError('macOS only / 仅支持 macOS')
        if self.uid == 0:
            raise SafetyError('Run as your user, not sudo/root / 请勿以 root 运行')

    def command(self, argv, *, interactive=False, timeout=30, check=True):
        result = self.runner(list(argv), interactive=interactive, timeout=timeout)
        if check and result.returncode:
            error = result.stderr or b''
            if isinstance(error, bytes):
                error = error.decode('utf-8', 'replace')
            raise SafetyError('Command failed ({}): {} {}'.format(result.returncode, argv[0], error))
        return result

    def plist(self, argv, *, expected_type=dict):
        output = self.command(argv).stdout
        if isinstance(output, str):
            output = output.encode()
        try:
            value = plistlib.loads(output)
        except (ValueError, TypeError, plistlib.InvalidFileException) as exc:
            raise SafetyError('Invalid command plist / 无效 plist 输出') from exc
        if not isinstance(value, expected_type):
            raise SafetyError('Unexpected plist structure / plist 数据无效')
        return value

    def inspect(self, identifier):
        self.guard()
        validate_identifier(identifier)
        data = self.plist([DISKUTIL, 'info', '-plist', identifier])
        # This private field is trusted only when freshly obtained from IOKit.
        data.pop('NTFSReadyAttachmentID', None)
        if stable_uuid(data) is None:
            registry = self.plist(['/usr/sbin/ioreg', '-a', '-r', '-c', 'IOMedia'], expected_type=list)
            data['NTFSReadyAttachmentID'] = attachment_id(registry, identifier)
        return Device.from_info(identifier, data)

    def recheck(self, target):
        fresh = self.inspect(target.device)
        if fresh.identity != target.identity:
            raise SafetyError('Target changed; stop / 目标已变化，请重新选择')
        return fresh

    def mounts(self):
        output = self.command(['/sbin/mount']).stdout
        return parse_mounts(output.decode('utf-8', 'strict') if isinstance(output, bytes) else output)

    def list_devices(self):
        self.guard()
        data = self.plist([DISKUTIL, 'list', '-plist', 'external'])
        identifiers = set()
        def visit(node):
            if isinstance(node, dict):
                candidate = node.get('DeviceIdentifier')
                if isinstance(candidate, str) and re.fullmatch(r'disk[0-9]+s[0-9]+', candidate):
                    identifiers.add(candidate)
                for value in node.values():
                    visit(value)
            elif isinstance(node, list):
                for value in node:
                    visit(value)
        visit(data.get('AllDisksAndPartitions', []))
        rows = []
        for identifier in sorted(identifiers):
            try:
                target = self.inspect(identifier)
                rows.append(dict(device=identifier, name=target.name, size=target.size,
                                 uuid=target.uuid, mounted=target.mounted,
                                 mountpoint=target.live_mountpoint, eligible=True))
            except SafetyError as exc:
                rows.append(dict(device=identifier, eligible=False, reason=str(exc)))
        return rows

    def dependencies(self):
        for prefix in ('/opt/homebrew/bin', '/usr/local/bin'):
            binary, probe = prefix + '/ntfs-3g', prefix + '/ntfs-3g.probe'
            if self.exists(binary) and self.exists(probe):
                return binary, probe
        raise SafetyError('Missing ntfs-3g + probe in trusted Homebrew paths / 缺少依赖')

    def doctor(self):
        self.guard()
        try:
            binary, probe = self.dependencies()
        except SafetyError:
            binary = probe = None
        helper = self.exists(MACFUSE_HELPER)
        kernel = self.command(['/usr/bin/kmutil', 'showloaded'], check=False)
        output = kernel.stdout or b''
        if isinstance(output, bytes):
            output = output.decode('utf-8', 'replace')
        return dict(platform=self.platform, uid=self.uid, gid=self.gid,
                    ntfs_3g=binary, probe=probe, macfuse_helper=helper,
                    dependencies_ready=bool(binary and helper),
                    kernel_loaded=(kernel.returncode == 0 and 'io.macfuse.filesystems.macfuse' in output),
                    kernel_check_error=kernel.returncode != 0,
                    mounts=[dict(device=k, mountpoint=v.mountpoint, driver=v.driver,
                                 readonly=v.readonly) for k, v in self.mounts().items()])

    def state(self, target):
        fresh = self.recheck(target)
        entries = self.mounts()
        entry = entries.get(target.device)
        if bool(entry) != fresh.mounted or (entry and fresh.live_mountpoint != entry.mountpoint):
            raise SafetyError('Mount state inconsistent / 挂载状态不一致')
        return fresh, entry, entries

    def writable_state(self, target):
        fresh, entry, _ = self.state(target)
        if (not entry or entry.source != '/dev/' + target.device
                or entry.mountpoint != target.mountpoint or entry.driver != 'macfuse'
                or entry.readonly or fresh.readonly_volume is not False):
            raise SafetyError('Expected writable macFUSE mount not ready / 可写挂载未就绪')
        return dict(device=target.device, mountpoint=entry.mountpoint, driver=entry.driver,
                    writable=True, write_probe_performed=False)

    def wait_state(self, target, *, writable):
        last = None
        for attempt in range(8):
            try:
                if writable:
                    return self.writable_state(target)
                fresh, entry, _ = self.state(target)
                if not fresh.mounted and not entry:
                    return dict(device=target.device, unmounted=True)
                last = SafetyError('Unmount not ready / 卸载未完成')
            except SafetyError as exc:
                last = exc
                # An identity change must never be retried against a reused disk number.
                self.recheck(target)
            if attempt < 7:
                self.sleep(0.25)
        raise last

    def clear_mountpoint(self, target, entries):
        if any(entry.mountpoint == target.mountpoint for entry in entries.values()):
            raise SafetyError('Mountpoint occupied / 挂载目录已被占用')
        if self.lexists(target.mountpoint):
            raise SafetyError('Existing directory/symlink refused / 拒绝已存在目录或符号链接')

    def restore_readonly(self, target, created, directory_identity=None):
        """Never restore a reused disk identifier or force an unsafe unmount."""
        fresh, entry, _ = self.state(target)
        if entry:
            if entry.driver == 'ntfs' and entry.readonly:
                return 'already native read-only'
            if entry.driver != 'macfuse' or entry.mountpoint != target.mountpoint:
                raise SafetyError('Unexpected mount during recovery; manual action required')
            self.recheck(target)
            self.command([DISKUTIL, 'unmount', target.device])
            self.wait_state(target, writable=False)
        if created and directory_identity is not None and self.lexists(target.mountpoint):
            self.recheck(target)
            if self.directory_token(target.mountpoint) != directory_identity:
                raise SafetyError('Recovery mountpoint identity changed; refusing directory cleanup')
            self.command(['/usr/bin/sudo', '/bin/rmdir', target.mountpoint], interactive=True)
        self.recheck(target)
        self.command([DISKUTIL, 'mount', 'readOnly', target.device])
        fresh, entry, _ = self.state(target)
        if not entry or entry.driver != 'ntfs' or not entry.readonly:
            raise SafetyError('Native read-only restore did not become ready')
        return 'native read-only restored'

    def select_target(self, identifier, expected=None):
        if expected is not None:
            if not isinstance(expected, Device) or expected.device != identifier:
                raise SafetyError('Expected target does not match requested device')
            return self.recheck(expected)
        return self.inspect(identifier)

    def mount(self, identifier, *, yes=False, dry_run=False, verify=False, expected=None):
        self.guard()
        if not yes and not dry_run:
            raise SafetyError('Confirmation required / 需要确认 (--yes)')
        target = self.select_target(identifier, expected)
        binary, probe = self.dependencies()
        if not self.exists(MACFUSE_HELPER):
            raise SafetyError('macFUSE helper missing / 缺少 macFUSE')
        fresh, entry, entries = self.state(target)
        options = 'norecover,local,noatime,windows_names,allow_other,auto_xattr,uid={},gid={},volname={}'.format(self.uid, self.gid, target.name)
        argv = ['/usr/bin/sudo', binary, '/dev/' + target.device, target.mountpoint, '-o', options]
        if entry and entry.driver == 'macfuse':
            result = self.writable_state(target)
            result['already_mounted'] = True
            if dry_run:
                result['dry_run'] = True
            elif verify:
                result['verification'] = self.verify(identifier, yes=True, expected=target)
                result['write_probe_performed'] = True
            return result
        if entry and (entry.driver != 'ntfs' or not entry.readonly or not fresh.readonly_volume):
            raise SafetyError('Only native read-only NTFS may be replaced / 仅替换原生只读 NTFS')
        if any(k != target.device and v.mountpoint == target.mountpoint for k, v in entries.items()):
            raise SafetyError('Another volume owns mountpoint / 目录属于其他卷')
        if not entry:
            self.clear_mountpoint(target, entries)
        if dry_run:
            return dict(device=identifier, dry_run=True, mountpoint=target.mountpoint,
                        argv=argv, would_unmount=bool(entry), write_probe_performed=False,
                        note='No commands executed; post-unmount probe required / 未执行挂载')
        if not self.terminal_ready():
            raise SafetyError('Interactive Terminal required before unmount / 卸载前需要交互终端')
        # Helper runs as the live user; never changes startup security policy.
        self.command([MACFUSE_HELPER, 'kernel-extension', 'load'], timeout=60)
        fresh, current, _ = self.state(target)
        if current != entry or fresh.readonly_volume != target.readonly_volume:
            raise SafetyError('Mount state changed before unmount / 卸载前挂载状态已变化')
        displaced, created = False, False
        directory_identity = None
        try:
            if entry:
                displaced = True
                self.command([DISKUTIL, 'unmount', target.device])
                self.wait_state(target, writable=False)
            else:
                displaced = True  # A failed attempt restores native read-only access too.
            fresh, current, entries = self.state(target)
            if current or fresh.mounted:
                raise SafetyError('Device still mounted / 设备仍已挂载')
            self.clear_mountpoint(target, entries)
            self.recheck(target)
            self.command(['/usr/bin/sudo', probe, '--readwrite', '/dev/' + target.device], interactive=True, timeout=60)
            fresh, current, entries = self.state(target)
            if current:
                raise SafetyError('Device remounted during probe / 检查期间设备重新挂载')
            self.clear_mountpoint(target, entries)
            self.recheck(target)
            self.command(['/usr/bin/sudo', '/bin/mkdir', target.mountpoint], interactive=True)
            created = True
            directory_identity = self.directory_token(target.mountpoint)
            fresh, current, entries = self.state(target)
            if current or any(v.mountpoint == target.mountpoint for v in entries.values()):
                raise SafetyError('Mountpoint became occupied / 挂载目录已被占用')
            if self.directory_token(target.mountpoint) != directory_identity:
                raise SafetyError('Mountpoint replaced before mount / 挂载目录已变化')
            self.command(argv, interactive=True, timeout=90)
            result = self.wait_state(target, writable=True)
            result['already_mounted'] = False
            if verify:
                result['verification'] = self.verify(identifier, yes=True, expected=target)
                result['write_probe_performed'] = True
            return result
        except (Exception, KeyboardInterrupt) as exc:
            recovery = 'not required'
            if displaced:
                try:
                    recovery = self.restore_readonly(target, created, directory_identity)
                except (Exception, KeyboardInterrupt) as recovery_exc:
                    recovery = 'FAILED (manual recovery needed): ' + str(recovery_exc)
            raise SafetyError('{}; recovery / 恢复: {}'.format(exc, recovery)) from exc

    def unmount(self, identifier, *, yes=False, dry_run=False, expected=None):
        self.guard()
        if not yes and not dry_run:
            raise SafetyError('Confirmation required / 需要确认')
        target = self.select_target(identifier, expected)
        fresh, entry, _ = self.state(target)
        if dry_run:
            return dict(device=identifier, dry_run=True, would_unmount=bool(entry))
        if not entry:
            return dict(device=identifier, unmounted=True, already_unmounted=True)
        self.recheck(target)
        self.command([DISKUTIL, 'unmount', identifier])
        return self.wait_state(target, writable=False)

    def verify(self, identifier, *, yes=False, expected=None):
        self.guard()
        if not yes:
            raise SafetyError('Temporary write test needs confirmation / 临时写入测试需要确认 (--yes)')
        target = self.select_target(identifier, expected)
        result = self.writable_state(target)
        prober = self.prober or probe_volume
        result.update(prober(target.mountpoint, self.command, lambda: self.writable_state(target)))
        self.writable_state(target)
        result['write_probe_performed'] = True
        result['finder_gui_tested'] = False
        return result


def probe_volume(mountpoint, command, guard):
    """Write ONLY a private random temporary probe directory; no recursive cleanup.

    `guard` revalidates device identity and the writable mount before each phase.
    This exercises I/O + xattrs + ditto, not an actual Finder GUI operation.
    """
    import hashlib
    import tempfile
    import stat
    guard()
    if os.path.islink(mountpoint) or not os.path.isdir(mountpoint):
        raise SafetyError('Probe mountpoint is not a real directory')
    root_stat = os.stat(mountpoint, follow_symlinks=False)
    directory = tempfile.mkdtemp(prefix='.ntfs-ready-probe-', dir=mountpoint)
    directory_stat = os.stat(directory, follow_symlinks=False)
    paths = {name: os.path.join(directory, name) for name in ('payload.bin', 'renamed.bin', 'copy.bin')}
    allowed = tuple(paths.values()) + tuple(os.path.join(directory, '._' + name) for name in paths)
    token = 'ntfs-ready-metadata'
    attribute = 'com.ntfs-ready.probe'
    payload = os.urandom(4096)
    digest = hashlib.sha256(payload).hexdigest()

    def checked():
        guard()
        current_root = os.stat(mountpoint, follow_symlinks=False)
        current_dir = os.stat(directory, follow_symlinks=False)
        if ((current_root.st_dev, current_root.st_ino) != (root_stat.st_dev, root_stat.st_ino)
                or (current_dir.st_dev, current_dir.st_ino) != (directory_stat.st_dev, directory_stat.st_ino)
                or not stat.S_ISDIR(current_dir.st_mode)):
            raise SafetyError('Probe directory/mount replaced; files left untouched at ' + directory)

    def output(result):
        value = result.stdout or b''
        return value.decode('utf-8', 'replace').strip() if isinstance(value, bytes) else value.strip()

    def xattr_read(path):
        checked()
        result = command(['/usr/bin/xattr', '-p', attribute, path])
        if output(result) != token:
            raise SafetyError('Extended attribute mismatch / 扩展属性不匹配')

    failure = None
    report = None
    try:
        checked()
        with open(paths['payload.bin'], 'xb') as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        checked()
        with open(paths['payload.bin'], 'rb') as handle:
            if hashlib.sha256(handle.read()).hexdigest() != digest:
                raise SafetyError('Payload hash mismatch')
        checked()
        command(['/usr/bin/xattr', '-w', attribute, token, paths['payload.bin']])
        xattr_read(paths['payload.bin'])
        checked()
        finder = command(['/usr/bin/xattr', '-p', 'com.apple.FinderInfo', paths['payload.bin']], check=False)
        finder_info = 'present'
        if finder.returncode:
            error = finder.stderr or b''
            if isinstance(error, bytes):
                error = error.decode('utf-8', 'replace')
            lower = error.lower()
            if '102' in error or 'not supported' in lower:
                raise SafetyError('xattr errno 102 / unsupported metadata; check auto_xattr: ' + error)
            if not ('no such xattr' in lower or 'attribute not found' in lower or 'errno 93' in lower):
                raise SafetyError('FinderInfo query failed: ' + error)
            finder_info = 'absent (expected on new file)'
        checked()
        os.rename(paths['payload.bin'], paths['renamed.bin'])
        xattr_read(paths['renamed.bin'])
        with tempfile.TemporaryDirectory(prefix='ntfs-ready-local-probe-') as local:
            source = os.path.join(local, 'source.bin')
            with open(source, 'xb') as handle:
                handle.write(payload)
            command(['/usr/bin/xattr', '-w', attribute, token, source])
            checked()
            command(['/usr/bin/ditto', '--rsrc', '--extattr', source, paths['copy.bin']], timeout=30)
            checked()
            with open(paths['copy.bin'], 'rb') as handle:
                if hashlib.sha256(handle.read()).hexdigest() != digest:
                    raise SafetyError('ditto payload hash mismatch')
            xattr_read(paths['copy.bin'])
        checked()
        with open(paths['renamed.bin'], 'rb') as handle:
            if hashlib.sha256(handle.read()).hexdigest() != digest:
                raise SafetyError('Rename payload hash mismatch')
        report = dict(payload_sha256=digest, write_read_rename_delete=True,
                      xattr_preserved=True, ditto_metadata_preserved=True,
                      finder_info=finder_info)
    except (Exception, KeyboardInterrupt) as exc:
        failure = exc
    try:
        checked()
        for path in allowed:
            if os.path.lexists(path):
                checked()
                # unlink handles a symlink itself, never follows it.
                os.unlink(path)
        checked()
        os.rmdir(directory)
    except (Exception, KeyboardInterrupt) as cleanup:
        raise SafetyError('Probe error: {}; cleanup incomplete, only generated directory remains at {}: {}'.format(failure, directory, cleanup)) from cleanup
    if failure:
        raise SafetyError('Temporary verification failed / 临时验证失败: ' + str(failure)) from failure
    return report
