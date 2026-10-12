"""Copy a fixed, own-source whitelist; never remove unknown or modified files."""
import hashlib
import json
from pathlib import Path
import shutil
import sys

MARKER = '.ntfs-ready-owned.json'
OWNER = 'NTFS Ready payload v1'
SCRIPTS = ('runtime.sh', 'install_payload.py', 'uninstall.sh')


def safe_path(path):
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError('Refusing symlink path: ' + str(part))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_owned(dest):
    marker = dest / MARKER
    safe_path(marker)
    if not marker.exists():
        return {}
    data = json.loads(marker.read_text())
    if data.get('owner') != OWNER or not isinstance(data.get('files'), dict):
        raise ValueError('Unrecognized ownership marker')
    for name in data['files']:
        path = Path(name)
        if path.is_absolute() or '..' in path.parts or name == MARKER:
            raise ValueError('Unsafe ownership entry')
        # Even a corrupted marker must never claim arbitrary user files.
        if not (name.startswith('ntfs_ready/') and path.suffix == '.py') and name not in (
                'Launcher.command', *(str(Path('scripts') / n) for n in SCRIPTS)):
            raise ValueError('Non-whitelisted ownership entry')
    return data['files']


def install(source, dest, check_only=False):
    safe_path(dest)
    package = source / 'ntfs_ready'
    if not (package / '__main__.py').is_file():
        raise ValueError('Source ntfs_ready package is missing; use a complete release')
    entries = {str(p.relative_to(source)): p for p in package.rglob('*.py')}
    entries.update({str(Path('scripts') / n): source / 'scripts' / n for n in SCRIPTS})
    entries['Launcher.command'] = source / 'scripts/Launcher.command'
    owned = load_owned(dest)
    for name, src in entries.items():
        safe_path(src)
        target = dest / name
        safe_path(target)
        if not src.is_file():
            raise ValueError('Missing source file: ' + str(src))
        if target.exists() and (name not in owned or not target.is_file() or digest(target) != owned[name]):
            raise ValueError('Preserving unknown/modified file: ' + str(target))
    if check_only:
        return
    dest.mkdir(parents=True, exist_ok=True)
    updated = dict(owned)
    for name, src in entries.items():
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, target)
        target.chmod(0o755 if target.suffix in ('.sh', '.command') else 0o644)
        updated[name] = digest(target)
    (dest / MARKER).write_text(json.dumps({'owner': OWNER, 'files': updated}, indent=2) + '\n')
    print('Installed NTFS Ready: ' + str(dest / 'Launcher.command'))


def uninstall(dest):
    safe_path(dest)
    owned = load_owned(dest)
    if not owned:
        raise ValueError('No recognized NTFS Ready ownership marker; nothing removed')
    preserved = {}
    for name, checksum in owned.items():
        target = dest / name
        safe_path(target)
        if target.is_file() and digest(target) == checksum:
            target.unlink()
        elif target.exists():
            preserved[name] = checksum
            print('Preserved modified file: ' + str(target))
    if preserved:
        (dest / MARKER).write_text(json.dumps({'owner': OWNER, 'files': preserved}, indent=2) + '\n')
    else:
        (dest / MARKER).unlink()
    directories = {dest / Path(n).parent for n in owned}
    directories.update(p for d in list(directories) for p in d.parents if p == dest or dest in p.parents)
    for directory in sorted(directories, key=lambda p: len(p.parts), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            pass
    print('Removed unchanged NTFS Ready files; dependencies and user files were preserved.')


if __name__ == '__main__':
    try:
        if sys.argv[1] in ('install', 'check'):
            install(Path(sys.argv[2]), Path(sys.argv[3]), check_only=sys.argv[1] == 'check')
        elif sys.argv[1] == 'uninstall':
            uninstall(Path(sys.argv[2]))
        else:
            raise ValueError('Unknown operation')
    except (OSError, ValueError, IndexError) as exc:
        print('NTFS Ready: ' + str(exc), file=sys.stderr)
        sys.exit(1)
