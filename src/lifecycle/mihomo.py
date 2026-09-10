"""Stop and remove Mihomo service, package and manual installations."""
from common import *
import argparse
import configparser
import pwd
import fcntl


class Mihomo:
    def __init__(self):
        self.binaries = set()
        self.units = []
        self.supervisor = []
        self.owners = {}
        self.brew = None
        home = Path.home()
        self.paths = [Path(p) for p in ['/usr/local/lib/linspace-mihomo', '/etc/mihomo',
            '/var/lib/mihomo', '/var/log/mihomo', '/run/linspace-mihomo', '/run/mihomo',
            '/var/cache/linspace-mihomo']]
        self.paths += [home / '.config/mihomo', home / '.cache/mihomo']

    def discover(self, extra=()):
        if any(not Path(path).is_absolute() for path in extra):
            raise ValueError('--bin requires an absolute executable path.')
        directories = {Path('/usr/local/bin'), Path('/usr/bin'), Path.home() / '.local/bin'}
        directories |= {Path(p) for p in os.environ.get('PATH', '').split(':') if p.startswith('/')}
        candidates = [directory / name for directory in directories for name in ('mihomo', 'clash-meta')]
        candidates += [Path(p) for p in extra]
        for path in candidates:
            if not path.is_file():
                continue
            if path.is_symlink() and path.resolve().name not in {'mihomo', 'clash-meta'}:
                raise ValueError(f'{path} uses a shared launcher; remove it with its original package manager first.')
            result = run([str(path), '-v'], check=False, timeout=10)
            if result.returncode or 'mihomo' not in result.stdout.lower():
                raise ValueError(f'Unrecognized Mihomo executable: {path}')
            self.binaries.add(path)
            self.binaries.add(path.resolve())
            owner = package_owner(path.resolve()) or package_owner(path)
            if owner:
                if not all(name.split(':')[0] in {'mihomo', 'clash-meta'} for name in owner[1]):
                    raise ValueError('The Mihomo command belongs to an unrelated package.')
                self.owners[tuple(owner[1])] = owner
        for root in [Path('/etc/systemd/system'), Path('/usr/lib/systemd/system'), Path('/lib/systemd/system'),
                     Path.home() / '.config/systemd/user']:
            if not root.is_dir():
                continue
            for path in root.glob('*.service'):
                if path.is_symlink() or not path.is_file():
                    continue
                lines = path.read_text(errors='replace').splitlines()
                commands = [line.split('=', 1)[1].strip().lstrip('-+') for line in lines if line.startswith('ExecStart=')]
                for command in commands:
                    args = shlex.split(command)
                    if args and (Path(args[0]) in self.binaries or Path(args[0]).name == 'mihomo'):
                        if len(commands) != 1:
                            raise ValueError(f'Inspect this multi-command service manually: {path}')
                        self.units.append((path, root == Path.home() / '.config/systemd/user'))
                        self.service_paths(args)
        for pattern in ['/etc/supervisor/conf.d/*.conf', '/etc/supervisord.d/*.ini', '/etc/mihomo/supervisord.conf']:
            for path in Path('/').glob(pattern.lstrip('/')):
                parser = configparser.RawConfigParser(strict=False)
                parser.read(path)
                matches = []
                for section in parser.sections():
                    args = shlex.split(parser.get(section, 'command', fallback=''))
                    if section.startswith('program:') and args and (Path(args[0]) in self.binaries or Path(args[0]).name == 'mihomo'):
                        matches.append(section.split(':', 1)[1])
                        self.service_paths(args)
                if matches:
                    if len(matches) != len([s for s in parser.sections() if s.startswith('program:')]):
                        raise ValueError(f'Mihomo shares supervisor configuration with other programs: {path}; split that file before uninstalling.')
                    self.supervisor.append((path, matches))
        for _, _, executable, args, _ in process_table().values():
            if Path(executable) in self.binaries:
                self.service_paths(args)
        brew = shutil.which('brew')
        if brew and 'mihomo' in run([brew, 'list', '--formula'], check=False).stdout.splitlines():
            self.brew = brew
        for path in self.paths:
            dedicated(path)
        return self

    def service_paths(self, args):
        for flag in ('-d', '--dir'):
            if flag in args and args.index(flag) + 1 < len(args):
                path = Path(args[args.index(flag) + 1])
                if not path.is_absolute() or path.name not in {'mihomo', 'clash-meta'}:
                    raise ValueError('A custom service data directory is not dedicated to Mihomo; inspect and remove it manually.')
                self.paths.append(path)
        for flag in ('-f', '--config'):
            if flag in args and args.index(flag) + 1 < len(args):
                path = Path(args[args.index(flag) + 1])
                if not path.is_absolute() or path.suffix not in {'.yaml', '.yml'}:
                    raise ValueError('Inspect the nonstandard service configuration path before uninstalling.')
                self.paths.append(dedicated(path))
        if args:
            path = Path(args[0])
            if path.is_absolute() and path.name == 'mihomo':
                if path.is_file() and path not in self.binaries:
                    version = run([str(path), '-v'], check=False, timeout=10)
                    if version.returncode or 'mihomo' not in version.stdout.lower():
                        raise ValueError(f'Unrecognized service executable: {path}')
                self.binaries.add(path)

    def uninstall(self, dry_run=False):
        linux = sys.platform.startswith('linux')
        if linux and os.geteuid() != 0:
            raise RuntimeError('Mihomo uninstall requires root on Linux.')
        linspace_log('STEP', 'Uninstall Mihomo' + (' (preview)' if dry_run else ''))
        active_systemd = Path('/run/systemd/system').is_dir()
        for unit, user in self.units:
            linspace_log('INFO', f'Disable service: {unit.name}')
            if not dry_run and active_systemd:
                run(['systemctl', *(['--user'] if user else []), 'disable', '--now', unit.name])
        for path, names in self.supervisor:
            if shutil.which('supervisorctl'):
                dedicated_supervisor = path == Path('/etc/mihomo/supervisord.conf')
                if dedicated_supervisor and not dry_run:
                    run(['supervisorctl', '-c', str(path), 'shutdown'])
                    continue
                for name in names:
                    linspace_log('INFO', f'Stop supervisor program: {name}')
                    if not dry_run:
                        result = run(['supervisorctl', 'stop', name], check=False)
                        if result.returncode and not any(value in result.stdout.lower() for value in ('not running', 'no such process')):
                            raise RuntimeError('Could not stop the Mihomo supervisor program.')
        if self.brew and not dry_run:
            run([self.brew, 'services', 'stop', 'mihomo'])
        stop_processes({str(p) for p in self.binaries}, [Path('/usr/local/lib/linspace-mihomo')], dry_run, all_users=linux)
        for owner in self.owners.values():
            remove_packages(owner, dry_run)
        if self.brew and not dry_run:
            run([self.brew, 'uninstall', '--formula', 'mihomo'], timeout=180)
        for path, _ in self.units:
            for parent in path.parent.glob('*.wants'):
                link = parent / path.name
                if link.is_symlink() and link.resolve() == path.resolve():
                    remove(link, dry_run)
            remove(path, dry_run)
            remove(path.with_name(path.name + '.d'), dry_run)
        for path, _ in self.supervisor:
            remove(path, dry_run)
        if not dry_run and any(path != Path('/etc/mihomo/supervisord.conf') for path, _ in self.supervisor) and shutil.which('supervisorctl'):
            run(['supervisorctl', 'reread'])
            run(['supervisorctl', 'update'])
        for path in sorted(self.binaries, key=lambda p: not p.is_symlink()):
            remove(path, dry_run)
        for path in dict.fromkeys(self.paths):
            remove(path, dry_run)
        if not dry_run and self.units and active_systemd:
            run(['systemctl', 'daemon-reload'])
        if linux:
            try:
                account = pwd.getpwnam('mihomo')
            except KeyError:
                account = None
            if account and account.pw_dir == '/var/lib/mihomo' and account.pw_shell in {'/usr/sbin/nologin', '/sbin/nologin', '/bin/false'}:
                linspace_log('INFO', 'Remove dedicated Mihomo service account')
                if not dry_run:
                    run(['userdel', 'mihomo'])
                    # userdel may already remove the private group.
                    run(['groupdel', 'mihomo'], check=False)
        linspace_log('OK', 'Preview complete; no changes made.' if dry_run else 'Mihomo stopped and removed, including subscriptions, configuration, logs and cache.')
        linspace_log('INFO', 'Clear proxy variables in the current terminal: unset http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY')


def main():
    parser = argparse.ArgumentParser(description='Stop and remove Mihomo, its service, configuration and cached data.')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--bin', action='append', default=[], help='Additional absolute Mihomo executable path')
    args = parser.parse_args()
    if sys.platform.startswith('linux'):
        if os.geteuid() != 0:
            raise RuntimeError('Mihomo uninstall requires root on Linux.')
        lock = Path('/run/lock/linspace-mihomo.lock')
        lock.parent.mkdir(parents=True, exist_ok=True)
        if lock.is_symlink():
            raise ValueError('Refusing a symlinked operation lock.')
        with lock.open('a') as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError('Mihomo installation or subscription update is running; retry shortly.') from None
            Mihomo().discover(args.bin).uninstall(args.dry_run)
    else:
        Mihomo().discover(args.bin).uninstall(args.dry_run)
