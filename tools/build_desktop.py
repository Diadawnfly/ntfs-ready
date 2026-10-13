#!/usr/bin/env python3
"""Build a native macOS app with our source backend; never bundle vendor drivers."""
import argparse
import json
import os
import pathlib
import plistlib
import shutil
import subprocess
import sys
import tempfile

APP_ID='io.github.diadawnfly.ntfsready'
VERSION='0.2.0'
BACKEND=('__init__.py','__main__.py','core.py','cli.py','gui_bridge.py')
INSTALLER=('install.sh','dependencies.sh','runtime.sh','Launcher.command','uninstall.sh','install_payload.py')
MARKER='Contents/Resources/.ntfs-ready-desktop-build.json'

def safe_source(path):
    if not path.is_file() or path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise ValueError('Missing or unsafe source: '+str(path))

def copy_file(source,target):
    safe_source(source)
    if target.is_symlink() or any(p.is_symlink() for p in target.parents):
        raise ValueError('Unsafe resource destination')
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,target)
    target.chmod(0o755 if target.suffix in ('.command','.sh') else 0o644)

def stage_resources(source,app):
    source=pathlib.Path(source).resolve()
    app=pathlib.Path(app)
    if app.is_symlink() or any(p.is_symlink() for p in app.parents):
        raise ValueError('Unsafe output path')
    resources=app/'Contents/Resources'
    for name in BACKEND:
        copy_file(source/'ntfs_ready'/name,resources/'backend/ntfs_ready'/name)
        copy_file(source/'ntfs_ready'/name,resources/'installer/ntfs_ready'/name)
    for name in INSTALLER:
        copy_file(source/'scripts'/name,resources/'installer/scripts'/name)
    copy_file(source/'Install.command',resources/'installer/Install.command')
    for name in ('LICENSE','THIRD_PARTY_NOTICES.md'):
        copy_file(source/name,resources/name)
    info={
        'CFBundleIdentifier':APP_ID,'CFBundleExecutable':'NTFSReady',
        'CFBundleName':'NTFS Ready','CFBundleDisplayName':'NTFS Ready',
        'CFBundlePackageType':'APPL','CFBundleShortVersionString':VERSION,
        'CFBundleVersion':VERSION,'LSMinimumSystemVersion':'13.0',
        'NSHighResolutionCapable':True,
        'NSHumanReadableCopyright':'Copyright © 2026 Diadawnfly and contributors. MIT source; separate driver licenses.',
        'NSRemovableVolumesUsageDescription':'读取外置 NTFS 硬盘状态；写入或卸载仅在你明确确认后执行。',
        'NSAppleEventsUsageDescription':'仅在你请求授权操作时打开系统终端。应用不保存密码。',
    }
    (app/'Contents/Info.plist').write_bytes(plistlib.dumps(info))
    marker=app/MARKER
    marker.write_text(json.dumps({'owner':APP_ID,'version':VERSION})+'\n',encoding='utf-8')


def developer_environment():
    env=os.environ.copy()
    clt=pathlib.Path('/Library/Developer/CommandLineTools')
    if 'DEVELOPER_DIR' not in env and (clt/'usr/bin/swiftc').is_file():
        env['DEVELOPER_DIR']=str(clt)
    return env

def build(source,output,universal=False):
    if sys.platform!='darwin' or os.getuid()==0:
        raise ValueError('Build on macOS as your normal user; no sudo or license auto-acceptance.')
    source=pathlib.Path(source).resolve()
    output=pathlib.Path(output).absolute()
    if output.is_symlink() or any(p.is_symlink() for p in output.parents):
        raise ValueError('Unsafe output directory')
    output.mkdir(parents=True,exist_ok=True)
    final=output/'NTFS Ready.app'
    if final.exists():
        if final.is_symlink() or not (final/MARKER).is_file() or json.loads((final/MARKER).read_text()).get('owner')!=APP_ID:
            raise ValueError('Refusing to overwrite an unrecognized app bundle')
    sources=sorted((source/'native/NTFSReady').glob('*.swift'))
    if not sources:
        raise ValueError('Native Swift sources are missing')
    for path in sources:
        safe_source(path)
    env=developer_environment()
    sdk=subprocess.check_output(['/usr/bin/xcrun','--show-sdk-path'],env=env,text=True).strip()
    subprocess.run(['/usr/bin/xcrun','swiftc','--version'],env=env,check=True)
    archs=['arm64','x86_64'] if universal else [os.uname().machine]
    if any(a not in ('arm64','x86_64') for a in archs):
        raise ValueError('Unsupported build architecture')
    with tempfile.TemporaryDirectory(prefix='.ntfs-ready-build-',dir=str(output)) as temp:
        app=pathlib.Path(temp)/'NTFS Ready.app'
        stage_resources(source,app)
        executable=app/'Contents/MacOS/NTFSReady'
        executable.parent.mkdir(parents=True)
        binaries=[]
        for arch in archs:
            binary=pathlib.Path(temp)/('NTFSReady-'+arch)
            args=['/usr/bin/xcrun','swiftc','-parse-as-library','-swift-version','5','-O','-sdk',sdk,'-target',arch+'-apple-macosx13.0']
            subprocess.run(args+[str(p) for p in sources]+['-o',str(binary)],env=env,check=True)
            binaries.append(binary)
        if len(binaries)==1:
            shutil.copyfile(binaries[0],executable)
        else:
            subprocess.run(['/usr/bin/lipo','-create',*[str(b) for b in binaries],'-output',str(executable)],check=True)
        executable.chmod(0o755)
        subprocess.run(['/usr/bin/codesign','--force','--deep','--sign','-',str(app)],check=True)
        subprocess.run(['/usr/bin/codesign','--verify','--deep','--strict',str(app)],check=True)
        if final.exists():
            shutil.rmtree(final)
        os.replace(app,final)
    print(final)
    print('Local ad-hoc signature only; this app is not Developer-ID signed or notarized.')
    return final

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',default=str(pathlib.Path(__file__).resolve().parents[1]))
    parser.add_argument('--output',default='dist')
    parser.add_argument('--universal',action='store_true')
    args=parser.parse_args()
    try:
        build(args.source,args.output,args.universal)
    except (ValueError,OSError,subprocess.SubprocessError) as exc:
        parser.exit(1,str(exc)+'\n')

if __name__=='__main__':
    main()
