import argparse
import copy
import re
import fcntl
import hashlib
import json
import os
import pwd
from pathlib import Path
import shutil
import stat
import signal
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import yaml

ROOT = Path('/var/lib/mihomo')
CONFIG = Path('/etc/mihomo/config.yaml')
SOCKET = Path('/run/mihomo/control.sock')
BIN = Path('/usr/local/bin/mihomo')
PROCESS = Path('/usr/local/lib/linspace-mihomo/process.py')
MARKER = Path('/usr/local/lib/linspace-mihomo/managed')
LOCK = Path('/run/lock/linspace-mihomo.lock')
TEMPLATE = Path('/usr/local/lib/linspace-mihomo/baseline.yaml')
GEO_SHA = '@@GEO_SHA@@'
GROUP = 'PROXY'
AUTO = 'AUTO'
CHECK_URL = 'https://www.google.com'
CHECK_STATUS = 200
CHECK_TIMEOUT_MS = 5000
PROXY_PORT = 7890
MAX_SIZE = 20 * 1024 * 1024
def targets():
    return {'config.yaml': CONFIG, 'proxies.yaml': ROOT / 'proxies.yaml', 'cache.db': ROOT / 'cache.db'}


def fail(message):
    raise RuntimeError(message)


def control(action, check=True):
    return subprocess.run(['/usr/bin/python3', str(PROCESS), action], check=check,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def active():
    return control('is-active', check=False).returncode == 0


def api(path, method='GET', body=None, *, sock=None, timeout=5):
    command = ['curl', '-q', '-fsS', '--noproxy', '*', '--proxy', '',
               '--unix-socket', str(SOCKET if sock is None else sock), '--connect-timeout', '3', '--max-time', str(timeout),
               '-X', method, '-H', 'Content-Type: application/json']
    if body is not None:
        command += ['--data-binary', '@-']
    command += ['http://localhost' + path]
    result = subprocess.run(command, input=None if body is None else json.dumps(body),
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return json.loads(result.stdout) if result.stdout else None


def owns_socket(pid, path):
    try:
        sockets = {os.readlink(p) for p in Path(f'/proc/{pid}/fd').iterdir()}
        return any(len(f) > 7 and f[7] == str(path) and f'socket:[{f[6]}]' in sockets
                   for f in (line.split() for line in Path(f'/proc/{pid}/net/unix').read_text().splitlines()[1:]))
    except OSError:
        return False


def owned_ports(pid):
    try:
        sockets = {os.readlink(p) for p in Path(f'/proc/{pid}/fd').iterdir()}
        found = set()
        for protocol in ('tcp', 'tcp6', 'udp', 'udp6'):
            for row in Path(f'/proc/{pid}/net/{protocol}').read_text().splitlines()[1:]:
                fields = row.split()
                address, port = fields[1].split(':')
                if f'socket:[{fields[9]}]' not in sockets or address.upper() != '0100007F':
                    continue
                if protocol.startswith('tcp') and fields[3] != '0A':
                    continue
                found.add((protocol[:3], int(port, 16)))
        return {('tcp', PROXY_PORT), ('udp', PROXY_PORT)} <= found and owns_socket(pid, SOCKET)
    except (OSError, ValueError):
        return False


def wait_ready():
    for _ in range(60):
        if active():
            pid = int(control('pid').stdout.strip() or 0)
            if pid > 0 and owned_ports(pid):
                try:
                    if api('/version')['version'] == 'v1.19.27':
                        return
                except Exception:
                    pass
        time.sleep(.5)
    fail('mihomo is not ready, or the service does not own the expected loopback and Unix listeners.')


def open_regular(source):
    try:
        fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        fail('Cannot safely read a managed file. Check symbolic links and permissions.')
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        os.close(fd)
        fail('Managed files must be regular files without symbolic or hard links.')
    return os.fdopen(fd, 'rb')


def private_snapshot(source, target):
    with open_regular(source) as inp, target.open('xb') as out:
        shutil.copyfileobj(inp, out)
        out.flush()
        os.fsync(out.fileno())
    os.chmod(target, 0o600)


def atomic_copy(source, target, mode=0o600):
    fd, name = tempfile.mkstemp(prefix='.new-', dir=target.parent)
    try:
        with os.fdopen(fd, 'wb') as out, open_regular(source) as inp:
            shutil.copyfileobj(inp, out)
            out.flush()
            os.fsync(out.fileno())
        account = pwd.getpwnam('mihomo')
        os.chown(name, 0 if target == CONFIG else account.pw_uid, account.pw_gid)
        os.chmod(name, 0o640 if target == CONFIG else mode)
        os.replace(name, target)
    finally:
        Path(name).unlink(missing_ok=True)


class UniqueLoader(yaml.SafeLoader):
    yaml_implicit_resolvers = copy.deepcopy(yaml.SafeLoader.yaml_implicit_resolvers)


# Match yaml.v3 boolean resolution: plain on/off/yes/no remain strings.
for initial, resolvers in UniqueLoader.yaml_implicit_resolvers.items():
    UniqueLoader.yaml_implicit_resolvers[initial] = [
        (tag, pattern) for tag, pattern in resolvers if tag != 'tag:yaml.org,2002:bool']
UniqueLoader.add_implicit_resolver('tag:yaml.org,2002:bool',
    re.compile(r'^(?:true|True|TRUE|false|False|FALSE)$'), list('tTfF'))


def unique_mapping(loader, node, deep=False):
    loader.flatten_mapping(node)
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            fail('Duplicate YAML keys are not allowed.')
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def normalize(source, target):
    if not 0 < source.stat().st_size <= MAX_SIZE:
        fail('The subscription file is empty or exceeds 20 MiB.')
    try:
        loader = UniqueLoader(source.read_text())
        try:
            document = loader.get_single_node()
            raw = loader.construct_document(document) if document is not None else None
        finally:
            loader.dispose()
        nodes = raw.get('proxies') if isinstance(raw, dict) else None
        if not isinstance(nodes, list) or not nodes:
            fail('Provide Clash/mihomo YAML with a nonempty proxies array. Provider-only configurations are not supported.')
        names = []
        reserved = {GROUP, AUTO, 'GLOBAL', 'DIRECT', 'REJECT', 'REJECT-DROP', 'PASS', 'COMPATIBLE', 'DNS'}
        for node in nodes:
            if not isinstance(node, dict):
                fail('Each proxy must be a mapping.')
            name, kind = node.get('name'), node.get('type')
            if node.get('skip-cert-verify') not in (None, False):
                fail('A proxy disables TLS certificate verification. Obtain a configuration with valid certificate verification.')
            if not isinstance(name, str) or not name or any(ord(c) < 32 or ord(c) == 127 for c in name):
                fail('Proxy names must be nonempty and contain no control characters.')
            if name in reserved or name in names:
                fail('Proxy names must be unique and must not conflict with managed groups or built-in policies.')
            if not isinstance(kind, str) or kind.lower() in {'direct', 'reject', 'rejectdrop', 'pass', 'compatible', 'dns'}:
                fail('The proxies array must contain actual proxy nodes.')
            names.append(name)
        for node in nodes:
            if node.get('dialer-proxy') and node['dialer-proxy'] not in names + ['DIRECT']:
                fail('A proxy depends on an external subscription group. Use self-contained proxy definitions.')
        # Preserve all node fields and their order; import no global subscription settings.
        node_tree = next(value for key, value in document.value if key.value == 'proxies')
        provider = yaml.MappingNode('tag:yaml.org,2002:map', [
            (yaml.ScalarNode('tag:yaml.org,2002:str', 'proxies'), node_tree)])
        # Serialize the original scalar nodes to retain credentials and other scalar values.
        target.write_text(yaml.serialize(provider, Dumper=yaml.SafeDumper, allow_unicode=True))
        return names
    except RuntimeError:
        raise
    except Exception:
        fail('Cannot safely parse the subscription YAML. Source contents and credentials are not printed.')


def download(url, target, via_proxy=False):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        fail('The subscription address must be an HTTPS URL without userinfo.')
    if any(ord(c) < 32 or ord(c) == 127 for c in url):
        fail('The subscription address must not contain control characters.')
    # Feed URL through stdin so curl argv/logs do not contain the subscription token.
    config = 'url = ' + json.dumps(url, ensure_ascii=False) + '\n'
    proxy = f'http://127.0.0.1:{PROXY_PORT}' if via_proxy else ''
    result = subprocess.run([
        'curl', '-q', '-fsSL', '--globoff', '--proto', '=https', '--proto-redir', '=https',
        '--connect-timeout', '10', '--max-time', '60', '--max-filesize', str(MAX_SIZE),
        '--proxy', proxy, '--noproxy', '' if via_proxy else '*',
        '--user-agent', 'clash.meta/v1.19.27', '--config', '-', '-o', str(target)],
        input=config, text=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return result.returncode == 0


def probe_node(name, sock=None):
    # Probe the named outbound directly. Routing rules cannot bypass this check.
    query = urllib.parse.urlencode({'url': CHECK_URL, 'timeout': CHECK_TIMEOUT_MS, 'expected': CHECK_STATUS})
    try:
        result = api('/proxies/' + urllib.parse.quote(name, safe='') + '/delay?' + query,
                     sock=sock, timeout=CHECK_TIMEOUT_MS / 1000 + 3)
        if not isinstance(result, dict) or not isinstance(result.get('delay'), (int, float)) or result['delay'] <= 0:
            return False
        # v1.19.27 can return a delay for an unexpected status; consult the URL-specific result too.
        detail = api('/proxies/' + urllib.parse.quote(name, safe=''), sock=sock)
        state = detail.get('extra', {}).get(CHECK_URL, {})
        history = state.get('history', [])
        return state.get('alive') is True and bool(history) and history[-1].get('delay', 0) > 0
    except (subprocess.SubprocessError, ValueError, OSError):
        return False


def select_first_available(stage, names):
    sock = stage / 'control.sock'
    account = pwd.getpwnam('mihomo')
    process = None
    try:
        with (stage.parent / 'probe.log').open('w') as log:
            process = subprocess.Popen([
                'setpriv', f'--reuid={account.pw_uid}', f'--regid={account.pw_gid}',
                '--clear-groups', '--inh-caps=-all', '--bounding-set=-all', '--no-new-privs',
                str(BIN), '-d', str(stage)], cwd=stage, stdout=log, stderr=log)
            for _ in range(60):
                if process.poll() is not None:
                    fail('The trial process failed to start. The existing service was not changed.')
                if owns_socket(process.pid, sock):
                    try:
                        group = api('/proxies/' + urllib.parse.quote(GROUP, safe=''), sock=sock)
                        if group.get('all') == names:
                            break
                    except (subprocess.SubprocessError, ValueError, OSError):
                        pass
                time.sleep(.2)
            else:
                fail('The trial API is not ready. The existing service was not changed.')
            for index, name in enumerate(names, 1):
                print(f'Checking proxy {index}/{len(names)}: {name}', flush=True)
                if probe_node(name, sock):
                    api('/proxies/' + urllib.parse.quote(GROUP, safe=''), 'PUT', {'name': name}, sock=sock)
                    return name
            fail('No proxy passed the HTTPS check. The existing configuration was not changed.')
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def verify_proxy_request():
    # Confirm the selected group really reaches HTTPS through its node, then test the live listener.
    if not probe_node(GROUP):
        fail('The selected proxy failed the live HTTPS check.')
    result = subprocess.run([
        'curl', '-q', '-fsS', '--globoff', '--proto', '=https',
        '--connect-timeout', '5', '--max-time', '10', '--noproxy', '',
        '--proxy', f'http://127.0.0.1:{PROXY_PORT}',
        '--url', CHECK_URL, '-o', os.devnull, '-w', '%{http_code}'],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if result.returncode != 0 or result.stdout != str(CHECK_STATUS):
        fail('The live proxy listener failed the HTTPS check.')


def verify_runtime(names, selected):
    cfg = api('/configs')
    expected = {'mixed-port': PROXY_PORT, 'allow-lan': False, 'bind-address': '127.0.0.1',
                'mode': 'rule', 'log-level': 'info', 'ipv6': True, 'geodata-mode': True,
                'geo-auto-update': False, 'port': 0, 'socks-port': 0, 'redir-port': 0, 'tproxy-port': 0}
    if any(cfg.get(k) != v for k, v in expected.items()) or cfg.get('authentication') or cfg['tun']['enable']:
        fail('Runtime global settings differ from the managed policy.')
    rules = [(r['type'], r['payload'].upper(), r['proxy']) for r in api('/rules')['rules']]
    if rules != [('GeoIP', 'CN', 'DIRECT'), ('Match', '', GROUP)]:
        fail('Runtime routing rules differ from the managed policy.')
    groups = api('/proxies')['proxies']
    if groups[GROUP]['type'] != 'Selector' or groups[AUTO]['type'] != 'URLTest':
        fail('Runtime proxy group types differ from the managed policy.')
    if groups[GROUP]['all'] != names or groups[AUTO]['all'] != names or groups[GROUP]['now'] != selected:
        fail('Runtime proxy order or selection does not match the expected state.')
    provider = api('/providers/proxies/my-sub')
    if provider['vehicleType'] != 'File' or provider['testUrl'] != 'http://www.gstatic.com/generate_204' or provider['expectedStatus'] != '*':
        fail('Runtime provider settings differ from the managed policy.')


def main(argv=None):
    parser = argparse.ArgumentParser(prog='sub', description='Import a subscription and select the first proxy in order that passes the HTTPS check.')
    parser.add_argument('source', help='HTTPS subscription URL, or path to a local Clash/mihomo YAML file')
    args = parser.parse_args(argv)
    if os.geteuid() != 0:
        fail('Run this script as root.')
    if not MARKER.is_file() or MARKER.read_text().strip() != 'linspace-mihomo-background-v1':
        fail('Run the managed install script first.')
    for key in list(os.environ):
        if key.lower() in {'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy'} or key.startswith('CLASH_') or key == 'SAFE_PATHS':
            os.environ.pop(key, None)
    os.umask(0o077)
    with LOCK.open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fail('Another mihomo installation or update is running.')
        if ROOT.is_symlink() or CONFIG.parent.is_symlink() or any(p.is_symlink() for p in list(targets().values()) + [ROOT / 'GeoIP.dat']):
            fail('The data directory and managed files must not be symbolic links.')
        if hashlib.sha256((ROOT / 'GeoIP.dat').read_bytes()).hexdigest() != GEO_SHA:
            fail('GeoIP.dat does not match the pinned snapshot. Run install again.')
        template = yaml.safe_load(TEMPLATE.read_text())
        if [g.get('name') for g in template.get('proxy-groups', [])] != [GROUP, AUTO]:
            fail('Run the current install script before using this version of sub.')
        was_active = active()
        work = Path(tempfile.mkdtemp(prefix='.sub-', dir=ROOT))
        changed = False
        keep_work = False
        try:
            raw = work / 'subscription.yaml'
            if '://' not in args.source:
                source = Path(args.source)
                if not source.is_file():
                    fail(f'{source} is not a file. Pass an HTTPS subscription URL or a local YAML file path.')
                if not 0 < source.stat().st_size <= MAX_SIZE:
                    fail('The proxy file is empty or too large.')
                shutil.copyfile(source, raw)
            else:
                url = args.source
                if not download(url, raw):
                    if not was_active:
                        fail('Direct download failed and no existing proxy is running. The current configuration was not changed.')
                    wait_ready()
                    if not download(url, raw, via_proxy=True):
                        fail('Download through the existing proxy also failed. The current configuration was not changed.')
                    print('Downloaded using the existing service routing and selected proxy.')
            names = normalize(raw, work / 'proxies.yaml')
            shutil.copyfile(TEMPLATE, work / 'config.yaml')
            stage = work / 'data'
            stage.mkdir()
            for name in ('config.yaml', 'proxies.yaml'):
                shutil.copyfile(work / name, stage / name)
            shutil.copyfile(ROOT / 'GeoIP.dat', stage / 'GeoIP.dat')
            trial_config = yaml.safe_load((stage / 'config.yaml').read_text())
            trial_config['mixed-port'] = 0
            trial_config['external-controller-unix'] = str(stage / 'control.sock')
            (stage / 'config.yaml').write_text(yaml.safe_dump(trial_config, allow_unicode=True, sort_keys=False))
            account = pwd.getpwnam('mihomo')
            os.chown(work, 0, account.pw_gid)
            os.chmod(work, 0o710)
            for path in [stage, *stage.iterdir()]:
                os.chown(path, account.pw_uid, account.pw_gid)
            with (work / 'check.log').open('w') as log:
                checked = subprocess.run(['runuser', '-u', 'mihomo', '--', str(BIN), '-t', '-d', str(stage)], stdout=log, stderr=log, timeout=120)
            if checked.returncode:
                fail('mihomo configuration validation failed. Check the subscription format and proxy settings.')
            selected = select_first_available(stage, names)
            if not (stage / 'cache.db').is_file():
                fail('No selection cache was generated. The current configuration was not changed.')
            private_snapshot(stage / 'cache.db', work / 'selection.db')
            backup = work / 'backup'
            backup.mkdir()
            changed = True
            control('stop')
            # Snapshot the cache only after the process has closed it.
            for name, p in targets().items():
                if p.exists():
                    private_snapshot(p, backup / name)
            (backup / 'snapshot-complete').touch()
            atomic_copy(work / 'proxies.yaml', ROOT / 'proxies.yaml')
            atomic_copy(work / 'config.yaml', CONFIG)
            atomic_copy(work / 'selection.db', ROOT / 'cache.db')
            control('start')
            wait_ready()
            verify_runtime(names, selected)
            verify_proxy_request()
            # Retain the complete previous configuration/cache as a private backup.
            archive = ROOT / ('backup-' + str(time.time_ns()))
            os.replace(backup, archive)
            changed = False
            print(f'Updated successfully: {len(names)} proxies; {GROUP} -> {selected}')
            print(f'Previous configuration: {archive}; proxy: 127.0.0.1:7890; control socket: {SOCKET}.')
        except BaseException:
            if changed:
                try:
                    control('stop')
                    backup = work / 'backup'
                    if (backup / 'snapshot-complete').exists():
                        for name, target in targets().items():
                            saved = backup / name
                            if saved.exists():
                                atomic_copy(saved, target, saved.stat().st_mode & 0o777)
                            else:
                                target.unlink(missing_ok=True)
                    if was_active:
                        control('start')
                        wait_ready()
                    print('Update failed. Previous files and service state were restored.', file=sys.stderr)
                except BaseException:
                    keep_work = True
                    print(f'Rollback is incomplete. Private backups are retained at {work}; restore them manually.', file=sys.stderr)
            raise
        finally:
            if not keep_work:
                shutil.rmtree(work)


if __name__ == '__main__':
    def interrupted(signum, frame):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, interrupted)
    try:
        main()
    except KeyboardInterrupt:
        print('Operation interrupted.', file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        # Do not echo URLs, node credentials, or raw engine logs on errors.
        print('Error: ' + (str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__), file=sys.stderr)
        sys.exit(1)
