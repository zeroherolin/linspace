#!/usr/bin/env python3
"""Install a built linspace release on one Debian/Ubuntu host."""
import argparse
import datetime
import fcntl
import fnmatch
import grp
import hashlib
import json
import os
import pwd
import re
import secrets
import shlex
import shutil
import subprocess
import sys
# A verified release must not gain generated Python cache files when executed.
sys.dont_write_bytecode = True
import tempfile
import time
from pathlib import Path
import verify

MAIN = Path('/etc/caddy/Caddyfile')
SITE = Path('/etc/caddy/sites-enabled/linspace.caddy')
FRAGMENT = Path('/etc/caddy/linspace.d/stash.caddy')
TOKEN = Path('/etc/linspace/stash-token')
CURRENT = Path('/srv/linspace/current')
STATE = Path('/var/lib/linspace/state.json')
IMPORT = 'import /etc/caddy/sites-enabled/linspace.caddy'
MANAGED = [MAIN, SITE, FRAGMENT, TOKEN, STATE, Path('/usr/local/lib/stashd/stashd.py'), Path('/etc/systemd/system/stashd.service'), Path('/etc/systemd/system/stashd.socket')]


def run(args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def atomic(path, data, mode=0o644, gid=0):
    path = Path(path)
    if path.is_symlink():
        raise ValueError(f'Refusing to replace symlink: {path}')
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.linspace-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, mode)
        os.chown(temporary, 0, gid)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def swap_link(target):
    temporary = CURRENT.parent / ('.current-' + secrets.token_hex(6))
    try:
        temporary.symlink_to(target)
        os.replace(temporary, CURRENT)
    finally:
        temporary.unlink(missing_ok=True)


def checked_release(release):
    release = release.resolve()
    manifest = release / 'SHA256SUMS'
    expected = set()
    for line in manifest.read_text().splitlines():
        sha, relative = line.split('  ', 1)
        path = release / relative
        if not re.fullmatch('[0-9a-f]{64}', sha) or path.is_symlink() or not path.resolve().is_relative_to(release) or not path.is_file():
            raise ValueError('Unsafe release manifest entry')
        if relative in expected or hashlib.sha256(path.read_bytes()).hexdigest() != sha:
            raise ValueError(f'Release checksum mismatch: {relative}')
        expected.add(relative)
    actual = set()
    for path in release.rglob('*'):
        if path.is_symlink():
            raise ValueError(f'Release contains symlink: {path}')
        if path.is_file() and path != manifest:
            actual.add(path.relative_to(release).as_posix())
    if actual != expected:
        raise ValueError('Release contains missing or unlisted files')
    meta = json.loads((release / 'release.json').read_text())
    if meta.get('format') != 1 or not re.fullmatch(r'[a-z0-9.-]+', meta['domain']):
        raise ValueError('Unsupported release metadata')
    return meta, hashlib.sha256(manifest.read_bytes()).hexdigest()[:20]


def merged_main(text, domain, fresh=False, adopt=False):
    if fresh or not text.strip():
        return IMPORT + '\n'
    depth = 0
    for line in text.splitlines():
        parts = shlex.split(line, comments=True)
        if depth == 0 and len(parts) == 2 and parts[0] == 'import':
            pattern = str((MAIN.parent / parts[1]).absolute())
            if fnmatch.fnmatchcase(str(SITE), pattern):
                return text
        depth += parts.count('{') - parts.count('}')
    if re.search(r'(?m)^\s*' + re.escape(domain) + r'\s*\{', text):
        # Adopt only the project's previous single-site layout. Other sites require manual integration.
        stripped = text.strip()
        if adopt and stripped.startswith(domain + ' {') and 'root * /srv/linspace' in stripped:
            depth = 0
            end = None
            for i, char in enumerate(stripped):
                depth += (char == '{') - (char == '}')
                if char == '}' and depth == 0:
                    end = i
                    break
            if end == len(stripped) - 1:
                return IMPORT + '\n'
        raise ValueError('This domain already has a site block. Integrate the managed import manually, or use --adopt-existing for the previous single-site linspace layout.')
    return text.rstrip() + '\n\n' + IMPORT + '\n'


def snapshot(directory):
    directory.mkdir(parents=True, mode=0o700)
    os.chmod(directory, 0o700)
    entries = []
    for path in MANAGED:
        if path.is_symlink():
            raise ValueError(f'Managed configuration must not be a symlink: {path}')
        item = {'path': str(path), 'exists': path.exists()}
        if path.exists():
            info = path.stat()
            item.update(mode=info.st_mode & 0o777, gid=info.st_gid, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            shutil.copyfile(path, directory / str(len(entries)))
            os.chmod(directory / str(len(entries)), 0o600)
        entries.append(item)
    state = {'entries': entries, 'current': os.readlink(CURRENT) if CURRENT.is_symlink() else None,
             'caddy_active': subprocess.run(['systemctl', 'is-active', '--quiet', 'caddy']).returncode == 0,
             'stash_active': subprocess.run(['systemctl', 'is-active', '--quiet', 'stashd.socket']).returncode == 0,
             'stash_enabled': subprocess.run(['systemctl', 'is-enabled', '--quiet', 'stashd.socket'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0}
    (directory / 'snapshot.json').write_text(json.dumps(state, indent=2) + '\n')
    return state


def restore(directory):
    state = json.loads((directory / 'snapshot.json').read_text())
    if {item['path'] for item in state['entries']} != {str(path) for path in MANAGED} or len(state['entries']) != len(MANAGED):
        raise ValueError('Backup does not describe exactly the managed files')
    for index, item in enumerate(state['entries']):
        if item['exists'] and hashlib.sha256((directory / str(index)).read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('Backup checksum mismatch; no services changed')
    if state['current'] is not None:
        target = Path(state['current'])
        if target.is_absolute() or '..' in target.parts or not target.parts or target.parts[0] != 'releases' or not (CURRENT.parent / target).is_dir():
            raise ValueError('The previous public release is missing or invalid; no services changed')
    subprocess.run(['systemctl', 'stop', 'stashd.service', 'stashd.socket'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for index, item in enumerate(state['entries']):
        path = Path(item['path'])
        if path not in MANAGED:
            raise ValueError('Invalid backup path')
        if item['exists']:
            atomic(path, (directory / str(index)).read_bytes(), item['mode'], item['gid'])
        else:
            path.unlink(missing_ok=True)
    if state['current'] is not None:
        swap_link(state['current'])
    else:
        CURRENT.unlink(missing_ok=True)
    run(['systemctl', 'daemon-reload'])
    if state['stash_enabled']:
        run(['systemctl', 'enable', 'stashd.socket'], stdout=subprocess.DEVNULL)
    else:
        subprocess.run(['systemctl', 'disable', 'stashd.socket'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if state['stash_active']:
        run(['systemctl', 'start', 'stashd.socket'])
    if state['caddy_active']:
        run(['caddy', 'validate', '--config', MAIN], stdout=subprocess.DEVNULL)
        run(['systemctl', 'reload', 'caddy'])
    else:
        run(['systemctl', 'stop', 'caddy'])
    print(f'Restored configuration, token, code, and release pointer from {directory}. Stash channel data was not changed.')


def apply(release, args):
    meta, release_id = checked_release(release)
    if meta['internal_test'] and not args.internal_test:
        raise ValueError('An internal-test build requires --internal-test; rebuild with filed site details for production')
    print(f'Domain: {meta["domain"]}\nPublic release: /srv/linspace/releases/{release_id}\nCaddy: {SITE}\nStash token: {TOKEN}\nMode: ' + ('internal test' if meta['internal_test'] else 'production'))
    if args.dry_run:
        print('Plan: validate build, install missing dependencies, back up managed files, activate release, reload services, verify HTTPS. No host changes made.')
        return
    if os.geteuid() != 0 or not Path('/etc/debian_version').exists() or not Path('/run/systemd/system').is_dir():
        raise ValueError('Deployment requires root on Debian/Ubuntu with a running systemd. Use sudo ./linspace deploy.')
    os.umask(0o022)
    for parent in ['/srv/linspace', '/etc/linspace', '/var/lib/linspace', '/usr/local/lib/stashd', '/etc/caddy/sites-enabled', '/etc/caddy/linspace.d']:
        if Path(parent).is_symlink():
            raise ValueError(f'Refusing managed symlink directory: {parent}')
    if CURRENT.is_symlink() and (not CURRENT.is_dir() or not CURRENT.resolve().is_relative_to(Path('/srv/linspace/releases'))):
        raise ValueError('The active release symlink must point to an existing managed release')
    if CURRENT.exists() and not CURRENT.is_symlink():
        raise ValueError('/srv/linspace/current must be absent or the managed release symlink')
    fresh_caddy = shutil.which('caddy') is None
    # Syntax and checksums are checked before installing packages or changing services.
    for script in list((release / 'site/mihomo').glob('*')) + list((release / 'site/stash').glob('*')):
        if script.is_file():
            run(['bash', '-n', script])
    compile((release / 'service/stashd.py').read_text(), 'stashd.py', 'exec')
    run(['bash', release / 'install-caddy.sh'])
    if shutil.which('curl') is None or shutil.which('ssh-keygen') is None:
        run(['apt-get', 'update'])
        run(['apt-get', 'install', '-y', '--no-install-recommends', 'curl', 'ca-certificates', 'openssh-client'])
    version = run(['caddy', 'version'], text=True, capture_output=True).stdout
    match = re.search(r'v(\d+)\.(\d+)\.(\d+)', version)
    if not match or tuple(map(int, match.groups())) < (2, 10, 0):
        raise ValueError('Caddy 2.10 or later is required. Upgrade the existing Caddy package before deploying.')
    caddy_gid = grp.getgrnam('caddy').gr_gid
    if SITE.exists() and not STATE.exists():
        raise ValueError(f'{SITE} already exists without managed state. Inspect that file before assigning it to this installation.')
    if STATE.exists() and json.loads(STATE.read_text()).get('format') != 1:
        raise ValueError('Existing linspace state has an unsupported format')
    main_text = merged_main(MAIN.read_text() if MAIN.exists() else '', meta['domain'], fresh=fresh_caddy, adopt=args.adopt_existing)
    Path('/var/lib/linspace').mkdir(parents=True, exist_ok=True)
    with Path('/var/lib/linspace/deploy.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + secrets.token_hex(3)
        backup = Path('/var/backups/linspace') / stamp
        snapshot(backup)
        print(f'Backup: {backup}')
        try:
            try:
                account = pwd.getpwnam('stash')
                if account.pw_uid == 0 or grp.getgrgid(account.pw_gid).gr_name != 'stash' or account.pw_dir != '/var/lib/stashd' or not account.pw_shell.endswith('/nologin'):
                    raise ValueError('Existing stash account is not a dedicated service account')
            except KeyError:
                run(['useradd', '--system', '--user-group', '--home-dir', '/var/lib/stashd', '--no-create-home', '--shell', '/usr/sbin/nologin', 'stash'])
            current_hash = None
            if FRAGMENT.exists():
                matches = re.findall(r'^\s*stash\s+(\$2[aby]\$\S+)\s*$', FRAGMENT.read_text(), re.M)
                if len(matches) != 1:
                    raise ValueError('Cannot find exactly one existing stash token hash; inspect the fragment before retrying')
                current_hash = matches[0]
            new_token = None
            if current_hash is None or args.rotate_token:
                new_token = secrets.token_hex(24)
                current_hash = run(['caddy', 'hash-password', '--bcrypt-cost', '10'], input=new_token + '\n', text=True, capture_output=True).stdout.strip()
                if not re.fullmatch(r'\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}', current_hash):
                    raise ValueError('Caddy returned an invalid password hash')
            public_release = Path('/srv/linspace/releases') / release_id
            public_release.parent.mkdir(parents=True, exist_ok=True)
            if public_release.is_symlink():
                raise ValueError('Release directories must not be symlinks')
            if public_release.exists():
                actual = {p.relative_to(public_release): p.read_bytes() for p in public_release.rglob('*') if p.is_file()}
                wanted = {p.relative_to(release / 'site'): p.read_bytes() for p in (release / 'site').rglob('*') if p.is_file()}
                if actual != wanted or any(p.is_symlink() for p in public_release.rglob('*')):
                    raise ValueError('Existing release directory differs from its immutable build')
            else:
                # A failed copy must not leave a partial directory under an immutable release ID.
                with tempfile.TemporaryDirectory(prefix='.staging-', dir=public_release.parent) as temporary:
                    staged = Path(temporary) / 'site'
                    shutil.copytree(release / 'site', staged)
                    for path in [staged, *staged.rglob('*')]:
                        path.chmod(0o755 if path.is_dir() else 0o644)
                    os.replace(staged, public_release)
            atomic(SITE, (release / 'config/Caddyfile').read_bytes())
            atomic(FRAGMENT, (release / 'config/stash.caddy.template').read_text().replace('__HASH__', current_hash).encode(), 0o640, caddy_gid)
            atomic(MAIN, main_text.encode())
            for name, destination in [('stashd.py', '/usr/local/lib/stashd/stashd.py'), ('stashd.service', '/etc/systemd/system/stashd.service'), ('stashd.socket', '/etc/systemd/system/stashd.socket')]:
                atomic(Path(destination), (release / 'service' / name).read_bytes())
            if new_token:
                TOKEN.parent.mkdir(parents=True, exist_ok=True)
                TOKEN.parent.chmod(0o700)
                atomic(TOKEN, (new_token + '\n').encode(), 0o600)
            swap_link('releases/' + release_id)
            run(['caddy', 'validate', '--config', MAIN], stdout=subprocess.DEVNULL)
            run(['systemd-analyze', 'verify', '/etc/systemd/system/stashd.socket', '/etc/systemd/system/stashd.service'], stdout=subprocess.DEVNULL)
            run(['systemctl', 'daemon-reload'])
            run(['systemctl', 'stop', 'stashd.service', 'stashd.socket'])
            run(['systemctl', 'enable', '--now', 'stashd.socket'], stdout=subprocess.DEVNULL)
            for attempt in range(20):
                response = subprocess.run(['curl', '-q', '-sS', '--max-time', '2', '--unix-socket', '/run/stashd/stashd.sock', '-o', '/dev/null', '-w', '%{http_code}', 'http://stashd/'], text=True, capture_output=True)
                if response.returncode == 0 and response.stdout == '405':
                    break
                time.sleep(.25)
            else:
                raise RuntimeError('stashd did not answer on its Unix socket')
            run(['systemctl', 'enable', '--now', 'caddy'], stdout=subprocess.DEVNULL)
            run(['systemctl', 'reload', 'caddy'])
            atomic(STATE, (json.dumps({**meta, 'release_id': release_id, 'backup': str(backup)}, indent=2) + '\n').encode(), 0o600)
        except BaseException:
            print(f'Deployment failed; restoring {backup}', file=sys.stderr)
            try:
                restore(backup)
            except Exception as error:
                print(f'Automatic restore failed: {error}. Backup retained at {backup}', file=sys.stderr)
            raise
    print(f'Installed release {release_id}. ' + (f'Token saved to {TOKEN} (root-only).' if new_token else 'Existing stash token retained.'))
    if args.skip_verify:
        print('HTTPS verification skipped explicitly. Run ./linspace verify before declaring the site ready.')
        return
    last_error = None
    for attempt in range(12):
        try:
            verify.verify(meta, args.local, quiet=True)
            return
        except (RuntimeError, OSError) as error:
            last_error = error
            if attempt < 11:
                time.sleep(5)
    raise RuntimeError(f'Installed successfully, but HTTPS verification is not ready: {last_error}. Check DNS, ports 80/443, and journalctl -u caddy; then run ./linspace verify. The valid installation is retained.')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--rotate-token', action='store_true')
    parser.add_argument('--adopt-existing', action='store_true')
    parser.add_argument('--internal-test', action='store_true')
    parser.add_argument('--local', action='store_true', help='verify via loopback with normal TLS validation')
    parser.add_argument('--skip-verify', action='store_true')
    parser.add_argument('--rollback', type=Path, help='restore an exact backup directory under /var/backups/linspace')
    args = parser.parse_args(argv)
    if args.rollback:
        if os.geteuid() != 0 or args.rollback.is_symlink() or args.rollback.resolve().parent != Path('/var/backups/linspace'):
            raise ValueError('Rollback requires root and a direct backup directory under /var/backups/linspace')
        with Path('/var/lib/linspace/deploy.lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            restore(args.rollback)
    else:
        apply(args.release.resolve(), args)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print(f'Error: {error}', file=sys.stderr)
        sys.exit(1)
