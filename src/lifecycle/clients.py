"""Remove recognized CLI installations while retaining conversation history."""
from common import *
import argparse
import glob
import json

CLIENT = '@@CLIENT@@'


class Client:
    def __init__(self, name, home=None, system=True):
        self.name = name
        self.home = Path.home() if home is None else Path(home)
        self.system = system
        self.package = '@anthropic-ai/claude-code' if name == 'claude' else '@openai/codex'
        self.configs = list(dict.fromkeys([self.home / ('.claude' if name == 'claude' else '.codex'),
            Path(os.environ.get('CLAUDE_CONFIG_DIR' if name == 'claude' else 'CODEX_HOME', self.home / ('.' + name)))]))
        self.data = list(dict.fromkeys([self.home / '.local/share', Path(os.environ.get('XDG_DATA_HOME', self.home / '.local/share'))]))
        self.roots = [root / 'linspace' / name for root in self.data]
        self.roots += ([root / 'claude' for root in self.data] + [p / 'local' for p in self.configs]
                       if name == 'claude' else [p / 'packages/standalone' for p in self.configs])
        self.launchers = set()
        self.targets = set()
        self.npm = {}
        self.managers = []
        self.manager_roots = set()
        self.owners = {}

    def discover(self, extra=()):
        if any(not Path(path).is_absolute() for path in extra):
            raise ValueError('--bin requires an absolute executable path.')
        for path in [self.home, *self.configs, *self.roots]:
            if not path.is_absolute():
                raise ValueError('Use absolute HOME and client data paths.')
        for path in [*self.configs, *self.roots]:
            dedicated(path, self.home)
        if any(path.is_symlink() for path in self.configs):
            raise ValueError('Client state directories must not be symbolic links.')
        directories = [self.home / '.local/bin', self.home / 'bin']
        if self.system:
            directories += [Path(p) for p in os.environ.get('PATH', '').split(':') if p.startswith('/')]
            directories += [Path('/usr/local/bin'), Path('/usr/bin'), Path('/opt/homebrew/bin')]
        if self.name == 'codex' and os.environ.get('CODEX_INSTALL_DIR'):
            directories += [Path(os.environ['CODEX_INSTALL_DIR'])]
        candidates = [p / self.name for p in directories] + [Path(p) for p in extra]
        self.find_npm(directories)
        candidates += [prefix / 'bin' / self.name for _, prefix in self.npm.values()]
        for root in self.roots:
            patterns = ['*/package/claude', 'versions/*', 'node_modules/.bin/claude'] if self.name == 'claude' else ['*/bin/codex', 'releases/*/bin/codex']
            for pattern in patterns:
                candidates += list(root.glob(pattern))
        if self.system:
            self.find_other_managers()
        for path in candidates:
            if not path.exists() and not path.is_symlink():
                continue
            target = path.resolve()
            # Official Codex's current/bin/codex traverses an internal release
            # symlink. Canonicalize only when it stays inside a known data root.
            if any(parent.is_symlink() for parent in path.parents) and any(within(target, root) for root in self.roots):
                path = target
            dedicated(path, self.home)
            if any(part.endswith('.app') for part in target.parts):
                if str(path) in extra:
                    raise ValueError('Desktop application bundles are outside CLI uninstall scope.')
                continue
            known = any(within(target, root) for root in self.roots) or any(within(target, root) for root in self.npm)
            if not known and self.managers:
                for parent in target.parents:
                    metadata = parent / 'package.json'
                    if metadata.is_file():
                        try:
                            matches = json.loads(metadata.read_text()).get('name') == self.package
                        except (ValueError, OSError):
                            matches = False
                        if matches:
                            self.manager_roots.add(parent)
                            known = True
                            break
            if path.is_symlink() and not known and not re.fullmatch(re.escape(self.name) + r'(?:-[A-Za-z0-9._-]+)?', target.name):
                raise ValueError(f'{path} uses a shared or unknown launcher; remove it with its original package/version manager first.')
            if path.exists() and not path.is_file():
                raise ValueError(f'The command path is not a file: {path}')
            if not known and path.exists():
                version = run([str(path), '--version'], check=False, timeout=15)
                if version.returncode or not re.search(r'\d+\.\d+\.\d+', version.stdout) or self.name not in version.stdout.lower():
                    raise ValueError(f'Unrecognized command; inspect it before uninstalling: {path}')
            if not known and not path.exists():
                raise ValueError(f'Unrecognized broken launcher: {path}')
            self.launchers.add(path)
            self.targets.add(str(target))
            if self.system:
                owner = package_owner(target) or package_owner(path)
                if owner:
                    # Refuse removing an unrelated multi-tool package due to one alias.
                    approved = {'claude-code'} if self.name == 'claude' else {'codex', 'codex-cli', 'openai-codex'}
                    if not all(name.split(':')[0] in approved for name in owner[1]):
                        raise ValueError(f'{path} belongs to an unrelated system package; remove its launcher manually.')
                    self.owners[tuple(owner[1])] = owner
        return self

    def find_npm(self, directories):
        prefixes = {p.parent for p in directories if p.name == 'bin'}
        prefixes |= {self.home / '.npm-global', self.home / '.local'}
        if self.system:
            prefixes |= {Path('/usr'), Path('/usr/local')}
        for pattern in ['.nvm/versions/node/*', '.local/share/fnm/node-versions/*/installation',
                        '.asdf/installs/nodejs/*', '.volta/tools/image/node/*']:
            prefixes.update(Path(p) for p in glob.glob(str(self.home / pattern)))
        npm = shutil.which('npm') if self.system else None
        if npm:
            result = run([npm, 'prefix', '-g'], check=False)
            if result.returncode == 0 and result.stdout.strip().startswith('/'):
                prefixes.add(Path(result.stdout.strip()))
        for prefix in prefixes:
            metadata = prefix / 'lib/node_modules' / self.package / 'package.json'
            if not metadata.is_file():
                continue
            if json.loads(metadata.read_text()).get('name') != self.package:
                raise ValueError(f'Unexpected package metadata: {metadata}')
            manager = prefix / 'bin/npm'
            tool = str(manager) if manager.is_file() else npm
            self.npm[metadata.parent] = (tool, prefix)

    def find_other_managers(self):
        brew = shutil.which('brew')
        if brew:
            env = {**os.environ, 'HOMEBREW_NO_AUTO_UPDATE': '1', 'HOMEBREW_NO_INSTALL_CLEANUP': '1'}
            for kind in ('formula', 'cask'):
                result = run([brew, 'list', '--' + kind], check=False, env=env)
                approved = {'claude-code', 'claude-code@latest'} if self.name == 'claude' else {'codex'}
                for name in set(result.stdout.splitlines()) & approved:
                    self.managers.append(([brew, 'uninstall', '--' + kind, name], env))
        for manager, query, uninstall in [('pnpm', ['list', '-g', '--depth', '0', '--json'], ['remove', '-g']),
                                          ('yarn', ['global', 'list', '--json'], ['global', 'remove']),
                                          ('bun', ['pm', 'ls', '-g'], ['remove', '-g'])]:
            tool = shutil.which(manager)
            if not tool:
                continue
            result = run([tool, *query], check=False)
            if result.returncode == 0 and re.search(re.escape(self.package) + r'(?:["\s@]|$)', result.stdout):
                self.managers.append(([tool, *uninstall, self.package], None))

    def history(self, dry_run):
        for directory in self.configs:
            if self.name == 'claude':
                keep = lambda name: name in {'projects', 'history.jsonl'}
            else:
                keep = lambda name: name in {'sessions', 'archived_sessions', 'history.jsonl', 'session_index.jsonl'} or bool(re.fullmatch(r'state_\d+\.sqlite(?:-wal|-shm)?', name))
            clear_history_except(directory, keep, dry_run)
        if self.name == 'claude':
            for path in self.home.glob('.claude.json*'):
                remove(path, dry_run)

    def logout(self, dry_run):
        # Use the client credential backend so OS keyring entries are also cleared.
        command = next((p for p in sorted(self.launchers, key=lambda p: (p.name != self.name, len(p.parts))) if p.exists()), None)
        if command and not dry_run:
            for directory in self.configs:
                if not directory.exists():
                    continue
                env = {**os.environ, 'CLAUDE_CONFIG_DIR' if self.name == 'claude' else 'CODEX_HOME': str(directory)}
                args = [str(command), 'auth', 'logout'] if self.name == 'claude' else [str(command), 'logout']
                result = run(args, check=False, env=env, timeout=20)
                if result.returncode:
                    raise RuntimeError('Client logout failed; resolve the credential-backend error before uninstalling.')
        elif not command and not dry_run and sys.platform == 'darwin':
            # Never claim that absent executables imply absent keychain credentials.
            if any((p / 'auth.json').exists() or (p / '.credentials.json').exists() or (p / 'config.toml').exists() or (p / 'settings.json').exists() for p in self.configs):
                raise RuntimeError('No working client can clear the macOS keychain. Reinstall the client, then retry uninstall.')

    def uninstall(self, dry_run=False):
        for root, (npm, prefix) in self.npm.items():
            if not npm:
                raise RuntimeError(f'npm is required to remove {root}; restore that Node installation first.')
        for owner in self.owners.values():
            if not dry_run and os.geteuid() != 0:
                raise RuntimeError('A system package is installed. Remove it as administrator, then rerun as this client account.')
        for path in [*self.launchers, *self.roots, *self.npm]:
            if path.exists() and not dry_run and not os.access(path.parent, os.W_OK):
                raise RuntimeError(f'Administrator access is needed to remove {path}; remove that installation separately, then retry as this account.')
        cache = Path(os.environ.get('XDG_CACHE_HOME', self.home / '.cache'))
        linspace_log('STEP', f'Uninstall {self.name}' + (' (preview)' if dry_run else ''))
        if not dry_run and os.geteuid() == 0:
            own = matching_processes(self.targets, self.roots + list(self.npm) + list(self.manager_roots))
            others = matching_processes(self.targets, self.roots + list(self.npm) + list(self.manager_roots), all_users=True)
            if set(others) - set(own):
                raise RuntimeError('Another account is using this shared installation; close those sessions before uninstalling.')
        stop_processes(self.targets, self.roots + list(self.npm) + list(self.manager_roots), dry_run)
        self.logout(dry_run)
        for args, env in self.managers:
            linspace_log('INFO', f'Uninstall with {Path(args[0]).name}: {args[-1]}')
            if not dry_run:
                run(args, env=env, timeout=180)
        for root, (npm, prefix) in self.npm.items():
            linspace_log('INFO', f'Uninstall {self.package} from {prefix}')
            if not dry_run and root.exists():
                run([npm, 'uninstall', '-g', '--prefix', str(prefix), '--ignore-scripts', '--offline', '--no-audit', '--no-fund', self.package], timeout=180,
                    env={**os.environ, 'PATH': str(prefix / 'bin') + os.pathsep + os.environ.get('PATH', '')})
        for owner in self.owners.values():
            remove_packages(owner, dry_run)
        if self.name == 'claude' and os.geteuid() == 0:
            for source in [Path('/etc/apt/sources.list.d/claude-code.list'), Path('/etc/apt/sources.list.d/claude-code.sources'), Path('/etc/yum.repos.d/claude-code.repo')]:
                if source.is_file() and 'downloads.claude.ai/claude-code' in source.read_text():
                    remove(source, dry_run)
                    if source.parent.name == 'sources.list.d':
                        remove(Path('/etc/apt/keyrings/claude-code.asc'), dry_run)
        for path in self.launchers:
            target = path.resolve()
            remove(path, dry_run)
            # A standalone executable can have a symlink in PATH. Only remove the
            # identified target, never an arbitrary parent tree such as /usr/bin.
            if target != path and not any(within(target, root) for root in self.roots + list(self.npm) + list(self.manager_roots)):
                if target.exists():
                    remove(target, dry_run)
        for root in self.roots:
            remove(root, dry_run)
        self.history(dry_run)
        for path in [cache / 'linspace' / self.name, cache / self.name, cache / (self.package.replace('/', '-'))]:
            remove(path, dry_run)
        # Prior installer versions used a shared content-addressed cache.
        for digest in '@@CLIENT_CACHE_HASHES@@'.split():
            remove(cache / 'linspace' / digest, dry_run)
        if not dry_run:
            leftovers = [p for p in self.launchers if p.exists() or p.is_symlink()]
            leftovers += [p for p in self.roots + list(self.npm) if p.exists() or p.is_symlink()]
            if leftovers:
                raise RuntimeError('Some installation files remain; resolve permissions and rerun uninstall.')
        linspace_log('OK', 'Preview complete; no changes made.' if dry_run else f'{self.name} removed; only conversation history retained.')
        linspace_log('INFO', 'Shell startup files and project directories are untouched. Open a new terminal to clear cached command paths.')
        linspace_log('INFO', 'Also clear API tokens exported in your shell; a child script cannot change the parent environment.')


def main():
    parser = argparse.ArgumentParser(description='Stop and uninstall the CLI from recognized sources; keep only conversation history.')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--bin', action='append', default=[], help='Additional absolute executable path outside PATH')
    args = parser.parse_args()
    with client_lock(CLIENT, args.dry_run):
        Client(CLIENT).discover(args.bin).uninstall(args.dry_run)
