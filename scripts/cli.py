#!/usr/bin/env python3
"""User entry point for configuration, builds, deployment, and verification."""
import argparse
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
    current = json.loads(args.config.read_text()) if args.config.exists() else json.loads((ROOT / 'config/site.example.json').read_text())
    questions = [('domain', 'Domain (already resolved and ICP-filed; no https://)'), ('site_name', 'Registered website name'), ('icp_number', 'Complete ICP filing number'), ('ssh_public_key_file', 'SSH PUBLIC key file (empty to disable key publishing)'), ('claude_settings_file', 'Public Claude settings JSON file')]
    for key, prompt in questions:
        supplied = getattr(args, key, None)
        if supplied is not None:
            current[key] = supplied
        elif not args.non_interactive:
            previous = current.get(key, '')
            entered = input(f'{prompt}' + (f' [{previous}]' if previous else '') + ': ').strip()
            current[key] = '' if key == 'ssh_public_key_file' and entered == '-' else entered or previous
    args.config.parent.mkdir(parents=True, exist_ok=True)
    pending = args.config.with_name('.site-pending.json')
    try:
        pending.write_text(json.dumps(current, ensure_ascii=False, indent=2) + '\n')
        config, key_data, settings = siteconfig.load(pending, args.internal_test)
        if key_data:
            public = ROOT / 'local/ssh.pub'
            public.parent.mkdir(parents=True, exist_ok=True)
            public.write_bytes(key_data)
            config['ssh_public_key_file'] = 'local/ssh.pub'
        # Retain chosen settings path; the neutral default contains no personal preferences.
        pending.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n')
        pending.chmod(0o600)
        os.replace(pending, args.config)
    finally:
        pending.unlink(missing_ok=True)
    print(f'Saved {args.config}. Domain, homepage, and client URLs will be generated together.')
    options = (' --config ' + shlex.quote(str(args.config))) if args.config != DEFAULT else ''
    options += ' --internal-test' if args.internal_test else ''
    print(f'Next: ./linspace deploy{options} --dry-run, then sudo ./linspace deploy{options}')


def main():
    parser = argparse.ArgumentParser(description='Configure and deploy your own linspace HTTPS site.')
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('configure', 'build', 'deploy', 'verify', 'urls'):
        p = sub.add_parser(name)
        p.add_argument('--config', type=Path, default=DEFAULT)
        p.add_argument('--internal-test', action='store_true', help='internal testing only; allow reserved domains and an empty filing number')
        if name == 'configure':
            for field in sorted(siteconfig.FIELDS):
                p.add_argument('--' + field.replace('_', '-'))
            p.add_argument('--non-interactive', action='store_true')
        if name == 'deploy':
            for flag in ('dry-run', 'rotate-token', 'adopt-existing', 'skip-verify', 'local'):
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
                flags = ['--' + name.replace('_', '-') for name in ('dry_run', 'rotate_token', 'adopt_existing', 'skip_verify', 'internal_test', 'local') if getattr(args, name)]
                deploy.main(['--release', str(release), *flags])
        else:
            config, key, _ = siteconfig.load(args.config, args.internal_test)
            if args.command == 'verify':
                asset = json.loads((ROOT / 'assets/manifest.json').read_text())['geoip']
                verify.verify({'domain': config['domain'], 'ssh_enabled': key is not None, 'geoip_sha256': asset['sha256']}, args.local)
            else:
                paths = ['', 'mihomo/install', 'mihomo/sub', 'mihomo/restart', 'claude/install', 'claude/config', 'stash/upload0', 'stash/download0', 'stash/clear']
                if key:
                    paths.insert(1, 'ssh/key.pub')
                for path in paths:
                    print(f'https://{config["domain"]}/{path}')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print(f'Error: {error}', file=sys.stderr)
        sys.exit(1)
