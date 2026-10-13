"""Read-only JSON snapshots and private, explicit Terminal action handoff."""
import argparse
import json
import os
import re
import shlex
import stat
import sys
import uuid
from dataclasses import asdict
from pathlib import Path
from . import __version__
from .core import DISKUTIL, Device, SafetyError, Service, validate_identifier, validate_name


ACTIONS = ('mount', 'unmount', 'verify')
REQUEST = 'request.json'
RESULT = 'result.json'
COMMAND = 'action.command'


def validate_identity(identifier, identity):
    validate_identifier(identifier)
    if (type(identity) is not list or len(identity) != 4 or identity[0] != identifier
            or type(identity[1]) is not int or identity[1] <= 0
            or not isinstance(identity[2], str) or not identity[2].strip()
            or any(ord(c) < 32 or ord(c) == 127 for c in identity[2])):
        raise SafetyError('Invalid selected identity')
    validate_name(identity[3])
    return tuple(identity)


def check_directory(fd, *, private=False, owned=False):
    value = os.fstat(fd)
    if not stat.S_ISDIR(value.st_mode):
        raise SafetyError('Not a real directory')
    if (private or owned) and value.st_uid != os.getuid():
        raise SafetyError('Directory owner mismatch')
    if private and stat.S_IMODE(value.st_mode) != 0o700:
        raise SafetyError('Private directory permissions required (0700)')
    if owned and value.st_mode & 0o022:
        raise SafetyError('Writable directory permissions refused')


def open_directory(path):
    """Walk without following symlinks, holding directory descriptors."""
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise SafetyError('Absolute non-traversing path required')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def private_file(fd, name, content, mode=0o600):
    handle = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode, dir_fd=fd)
    with os.fdopen(handle, 'wb') as stream:
        os.fchmod(stream.fileno(), mode)
        stream.write(content.encode('utf-8'))
        stream.flush()
        os.fsync(stream.fileno())


def trusted_path(path, *, executable=False):
    """Resolve the known Python/package path, never a request-supplied command."""
    resolved = Path(path).resolve(strict=True)
    for parent in [resolved] + list(resolved.parents):
        value = parent.lstat()
        if value.st_uid not in (0, os.getuid()) or value.st_mode & 0o022:
            raise SafetyError('Untrusted Python/package path: ' + str(parent))
    if executable and (not resolved.is_file() or not os.access(str(resolved), os.X_OK)):
        raise SafetyError('Python executable unavailable')
    return str(resolved)


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise SafetyError('Duplicate request key')
        value[key] = item
    return value


def validated_request(request, nonce):
    if (type(request) is not dict or set(request) != {'schema', 'version', 'nonce', 'action', 'identity', 'device'}
            or type(request['schema']) is not int or request['schema'] != 1
            or request['version'] != __version__ or request['nonce'] != nonce
            or request['action'] not in ACTIONS):
        raise SafetyError('Invalid action request/schema/version/nonce')
    fields = request['device']
    if type(fields) is not dict or set(fields) != set(Device.__dataclass_fields__):
        raise SafetyError('Invalid Device snapshot fields')
    identity = validate_identity(fields['device'], request['identity'])
    if (type(fields['size']) is not int or fields['size'] <= 0
            or (fields['device'], fields['size'], fields['uuid'], fields['name']) != identity
            or type(fields['mounted']) is not bool
            or (fields['readonly_volume'] is not None and type(fields['readonly_volume']) is not bool)):
        raise SafetyError('Invalid Device snapshot types/identity')
    point = fields['live_mountpoint']
    if (not isinstance(point, str) or (point and not point.startswith('/'))
            or any(ord(c) < 32 or ord(c) == 127 for c in point)
            or fields['mounted'] != bool(point)):
        raise SafetyError('Invalid Device mountpoint snapshot')
    return Device(**fields), request['action']


class Bridge:
    def __init__(self, service=None, *, home=None, terminal_ready=None, uid=None):
        self.service = service if service is not None else Service()
        self.terminal_ready = terminal_ready if terminal_ready is not None else lambda: sys.stdin.isatty()
        self.uid = uid if uid is not None else os.getuid
        # Injection is API-only for simulated tests, not an environment/CLI bypass.
        self.home = Path(home) if home is not None else Path.home()
        self.actions = self.home / 'Library' / 'Caches' / 'NTFS Ready Desktop' / 'actions'

    def _actions_directory(self, create=False):
        fd = open_directory(self.home)
        try:
            check_directory(fd, owned=True)
            for part, private in (('Library', False), ('Caches', False), ('NTFS Ready Desktop', True), ('actions', True)):
                if create:
                    try:
                        os.mkdir(part, 0o700, dir_fd=fd)
                    except FileExistsError:
                        pass
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = child
                check_directory(fd, private=private, owned=True)
            return fd
        except BaseException:
            os.close(fd)
            raise

    def prepare_action(self, action, identifier, identity):
        if action not in ACTIONS:
            raise SafetyError('Unsupported action')
        selected = validate_identity(identifier, identity)
        self.service.guard()
        target = self.service.inspect(identifier)
        if target.identity != selected:
            raise SafetyError('Target changed; refresh and select again')
        python = trusted_path(sys.executable, executable=True)
        package = trusted_path(Path(__file__).parent.parent)
        nonce = uuid.uuid4().hex
        root_fd = self._actions_directory(create=True)
        try:
            os.mkdir(nonce, 0o700, dir_fd=root_fd)
            fd = os.open(nonce, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
            try:
                check_directory(fd, private=True)
                request_path = str(self.actions / nonce / REQUEST)
                request = dict(schema=1, version=__version__, nonce=nonce, action=action,
                               identity=list(selected), device=asdict(target))
                private_file(fd, REQUEST, json.dumps(request, ensure_ascii=False))
                command = ('#!/bin/bash\nset -eu\n'
                           'unset PYTHONHOME PYTHONSTARTUP PYTHONINSPECT PYTHONUSERBASE\n'
                           'export PYTHONNOUSERSITE=1\nexport PYTHONPATH=' + shlex.quote(package) + '\n'
                           'cd -- ' + shlex.quote(package) + '\n'
                           'exec ' + shlex.quote(python) + ' -B -s -m ntfs_ready.gui_bridge run-action --request '
                           + shlex.quote(request_path) + '\n')
                private_file(fd, COMMAND, command, mode=0o700)
            finally:
                os.close(fd)
        finally:
            os.close(root_fd)
        return dict(schema=1, nonce=nonce, command_path=str(self.actions / nonce / COMMAND),
                    result_path=str(self.actions / nonce / RESULT))

    def _request_directory(self, request_path):
        path = Path(request_path)
        nonce = path.parent.name
        if (not isinstance(request_path, str) or request_path != str(path)
                or not path.is_absolute() or '..' in path.parts or path.name != REQUEST
                or path.parent.parent != self.actions or re.fullmatch('[0-9a-f]{32}', nonce) is None):
            raise SafetyError('Request must be in the private action cache at its exact filename')
        root_fd = self._actions_directory()
        try:
            fd = os.open(nonce, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
            try:
                check_directory(fd, private=True)
            except BaseException:
                os.close(fd)
                raise
            return fd, nonce
        finally:
            os.close(root_fd)

    def run_action(self, request_path):
        """A Terminal-only operation. Refuse unsafe jobs before trusting output paths.

        Directory-relative, no-follow descriptors protect the request and result
        from symlink replacement. Exclusive claim and result publication prevent
        replay and overwriting an existing result. No arbitrary output path is read
        from the request. This cache is not a boundary against the same user who
        owns the Python application and can already invoke its CLI directly.
        """
        fd, nonce = self._request_directory(request_path)
        try:
            request_fd = os.open(REQUEST, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            with os.fdopen(request_fd, 'rb') as stream:
                value = os.fstat(stream.fileno())
                if (not stat.S_ISREG(value.st_mode) or value.st_uid != os.getuid()
                        or stat.S_IMODE(value.st_mode) != 0o600 or value.st_nlink != 1):
                    raise SafetyError('Request ownership/type/private permissions invalid')
                # Ownership is now known; malformed content gets a failure result.
                raw = stream.read(65537)
            try:
                os.stat(RESULT, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise SafetyError('Result already exists; action will not be repeated')
            private_file(fd, 'running', nonce)
            # Reserve a writable private staging file BEFORE any operation.
            staging_fd = os.open('result.pending', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=fd)
            with os.fdopen(staging_fd, 'wb') as output:
                os.fchmod(output.fileno(), 0o600)
                payload = dict(schema=1, nonce=nonce, ok=False, action=None, device=None,
                               message='', result={}, error=None)
                try:
                    if len(raw) > 65536:
                        raise SafetyError('Request too large')
                    request = json.loads(raw.decode('utf-8'), object_pairs_hook=unique_object)
                    target, action = validated_request(request, nonce)
                    payload.update(action=action, device=target.device)
                    if self.uid() == 0:
                        raise SafetyError('Run as your user, not root')
                    if not self.terminal_ready():
                        raise SafetyError('Interactive Terminal required before disk actions')
                    self.service.guard()
                    self.service.recheck(target)
                    method = getattr(self.service, action)
                    options = dict(yes=True, expected=target)
                    if action == 'mount':
                        options.update(dry_run=False, verify=False)
                    elif action == 'unmount':
                        options.update(dry_run=False)
                    result = method(target.device, **options)
                    if type(result) is not dict:
                        raise SafetyError('Service result is not an object')
                    # Confirm serializability before publishing a successful result.
                    json.dumps(result, allow_nan=False)
                    payload.update(ok=True, result=result, message=action + ' completed')
                except (Exception, KeyboardInterrupt) as exc:
                    payload.update(error=str(exc) or type(exc).__name__, message='Action refused or failed')
                output.write(json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8'))
                output.flush()
                os.fsync(output.fileno())
            # link publishes a fully written result atomically, without overwrite.
            os.link('result.pending', RESULT, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
            os.unlink('result.pending', dir_fd=fd)
            os.fsync(fd)
            return payload
        finally:
            os.close(fd)

    def snapshot(self):
        service = self.service
        service.guard()
        report = dict(schema=1, version=__version__, devices=[], unsupported=[],
                      doctor=service.doctor(), warnings=[])
        for row in service.list_devices():
            identifier = row['device']
            if row.get('eligible') is not True:
                report['unsupported'].append(dict(device=identifier, reason=row.get('reason', 'Not eligible')))
                continue
            try:
                target = service.inspect(identifier)
                fresh, entry, _ = service.state(target)
                driver = entry.driver if entry else None
                readonly = fresh.readonly_volume
                status = 'unknown'
                if not fresh.mounted and entry is None:
                    status = 'unmounted'
                elif entry and entry.source == '/dev/' + identifier and entry.mountpoint == fresh.live_mountpoint:
                    if driver == 'ntfs' and entry.readonly and readonly is True:
                        status = 'readOnly'
                    elif (driver == 'macfuse' and entry.mountpoint == fresh.mountpoint
                          and not entry.readonly and readonly is False):
                        status = 'writable'
                device = dict(device=identifier, name=fresh.name, size=fresh.size, uuid=fresh.uuid,
                              mounted=fresh.mounted, mountpoint=fresh.live_mountpoint,
                              readonly=readonly, driver=driver, status=status,
                              identity=list(fresh.identity), freeBytes=None, capacityBytes=None)
                try:
                    info = service.plist([DISKUTIL, 'info', '-plist', identifier])
                    service.recheck(fresh)
                    if info.get('DeviceIdentifier') != identifier:
                        raise ValueError('Metadata device mismatch')
                    capacity, free = info.get('VolumeSize'), info.get('FreeSpace')
                    if type(capacity) is int and 0 < capacity <= fresh.size:
                        device['capacityBytes'] = capacity
                        if type(free) is int and 0 <= free <= capacity:
                            device['freeBytes'] = free
                except Exception as exc:
                    report['warnings'].append(identifier + ': ' + str(exc))
                report['devices'].append(device)
            except Exception as exc:
                report['warnings'].append(identifier + ': ' + str(exc))
        return report


class JSONParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def main(argv=None, *, bridge=None):
    try:
        parser = JSONParser()
        commands = parser.add_subparsers(dest='command', required=True)
        commands.add_parser('snapshot')
        prepare = commands.add_parser('prepare-action')
        prepare.add_argument('--action', required=True, choices=ACTIONS)
        prepare.add_argument('--device', required=True)
        prepare.add_argument('--identity-json', required=True)
        run = commands.add_parser('run-action')
        run.add_argument('--request', required=True)
        args = parser.parse_args(argv)
        api = bridge if bridge is not None else Bridge()
        if args.command == 'snapshot':
            payload = api.snapshot()
        elif args.command == 'prepare-action':
            payload = api.prepare_action(args.action, args.device, json.loads(args.identity_json))
        else:
            payload = api.run_action(args.request)
        print(json.dumps(payload, ensure_ascii=False, allow_nan=False))
        return 1 if args.command == 'run-action' and not payload['ok'] else 0
    except Exception as exc:
        print(json.dumps(dict(schema=1, error=str(exc)), ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
