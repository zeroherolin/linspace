#!/usr/bin/env python3
"""User entry point for configuration, builds, deployment, and verification."""
from linspace_console import linspace_log
import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
import build
import deploy
import siteconfig
import verify

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / 'local/site.json'


def configure(args):
    linspace_log('STEP', 'Configure site')
    current = json.loads((ROOT / 'config/site.example.json').read_text())
    if args.config.exists():
        current.update(json.loads(args.config.read_text()))
    questions = [('domain', 'Domain (already resolved and ICP-filed; no https://)'), ('site_name', 'Registered website name'), ('icp_number', 'Complete ICP filing number'), ('ssh_public_key_file', 'SSH PUBLIC key file (empty to disable key publishing)'), ('ssh_public_key_name', 'Published SSH key filename (e.g. team.pub)'), ('claude_settings_file', 'Public Claude Code settings JSON file'), ('codex_config_file', 'Public Codex configuration TOML file')]
    for key, prompt in questions:
        supplied = getattr(args, key, None)
        if supplied is not None:
            current[key] = supplied
        elif not args.non_interactive:
            if key == 'ssh_public_key_name' and not current.get('ssh_public_key_file'):
                continue
            previous = current.get(key, '')
            entered = input(f'{prompt}' + (f' [{previous}]' if previous else '') + ': ').strip()
            current[key] = '' if key == 'ssh_public_key_file' and entered == '-' else entered or previous
    if args.stash_public_key_files is not None:
        current['stash_public_key_files'] = args.stash_public_key_files
    elif not args.non_interactive:
        previous = current.get('stash_public_key_files')
        entered = input('Stash public keys: JSON path array, [] disables writes, auto reuses the SSH key'
                        f' [{json.dumps(previous) if previous is not None else "auto"}]: ').strip()
        if entered:
            current['stash_public_key_files'] = None if entered == 'auto' else json.loads(entered)
    args.config.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.site-', suffix='.json', dir=args.config.parent)
    os.close(fd)
    pending = Path(temporary)
    try:
        pending.write_text(json.dumps(current, ensure_ascii=False, indent=2) + '\n')
        config, key_data, _, _ = siteconfig.load(pending, args.internal_test, root=ROOT)
        if key_data:
            public = ROOT / 'local/keys' / (hashlib.sha256(key_data).hexdigest() + '.pub')
            public.parent.mkdir(parents=True, exist_ok=True)
            if public.is_symlink() or public.exists() and public.read_bytes() != key_data:
                raise ValueError('The saved public-key copy is invalid; inspect local/keys before retrying')
            if not public.exists():
                fd, temporary = tempfile.mkstemp(prefix='.key-', dir=public.parent)
                try:
                    with os.fdopen(fd, 'wb') as output:
                        output.write(key_data)
                    os.chmod(temporary, 0o644)
                    os.replace(temporary, public)
                finally:
                    Path(temporary).unlink(missing_ok=True)
            config['ssh_public_key_file'] = public.relative_to(ROOT).as_posix()
        # Retain operator-selected public configuration paths.
        pending.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n')
        pending.chmod(0o600)
        os.replace(pending, args.config)
    finally:
        pending.unlink(missing_ok=True)
    linspace_log('OK', f'Saved {args.config}')
    linspace_log('INFO', 'Stash uses SSH signatures; no token is needed.')
    options = (' --config ' + shlex.quote(str(args.config))) if args.config != DEFAULT else ''
    options += ' --internal-test' if args.internal_test else ''
    linspace_log('INFO', f'Next: ./linspace deploy{options} --dry-run, then sudo ./linspace deploy{options}')


def main():
    parser = argparse.ArgumentParser(description='Configure and deploy your own linspace HTTPS site.')
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('configure', 'build', 'deploy', 'verify', 'urls'):
        p = sub.add_parser(name)
        p.add_argument('--config', type=Path, default=DEFAULT)
        p.add_argument('--internal-test', action='store_true', help='internal testing only; allow reserved domains and an empty filing number')
        if name == 'configure':
            for field in siteconfig.FIELDS:
                p.add_argument('--' + field.replace('_', '-'), **({'nargs': '*'} if field == 'stash_public_key_files' else {}))
            p.add_argument('--non-interactive', action='store_true')
        if name == 'deploy':
            for flag in ('dry-run', 'adopt-existing', 'skip-verify', 'local'):
                p.add_argument('--' + flag, action='store_true')
        if name == 'verify':
            p.add_argument('--local', action='store_true')
    sub.add_parser('check')
    p = sub.add_parser('rollback')
    p.add_argument('backup', type=Path)
    args = parser.parse_args()
    if args.command == 'configure':
        configure(args)
    elif args.command == 'check':
        subprocess.run([sys.executable, str(ROOT / 'scripts/check.py')], check=True, cwd=ROOT)
    elif args.command == 'rollback':
        deploy.main(['--rollback', str(args.backup)])
    else:
        if not args.config.exists():
            raise ValueError(f'{args.config} is missing. Run ./linspace configure first.')
        if args.command == 'build':
            build.build(args.config, internal=args.internal_test)
        elif args.command == 'deploy':
            # sudo deployment must not leave root-owned build files in a user's checkout.
            with tempfile.TemporaryDirectory(prefix='linspace-deploy-') as temporary:
                release = build.build(args.config, Path(temporary) / 'dist', internal=args.internal_test)
                flags = ['--' + name.replace('_', '-') for name in ('dry_run', 'adopt_existing', 'skip_verify', 'internal_test', 'local') if getattr(args, name)]
                deploy.main(['--release', str(release), *flags])
        else:
            config, key, _, _ = siteconfig.load(args.config, args.internal_test)
            if args.command == 'verify':
                verify.verify({'domain': config['domain'], 'ssh_enabled': key is not None, 'ssh_public_key_name': config['ssh_public_key_name']}, args.local)
            else:
                paths = ['', 'mihomo/install', 'mihomo/sub', 'mihomo/restart', 'claude/install', 'claude/config', 'codex/install', 'codex/config', 'codex/models_1m', 'codex/auth', 'stash/upload0', 'stash/download0', 'stash/clear']
                paths += [f'{client}/uninstall' for client in ('mihomo', 'claude', 'codex')]
                if key:
                    paths.insert(1, 'ssh/' + config['ssh_public_key_name'])
                for path in paths:
                    print(f'https://{config["domain"]}/{path}')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as error:
        linspace_log('ERROR', error)
        sys.exit(1)
