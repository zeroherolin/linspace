from linspace_console import linspace_log
import argparse
import fcntl
import json
import socket
import http.client
import os
from pathlib import Path
import pwd
import signal
import subprocess
import sys
import time

LIB = Path('/usr/local/lib/linspace-mihomo')
CONTROL = Path('/run/linspace-mihomo')
RECORD = CONTROL / 'process.json'
API_RUN = Path('/run/mihomo')
LOG_DIR = Path('/var/log/mihomo')
BIN = Path('/usr/local/bin/mihomo')
RUNNER = LIB / 'run-mihomo.sh'


def process_sockets(pid):
    # Match the daemon's filesystem credentials when /proc inspection is restricted.
    # This needs no ptrace capability and keeps exact socket/PID verification.
    uid, gid = os.geteuid(), os.getegid()
    account = pwd.getpwnam('mihomo')
    try:
        if uid == 0:
            os.setegid(account.pw_gid)
            os.seteuid(account.pw_uid)
        return {os.readlink(p) for p in Path(f'/proc/{pid}/fd').iterdir()}
    finally:
        if uid == 0:
            os.seteuid(uid)
            os.setegid(gid)


def process_identity(pid):
    try:
        text = Path(f'/proc/{pid}/stat').read_text()
        fields = text[text.rfind(')') + 2:].split()
        if fields[0] == 'Z':
            return None
        return fields[19]
    except (OSError, IndexError):
        return None


def running_pid():
    try:
        record = json.loads(RECORD.read_text())
        pid = int(record['pid'])
        if pid > 1 and process_identity(pid) == record['start_time']:
            return pid
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return 0


def private_directory(path, uid, gid):
    if path.is_symlink():
        raise RuntimeError('Runtime directories must not be symbolic links.')
    path.mkdir(parents=True, exist_ok=True)
    os.chown(path, uid, gid)
    os.chmod(path, 0o700)


def prepare_runtime():
    account = pwd.getpwnam('mihomo')
    private_directory(CONTROL, 0, 0)
    private_directory(LOG_DIR, 0, 0)
    private_directory(API_RUN, account.pw_uid, account.pw_gid)


def command():
    account = pwd.getpwnam('mihomo')
    return ['/usr/bin/setpriv', f'--reuid={account.pw_uid}', f'--regid={account.pw_gid}',
            '--clear-groups', '--inh-caps=-all', '--bounding-set=-all', '--no-new-privs', str(RUNNER)]


def stop_background():
    pid = running_pid()
    if pid:
        if os.getpgid(pid) != pid:
            raise RuntimeError('Unexpected process group; refusing to stop it.')
        os.killpg(pid, signal.SIGTERM)
        for _ in range(100):
            if not running_pid():
                break
            time.sleep(.1)
        if running_pid() == pid:
            os.killpg(pid, signal.SIGKILL)
            for _ in range(30):
                if not running_pid():
                    break
                time.sleep(.1)
            if running_pid():
                raise RuntimeError('The managed process did not stop.')
    RECORD.unlink(missing_ok=True)


def start_background():
    if running_pid():
        return
    if not Path('/etc/mihomo/config.yaml').is_file():
        raise RuntimeError('Import a subscription before starting mihomo.')
    logfile = LOG_DIR / 'mihomo.log'
    if logfile.is_symlink():
        raise RuntimeError('The log file must not be a symbolic link.')
    # Bound retained logs at each start. Long-running installations should also
    # use their existing log rotation facility.
    if logfile.exists() and logfile.stat().st_size > 5 * 1024 * 1024:
        for index in range(2, 0, -1):
            previous = LOG_DIR / f'mihomo.log.{index}'
            if previous.exists():
                os.replace(previous, LOG_DIR / f'mihomo.log.{index + 1}')
        os.replace(logfile, LOG_DIR / 'mihomo.log.1')
    with logfile.open('ab') as output:
        os.chmod(logfile, 0o600)
        process = subprocess.Popen(['/usr/bin/nohup', *command()],
            stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
            cwd='/var/lib/mihomo', start_new_session=True, close_fds=True)
    identity = process_identity(process.pid)
    if identity is None:
        raise RuntimeError('The background process exited immediately. Check its log.')
    temporary = CONTROL / 'process.json.new'
    temporary.write_text(json.dumps({'pid': process.pid, 'start_time': identity}) + '\n')
    os.chmod(temporary, 0o600)
    os.replace(temporary, RECORD)
    time.sleep(.2)
    if process.poll() is not None:
        RECORD.unlink(missing_ok=True)
        raise RuntimeError('The background process failed to start. Check its log.')


class UnixConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(str(API_RUN / 'control.sock'))


def ready(pid):
    try:
        descriptors = process_sockets(pid)
        found = set()
        for protocol in ('tcp', 'tcp6', 'udp', 'udp6'):
            for line in Path(f'/proc/{pid}/net/{protocol}').read_text().splitlines()[1:]:
                fields = line.split()
                address, port = fields[1].split(':')
                if f'socket:[{fields[9]}]' in descriptors and address == '0100007F':
                    if not protocol.startswith('tcp') or fields[3] == '0A':
                        found.add((protocol[:3], int(port, 16)))
        if not {('tcp', 7890), ('udp', 7890)} <= found:
            return False
        own_socket = any(len(f) > 7 and f[7] == str(API_RUN / 'control.sock') and f'socket:[{f[6]}]' in descriptors
                         for f in (line.split() for line in Path(f'/proc/{pid}/net/unix').read_text().splitlines()[1:]))
        if not own_socket:
            return False
        connection = UnixConnection('localhost', timeout=2)
        try:
            connection.request('GET', '/version')
            response = connection.getresponse()
            return response.status == 200 and json.loads(response.read())['version'] == '@@MIHOMO_VERSION@@'
        finally:
            connection.close()
    except (OSError, ValueError, KeyError, http.client.HTTPException):
        return False


def wait_ready():
    for _ in range(60):
        pid = running_pid()
        if not pid:
            break
        if ready(pid):
            return pid
        time.sleep(.5)
    raise RuntimeError('mihomo is not ready. Check the log and port conflicts.')


def main():
    parser = argparse.ArgumentParser(description='Control the ordinary background mihomo process.')
    parser.add_argument('action', choices=['start', 'stop', 'restart', 'status', 'is-active', 'pid'])
    action = parser.parse_args().action
    if os.geteuid() != 0:
        raise RuntimeError('Run this command as root.')
    os.umask(0o077)
    for name in list(os.environ):
        if name.lower() in {'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy'} or name.startswith('CLASH_') or name == 'SAFE_PATHS':
            os.environ.pop(name, None)
    if (LIB / 'managed').read_text().strip() != 'linspace-mihomo-background-v1':
        raise RuntimeError('Run the current install script first.')
    if action in ('pid', 'status', 'is-active'):
        pid = running_pid()
        if action == 'pid':
            print(pid)
            return 0
        if action == 'status':
            linspace_log('OK' if pid else 'INFO', f'mihomo RUNNING (pid {pid})' if pid else 'mihomo STOPPED')
        return 0 if pid else 3
    prepare_runtime()
    with (CONTROL / 'control.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if action in ('start', 'restart') and not Path('/etc/mihomo/config.yaml').is_file():
            raise RuntimeError('Import a subscription before starting mihomo.')
        if action in ('stop', 'restart'):
            stop_background()
        if action in ('start', 'restart'):
            start_background()
            try:
                pid = wait_ready()
            except BaseException:
                stop_background()
                raise
            linspace_log('OK', f'mihomo started in background (pid {pid}).')
            linspace_log('INFO', 'Proxy: 127.0.0.1:7890; log: /var/log/mihomo/mihomo.log')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        linspace_log('ERROR', exc)
        sys.exit(1)
