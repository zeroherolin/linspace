#!/usr/bin/env python3
"""Check HTTPS routes without writing or clearing stash channels."""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path


def probe(domain, path, method='HEAD', local=False, scheme='https'):
    with tempfile.TemporaryDirectory(prefix='linspace-http-') as temporary:
        headers = Path(temporary) / 'headers'
        command = ['curl', '-q', '-sS', '--globoff', '--noproxy', '*', '--proxy', '', '--connect-timeout', '5', '--max-time', '20',
                   '-D', str(headers), '-o', '/dev/null', '-w', '%{http_code}']
        if local:
            command += ['--resolve', f'{domain}:443:127.0.0.1', '--resolve', f'{domain}:80:127.0.0.1']
        if method == 'HEAD':
            command += ['--head']
        else:
            command += ['-X', method, '-H', 'Content-Length: 0']
        result = subprocess.run(command + [f'{scheme}://{domain}{path}'], text=True, capture_output=True)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or f'curl exited {result.returncode}')
        fields = {}
        for line in headers.read_text().splitlines():
            if ':' in line:
                name, value = line.split(':', 1)
                fields[name.lower()] = value.strip()
        return int(result.stdout), fields


def verify(meta, local=False, quiet=False):
    domain = meta['domain']
    paths = ['ssh/' + meta.get('ssh_public_key_name', 'key.pub')] if meta['ssh_enabled'] else []
    paths += ['mihomo/install', 'mihomo/sub', 'mihomo/restart', 'claude/config', 'codex/config', 'codex/models_1m', 'codex/auth', 'stash/upload', 'stash/clear']
    paths += [f'stash/upload{n}' for n in range(8)]
    paths += ['stash/keys', 'stash/challenge']
    checks = [('/', 200, 'text/html', 'no-store')]
    checks += [('/' + p, 200, 'text/plain', 'no-store') for p in paths]
    checks.append((f'/mihomo/assets/geoip-{meta["geoip_sha256"]}.dat', 200, 'application/octet-stream', 'immutable'))
    for path, expected, media, cache in checks:
        status, headers = probe(domain, path, local=local)
        if status != expected or not headers.get('content-type', '').startswith(media) or cache not in headers.get('cache-control', '') or headers.get('x-content-type-options') != 'nosniff':
            raise RuntimeError(f'{path}: unexpected status or headers (HTTP {status})')
        if not quiet:
            print(f'OK {path}: {status}')
    for path, expected, method in [('/not-published', 404, 'HEAD'), ('/stash/clear', 401, 'POST'), ('/stash/download0', 401, 'PUT')]:
        status, _ = probe(domain, path, method, local)
        if status != expected:
            raise RuntimeError(f'{method} {path}: expected {expected}, got {status}')
    for path, scheme, expected, destination in [('/', 'http', 308, f'https://{domain}/'), ('/claude/install', 'https', 302, 'https://claude.ai/install.sh'), ('/codex/install', 'https', 302, 'https://chatgpt.com/codex/install.sh')]:
        status, headers = probe(domain, path, local=local, scheme=scheme)
        if status != expected or headers.get('location') != destination:
            raise RuntimeError(f'{scheme} {path}: unexpected redirect')
    print(f'HTTPS verification passed for {domain}' + (' via loopback' if local else '') + '; stash contents unchanged.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--local', action='store_true')
    args = parser.parse_args()
    verify(json.loads((args.release / 'release.json').read_text()), args.local)


if __name__ == '__main__':
    main()
