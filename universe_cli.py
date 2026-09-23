"""Safe terminal editor for config/universe.json."""
import argparse
import copy
import json
import os
import re
import tempfile
import subprocess
from pathlib import Path

from relay import UNIVERSE_PATH, validate_universe


def code(value):
    if not re.fullmatch(r'\d{6}', value):
        raise argparse.ArgumentTypeError('종목코드는 6자리 숫자여야 합니다')
    return value


def load():
    return json.loads(UNIVERSE_PATH.read_text(encoding='utf-8'))


def write(data, dry_run):
    validate_universe(data)
    if dry_run:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    UNIVERSE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=UNIVERSE_PATH.parent, prefix='.universe-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            json.dump(data, out, ensure_ascii=False, indent=2)
            out.write('\n')
        os.replace(temp, UNIVERSE_PATH)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def publish_universe(message=None):
    """Publish only the validated universe through an isolated origin/main worktree."""
    root = UNIVERSE_PATH.parent.parent
    tempdir = tempfile.mkdtemp(prefix='universe-publish-', dir=root / '.git')
    def git(*args, cwd=root):
        return subprocess.run(['git', *args], cwd=cwd, check=True, text=True,
                              capture_output=True)
    try:
        git('fetch', 'origin')
        git('worktree', 'add', '--detach', tempdir, 'origin/main')
        target = Path(tempdir) / 'config/universe.json'
        target.write_text(UNIVERSE_PATH.read_text(encoding='utf-8'), encoding='utf-8')
        git('add', 'config/universe.json', cwd=tempdir)
        staged = git('diff', '--cached', '--name-only', cwd=tempdir).stdout.splitlines()
        if staged != ['config/universe.json']:
            raise ValueError('unexpected staged files')
        result = git('commit', '-m', message or 'Update universe configuration', cwd=tempdir)
        git('push', 'origin', 'HEAD:main', cwd=tempdir)
        print('PUBLISH OK')
        return result.stdout.strip()
    except Exception as exc:
        print(f'PUBLISH FAILED\nReason: {exc}\nLocal universe change is preserved.')
        raise
    finally:
        try: git('worktree', 'remove', '--force', tempdir)
        except Exception: pass


def groups(data, kind):
    return data[{'sector': 'sectors', 'theme': 'themes', 'watchlist': 'watchlists'}[kind]]


def require_stock(data, item_code):
    if item_code not in {s['itemCode'] for s in data['stocks']}:
        raise ValueError(f'존재하지 않는 종목: {item_code}')


def add_to(data, kind, name, item_code, create=False):
    require_stock(data, item_code)
    collection = groups(data, kind)
    if name not in collection:
        if not create: raise ValueError(f'존재하지 않는 {kind}: {name} (--create-groups 사용)')
        collection[name] = []
    group = collection[name]
    if item_code not in group:
        group.append(item_code)


def run(args):
    data = load()
    cmd = args.command
    if cmd == 'show':
        print(json.dumps(data, ensure_ascii=False, indent=2)); return
    if cmd == 'validate':
        validate_universe(data); print('유효합니다'); return
    if cmd == 'add-stock':
        name = args.stock_name or args.name
        if not name: raise ValueError('stockName is required')
        require_new = {s['itemCode'] for s in data['stocks']}
        if args.item_code not in require_new:
            data['stocks'].append({'itemCode': args.item_code, 'stockName': name,
                                   'enabled': False if args.disabled else True})
        elif args.enabled is not None:
            next(stock for stock in data['stocks'] if stock['itemCode'] == args.item_code)['enabled'] = args.enabled
        for kind, names in (('sector', args.sector), ('theme', args.theme), ('watchlist', args.watchlist)):
            for group_name in names: add_to(data, kind, group_name, args.item_code, args.create_groups)
    elif cmd == 'apply':
        request = json.loads(args.payload); stock = request.get('stock', {})
        item_code = code(stock.get('itemCode', ''))
        name = stock.get('stockName')
        if not isinstance(name, str) or not name: raise ValueError('stock.stockName is required')
        existing = {s['itemCode'] for s in data['stocks']}
        if item_code not in existing: data['stocks'].append({'itemCode': item_code, 'stockName': name, 'enabled': bool(stock.get('enabled', True))})
        else:
            target = next(s for s in data['stocks'] if s['itemCode'] == item_code)
            if 'enabled' in stock: target['enabled'] = bool(stock['enabled'])
        for kind, key in (('sector','sectors'), ('theme','themes'), ('watchlist','watchlists')):
            for group_name in request.get(key, []): add_to(data, kind, group_name, item_code, bool(request.get('createGroups')))
    elif cmd == 'remove-stock':
        require_stock(data, args.item_code)
        data['stocks'] = [s for s in data['stocks'] if s['itemCode'] != args.item_code]
        for kind in ('sectors', 'themes', 'watchlists'):
            for members in data[kind].values():
                if args.item_code in members: members.remove(args.item_code)
        for leader_groups in data.get('leaders', {}).values():
            for members in leader_groups.values():
                members[:] = [code for code in members if code != args.item_code]
    elif cmd in ('enable-stock', 'disable-stock'):
        for stock in data['stocks']:
            if stock['itemCode'] == args.item_code:
                stock['enabled'] = cmd == 'enable-stock'; break
        else: require_stock(data, args.item_code)
    elif cmd in ('add-sector', 'add-theme', 'add-watchlist', 'add-group'):
        kind = args.kind if cmd == 'add-group' else cmd.removeprefix('add-')
        if args.name in groups(data, kind): raise ValueError(f'이미 존재하는 {kind}: {args.name}')
        groups(data, kind)[args.name] = []
    elif cmd in ('add-to-sector', 'add-to-theme', 'add-to-watchlist'):
        add_to(data, cmd.removeprefix('add-to-'), args.name, args.item_code)
    elif cmd == 'remove-from-group':
        group = groups(data, args.kind).get(args.name)
        if group is None: raise ValueError(f'존재하지 않는 그룹: {args.name}')
        if args.item_code in group: group.remove(args.item_code)
    elif cmd == 'set-leaders':
        if args.name not in groups(data, args.kind): raise ValueError(f'존재하지 않는 그룹: {args.name}')
        for item_code in args.item_codes: require_stock(data, item_code)
        data.setdefault('leaders', {}).setdefault(args.kind, {})[args.name] = args.item_codes
    write(data, args.dry_run)
    if getattr(args, 'publish', False) and not args.dry_run:
        publish_universe(getattr(args, 'message', None))


def parser():
    p = argparse.ArgumentParser(); p.add_argument('--dry-run', action='store_true'); p.add_argument('--publish', action='store_true'); p.add_argument('--message')
    sub = p.add_subparsers(dest='command', required=True)
    def item(command): command.add_argument('item_code', type=code)
    q = sub.add_parser('add-stock'); item(q); q.add_argument('stock_name', nargs='?'); q.add_argument('--name'); state=q.add_mutually_exclusive_group(); state.add_argument('--enabled', action='store_const', const=True, default=None); state.add_argument('--disabled', action='store_true'); q.add_argument('--sector', action='append', default=[]); q.add_argument('--theme', action='append', default=[]); q.add_argument('--watchlist', action='append', default=[]); q.add_argument('--create-groups', action='store_true')
    q = sub.add_parser('apply'); q.add_argument('payload'); q.add_argument('--dry-run', action='store_true', default=argparse.SUPPRESS)
    for name in ('remove-stock', 'enable-stock', 'disable-stock'):
        q = sub.add_parser(name); item(q)
    for name in ('add-sector', 'add-theme', 'add-watchlist'):
        sub.add_parser(name).add_argument('name')
    q = sub.add_parser('add-group'); q.add_argument('kind', choices=('sector','theme','watchlist')); q.add_argument('name')
    for name in ('add-to-sector', 'add-to-theme', 'add-to-watchlist'):
        q = sub.add_parser(name); q.add_argument('name'); item(q)
    q = sub.add_parser('remove-from-group'); q.add_argument('kind', choices=('sector','theme','watchlist')); q.add_argument('name'); item(q)
    q = sub.add_parser('set-leaders'); q.add_argument('kind', choices=('sector','theme','watchlist')); q.add_argument('name'); q.add_argument('item_codes', nargs='*', type=code)
    sub.add_parser('show'); sub.add_parser('validate')
    # Also accept publish options after a subcommand; SUPPRESS preserves prefix values.
    for command in sub.choices.values():
        command.add_argument('--publish', action='store_true', default=argparse.SUPPRESS)
        command.add_argument('--message', default=argparse.SUPPRESS)
        if command.prog.split()[-1] != 'apply':
            command.add_argument('--dry-run', action='store_true', default=argparse.SUPPRESS)
    return p


if __name__ == '__main__':
    try:
        run(parser().parse_args())
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f'오류: {exc}')
