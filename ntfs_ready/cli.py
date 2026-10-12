"""Bilingual argparse front end; installation belongs to the shell installer."""
import argparse
import contextlib
import json
import sys
from . import __version__
from .core import Service, SafetyError, validate_identifier


def build_parser():
    parser = argparse.ArgumentParser(prog='python3 -m ntfs_ready',
                                     description='NTFS Ready / NTFS 安全挂载 (beta)')
    parser.add_argument('--version', action='version', version='NTFS Ready ' + __version__ + ' beta')
    commands = parser.add_subparsers(dest='command')
    for name in ('list', 'doctor'):
        commands.add_parser(name).add_argument('--json', action='store_true', help='Machine-readable / JSON 输出')
    for name in ('mount', 'unmount', 'verify'):
        sub = commands.add_parser(name)
        sub.add_argument('device', help='Exact live identifier / 当前设备标识: diskNsN')
        sub.add_argument('--yes', action='store_true', help='Confirm changes / 确认操作')
        if name in ('mount', 'unmount'):
            sub.add_argument('--dry-run', action='store_true', help='Read-only plan / 仅显示计划')
        if name == 'mount':
            sub.add_argument('--verify', action='store_true', help='Also perform temporary write+xattr+ditto test / 执行临时写入验证')
        if name == 'verify':
            sub.add_argument('--json', action='store_true')
    commands.add_parser('menu', help='Interactive selection / 交互菜单')
    return parser


def emit(value, out, json_mode=False):
    if json_mode:
        print(json.dumps(value, ensure_ascii=False), file=out)
    else:
        print('Result / 结果:', file=out)
        print(json.dumps(value, ensure_ascii=False, indent=2), file=out)


def menu(app, ask, out, err):
    while True:
        choice = ask('list doctor mount verify unmount quit / 选择操作: ').strip().lower()
        if choice in ('quit', 'q', 'exit'):
            return 0
        try:
            if choice in ('list', 'doctor'):
                emit(app.list_devices() if choice == 'list' else app.doctor(), out)
                continue
            if choice not in ('mount', 'verify', 'unmount'):
                print('Unknown selection / 选择无效', file=err)
                continue
            rows = [row for row in app.list_devices() if row['eligible']]
            for index, row in enumerate(rows, 1):
                print('{}: {} {} ({} bytes)'.format(index, row['device'], row['name'], row['size']), file=out)
            if not rows:
                print('No eligible external NTFS volumes / 没有可操作外置 NTFS 卷', file=out)
                continue
            number = ask('Volume number / 卷编号: ')
            if not number.isascii() or not number.isdigit() or not 1 <= int(number) <= len(rows):
                raise SafetyError('Invalid selection / 卷编号无效')
            selected = rows[int(number) - 1]
            target = app.inspect(selected['device'])
            if target.identity != (selected['device'], selected['size'], selected['uuid'], selected['name']):
                raise SafetyError('Selection became stale / 选择已失效')
            if ask('Confirm {} {}? type yes / 输入 yes 确认: '.format(choice, target.device)).strip().lower() != 'yes':
                print('Cancelled / 已取消', file=out)
                continue
            app.recheck(target)
            if choice == 'mount':
                # Temporary writes need a separate explicit answer in the menu.
                verify = ask('Temporary write + metadata verification? yes/no / 临时写入验证? ').strip().lower() == 'yes'
                app.recheck(target)
                result = app.mount(target.device, yes=True, verify=verify, expected=target)
            elif choice == 'verify':
                result = app.verify(target.device, yes=True, expected=target)
            else:
                result = app.unmount(target.device, yes=True, expected=target)
            emit(result, out)
        except (SafetyError, OSError, ValueError) as exc:
            print('Error / 错误: ' + str(exc), file=err)


def main(argv=None, *, service=None, input_fn=None, out=None, err=None):
    out = sys.stdout if out is None else out
    err = sys.stderr if err is None else err
    parser = build_parser()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            args = parser.parse_args(argv)
        except SystemExit as exc:
            return int(exc.code)
    if args.command is None:
        parser.print_help(file=out)
        return 0
    app = Service() if service is None else service
    json_mode = getattr(args, 'json', False)
    def ask(prompt):
        if input_fn is not None:
            return input_fn(prompt)
        if not sys.stdin.isatty():
            raise SafetyError('Interactive confirmation required; use --yes explicitly / 需要交互确认')
        print(prompt, end='', file=err, flush=True)
        return input()
    try:
        app.guard()
        if args.command == 'menu':
            return menu(app, ask, out, err)
        if args.command == 'list':
            result = app.list_devices()
        elif args.command == 'doctor':
            result = app.doctor()
        else:
            validate_identifier(args.device)
            dry_run = getattr(args, 'dry_run', False)
            expected = app.inspect(args.device)
            if not args.yes and not dry_run:
                warning = 'Temporary writes + metadata test' if args.command == 'verify' else args.command
                if ask('Confirm {} {}? type yes / 输入 yes 确认: '.format(warning, args.device)).strip().lower() != 'yes':
                    raise SafetyError('Cancelled / 已取消')
            if args.command == 'mount':
                result = app.mount(args.device, yes=True, dry_run=dry_run, verify=args.verify, expected=expected)
            elif args.command == 'unmount':
                result = app.unmount(args.device, yes=True, dry_run=dry_run, expected=expected)
            else:
                result = app.verify(args.device, yes=True, expected=expected)
        emit(result, out, json_mode)
        return 0
    except (SafetyError, OSError, ValueError, EOFError) as exc:
        if json_mode:
            emit({'error': str(exc)}, out, True)
        else:
            print('Error / 错误: ' + str(exc), file=err)
        return 1
    except KeyboardInterrupt:
        print('Interrupted / 已中断', file=err)
        return 130
