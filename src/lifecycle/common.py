"""Process and filesystem operations shared by the standalone uninstallers."""
from linspace_console import linspace_log
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from contextlib import contextmanager


@contextmanager
def client_lock(name, dry_run=False):
    if name not in {'claude', 'codex'} or not Path.home().is_absolute() or Path.home() == Path('/'):
        raise ValueError('Use a valid client name and an absolute account home directory.')
    if dry_run:
        yield
        return
    root = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state'))
    if not root.is_absolute():
        raise ValueError('Use an absolute XDG_STATE_HOME.')
    lock = dedicated(root / 'linspace/locks' / name)
    lock.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            lock.mkdir(mode=0o700)
            break
        except FileExistsError:
            if lock.is_symlink() or not (lock / 'pid').is_file():
                raise RuntimeError('Another client operation is starting; retry shortly.') from None
            owner = (lock / 'pid').read_text().strip()
            if not owner.isdigit():
                raise RuntimeError('Invalid client operation lock; inspect it before retrying.')
            try:
                os.kill(int(owner), 0)
            except ProcessLookupError:
                (lock / 'pid').unlink()
                lock.rmdir()
            else:
                raise RuntimeError('Another install or uninstall is running; retry after it finishes.') from None
    else:
        raise RuntimeError('Could not acquire the client operation lock.')
    try:
        (lock / 'pid').write_text(str(os.getpid()) + '\n')
        yield
    finally:
        (lock / 'pid').unlink(missing_ok=True)
        lock.rmdir()
        for parent in (lock.parent, lock.parent.parent):
            try:
                parent.rmdir()
            except OSError:
                pass


def run(args, check=True, timeout=60, env=None):
    result = subprocess.run([str(x) for x in args], text=True, capture_output=True,
                            stdin=subprocess.DEVNULL, timeout=timeout, env=env)
    if check and result.returncode:
        # Package-manager diagnostics may contain registry credentials. Identify the
        # failed operation, without copying arbitrary subprocess output.
        raise RuntimeError(f'{Path(args[0]).name} {args[1]} failed (exit {result.returncode}); resolve the package-manager error and retry.')
    return result


def dedicated(path, home=None):
    """Reject broad roots and symlinked parent directories before recursive removal."""
    path = Path(os.path.abspath(path))
    home = Path.home() if home is None else home
    protected = {Path('/'), Path('/usr'), Path('/usr/local'), Path('/opt'), Path('/var'),
                 Path('/etc'), Path('/tmp'), Path('/home'), Path('/Users'), home,
                 home / '.local', home / '.local/share', home / '.config', home / '.cache'}
    if path in protected or len(path.parts) < 3:
        raise ValueError(f'Refusing a broad data path: {path}')
    for parent in path.parents:
        if parent.is_symlink():
            aliases = {'/bin': '/usr/bin', '/sbin': '/usr/sbin', '/lib': '/usr/lib',
                       '/lib64': '/usr/lib64', '/var': '/private/var', '/tmp': '/private/tmp'}
            if aliases.get(str(parent)) != str(parent.resolve()):
                raise ValueError(f'Refusing a symlinked parent directory: {parent}')
    return path


def remove(path, dry_run=False):
    path = dedicated(path)
    if not path.exists() and not path.is_symlink():
        return
    linspace_log('INFO', f'Remove {path}')
    if dry_run:
        return
    if path.is_symlink() or not path.is_dir():
        path.unlink()
    else:
        shutil.rmtree(path)


def within(path, root):
    try:
        Path(path).relative_to(root)
        return True
    except ValueError:
        return False


def process_table():
    """Read process identity without logging command arguments or credentials."""
    table = {}
    if sys.platform.startswith('linux'):
        for directory in Path('/proc').iterdir():
            if not directory.name.isdigit():
                continue
            try:
                fields = (directory / 'stat').read_text().rsplit(')', 1)[1].split()
                if fields[0] == 'Z':
                    continue
                arguments = (directory / 'cmdline').read_bytes().split(b'\0')
                args = [x.decode(errors='replace') for x in arguments if x]
                try:
                    executable = os.readlink(directory / 'exe').removesuffix(' (deleted)')
                except PermissionError:
                    executable = args[0] if args else ''
                table[int(directory.name)] = (int(fields[1]), fields[19], executable, args,
                    directory.stat().st_uid)
            except (OSError, ValueError, IndexError):
                continue
    else:
        import ctypes
        library = ctypes.CDLL('/usr/lib/libproc.dylib')
        library.proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
        library.proc_pidpath.restype = ctypes.c_int
        result = run(['ps', '-axo', 'pid=,ppid=,uid=,lstart=,command='])
        for line in result.stdout.splitlines():
            fields = line.split(None, 8)
            if len(fields) != 9:
                continue
            try:
                pid, parent, uid = map(int, fields[:3])
                args = shlex.split(fields[8])
                buffer = ctypes.create_string_buffer(4096)
                size = library.proc_pidpath(pid, buffer, len(buffer))
                executable = buffer.value.decode(errors='replace') if size > 0 else args[0] if args else ''
                table[pid] = (parent, ' '.join(fields[3:8]), executable, args, uid)
            except ValueError:
                continue
    return table


def matching_processes(executables, roots=(), all_users=False):
    table = process_table()
    exclude = {os.getpid()}
    current = os.getpid()
    while current in table and table[current][0] > 1:
        current = table[current][0]
        exclude.add(current)
    matches = set()
    for pid, (parent, started, executable, args, uid) in table.items():
        if pid in exclude or not all_users and uid != os.getuid():
            continue
        # Only the executable and interpreter's script argument identify a client.
        candidates = [executable]
        if (Path(executable).name in {'node', 'nodejs', 'bash', 'sh'} or Path(executable).name.startswith('python')) and len(args) > 1:
            candidates.append(args[1])
        if any(value in executables or any(within(value, root) for root in roots) for value in candidates):
            matches.add(pid)
    # Include helper processes, while never signaling our own ancestors.
    for _ in range(len(table)):
        added = {pid for pid, item in table.items() if item[0] in matches and pid not in exclude}
        if added <= matches:
            break
        matches |= added
    return {pid: table[pid][1] for pid in matches}


def stop_processes(executables, roots=(), dry_run=False, all_users=False):
    targets = matching_processes(executables, roots, all_users)
    if not targets:
        return
    linspace_log('STEP', f'Stop {len(targets)} client process(es)')
    if dry_run:
        return
    for sig, wait in [(signal.SIGTERM, 8), (signal.SIGKILL, 3)]:
        table = process_table()
        for pid, started in targets.items():
            if pid in table and table[pid][1] == started:
                os.kill(pid, sig)
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            table = process_table()
            targets = {pid: started for pid, started in targets.items() if pid in table and table[pid][1] == started}
            if not targets:
                break
            time.sleep(.1)
        if not targets:
            break
    if targets or matching_processes(executables, roots, all_users):
        raise RuntimeError('A client process is still running or was restarted by a supervisor; stop its supervisor and retry.')


def package_owner(path):
    """Use the host package database, never guess ownership from a filename."""
    path = str(path)
    for manager, query in [('dpkg-query', ['-S', path]), ('rpm', ['-qf', '--qf', '%{NAME}', path]),
                           ('pacman', ['-Qqo', path]), ('apk', ['info', '--who-owns', path])]:
        tool = shutil.which(manager)
        if not tool:
            continue
        result = run([tool, *query], check=False)
        if result.returncode:
            continue
        if manager == 'dpkg-query':
            names = [line.rsplit(': ', 1)[0] for line in result.stdout.splitlines() if ': ' in line]
        elif manager == 'apk':
            match = re.search(r' is owned by (.+)-\d[^\s]*$', result.stdout.strip())
            names = [match[1]] if match else []
        else:
            names = result.stdout.splitlines()
        if names:
            return manager, names
    return None


def remove_packages(owner, dry_run=False):
    manager, names = owner
    if any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.+:_@-]*', name) for name in names):
        raise ValueError('Invalid package name returned by the package database')
    commands = {'dpkg-query': ['dpkg', '--purge'], 'rpm': ['rpm', '-e'],
                'pacman': ['pacman', '-R', '--noconfirm'], 'apk': ['apk', 'del']}
    linspace_log('INFO', f'Uninstall {", ".join(names)} with {manager}')
    if not dry_run:
        if os.geteuid() != 0:
            raise RuntimeError(f'System package removal needs administrator access: {" ".join(commands[manager] + names)}')
        run(commands[manager] + names, timeout=180)


def clear_history_except(directory, allowed, dry_run=False):
    directory = dedicated(directory)
    if directory.is_symlink():
        raise ValueError(f'Refusing a symlinked state directory: {directory}')
    if not directory.exists():
        return
    for item in directory.iterdir():
        if allowed(item.name):
            linspace_log('INFO', f'Keep conversation history: {item}')
        else:
            remove(item, dry_run)
    if not dry_run and not any(directory.iterdir()):
        directory.rmdir()
