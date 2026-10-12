#!/usr/bin/env python3
"""Build a source-only, double-click-installer release; never vendor drivers."""
import argparse
import hashlib
import pathlib
import re
import stat
import zipfile

ROOT_FILES = {'Install.command', 'README.md', 'README.zh-CN.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md', 'SECURITY.md', 'CONTRIBUTING.md', 'CHANGELOG.md', 'pyproject.toml', '.gitignore'}
SOURCE_DIRS = {'ntfs_ready': {'.py'}, 'scripts': {'.sh', '.command', '.py'}, 'tools': {'.py'}, 'tests': {'.py'}, 'docs': {'.md'}, '.github': {'.yml', '.yaml', '.md'}}
REQUIRED = [
    'Install.command', 'scripts/install.sh', 'scripts/dependencies.sh',
    'scripts/runtime.sh', 'scripts/Launcher.command', 'scripts/uninstall.sh',
    'scripts/install_payload.py', 'ntfs_ready/__init__.py',
    'ntfs_ready/__main__.py', 'ntfs_ready/cli.py', 'ntfs_ready/core.py',
    'README.md', 'LICENSE',
]

def build_release(source, output, version='0.1.0-beta'):
    source = pathlib.Path(source).resolve()
    output = pathlib.Path(output).resolve()
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[a-zA-Z0-9.-]+)?', version):
        raise ValueError('Invalid release version')
    for required in REQUIRED:
        if not (source / required).is_file():
            raise ValueError('Missing required release input: ' + required)
    candidates = [source / name for name in sorted(ROOT_FILES) if (source / name).is_file()]
    for dirname, suffixes in SOURCE_DIRS.items():
        folder = source / dirname
        if folder.exists():
            candidates.extend(p for p in folder.rglob('*') if p.is_file() and p.suffix in suffixes and '__pycache__' not in p.parts)
    for path in candidates:
        relative = path.relative_to(source)
        if path.is_symlink() or any((source.joinpath(*relative.parts[:i])).is_symlink() for i in range(1, len(relative.parts))):
            raise ValueError('Refusing a symbolic link in release inputs: ' + str(relative))
        path.resolve().relative_to(source)
    output.mkdir(parents=True, exist_ok=True)
    archive = output / ('NTFS-Ready-' + version + '.zip')
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for path in sorted(set(candidates)):
            relative = path.relative_to(source)
            info = zipfile.ZipInfo('NTFS-Ready/' + relative.as_posix())
            info.create_system = 3
            executable = path.suffix in {'.command', '.sh'}
            info.external_attr = (stat.S_IFREG | (0o755 if executable else 0o644)) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, path.read_bytes())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (output / 'SHA256SUMS.txt').write_text(digest + '  ' + archive.name + '\n', encoding='utf-8')
    return archive

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', default=str(pathlib.Path(__file__).resolve().parents[1]))
    parser.add_argument('--output', default='dist')
    parser.add_argument('--version', default='0.1.0-beta')
    args = parser.parse_args()
    try:
        print(build_release(args.source, args.output, args.version))
    except (ValueError, OSError) as exc:
        parser.exit(1, str(exc) + '\n')

if __name__ == '__main__':
    main()
