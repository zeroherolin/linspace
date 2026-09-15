#!/usr/bin/env python3
"""Check HTTPS routes without writing or clearing stash channels."""
import sys
# A verified release must not gain generated Python cache files when executed.
sys.dont_write_bytecode = True
from linspace_console import linspace_log
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
            command += ['-X', method]
            if method in ('PUT', 'POST'):
                command += ['-H', 'Content-Length: 0']
            if method == 'GET':
                command += ['--max-filesize', str(1024 * 1024)]
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
    paths += ['mihomo/install', 'mihomo/sub', 'mihomo/restart', 'claude/install', 'claude/config', 'codex/install', 'codex/config', 'codex/models_1m', 'codex/auth', 'stash/upload', 'stash/clear']
    paths += [f'{client}/uninstall' for client in ('mihomo', 'claude', 'codex')]
    paths += [f'stash/upload{n}' for n in range(8)]
    paths += ['stash/keys', 'stash/challenge']
    checks = [('/', 200, 'text/html', 'no-store')]
    checks += [('/help', 200, 'text/html', 'no-store')]
    checks += [('/' + p, 200, 'text/plain', 'no-store') for p in paths]
    for path, expected, media, cache in checks:
        status, headers = probe(domain, path, local=local)
        if status != expected or not headers.get('content-type', '').startswith(media) or cache not in headers.get('cache-control', '') or headers.get('x-content-type-options') != 'nosniff':
            raise RuntimeError(f'{path}: unexpected status or headers (HTTP {status})')
        if not quiet:
            linspace_log('OK', f'{path} [{status}]')
    # Missing channels return 404; empty uploaded files return 200. Check both
    # methods and the alias without uploading fixtures or retaining public text.
    for path in ['/stash/download', *[f'/stash/download{n}' for n in range(8)]]:
        for method in ('HEAD', 'GET'):
            status, headers = probe(domain, path, method, local)
            if status not in (200, 404) or not headers.get('content-type', '').startswith('text/plain') or 'no-store' not in headers.get('cache-control', '') or headers.get('x-content-type-options') != 'nosniff':
                raise RuntimeError(f'{method} {path}: unexpected status or headers (HTTP {status})')
            if not quiet:
                linspace_log('OK', f'{method} {path} [{status}]')
    for path, expected, method in [('/not-published', 404, 'HEAD'), ('/stash/clear', 401, 'POST'), ('/stash/download0', 401, 'PUT')]:
        status, _ = probe(domain, path, method, local)
        if status != expected:
            raise RuntimeError(f'{method} {path}: expected {expected}, got {status}')
    for path, scheme, expected, destination in [('/', 'http', 308, f'https://{domain}/')]:
        status, headers = probe(domain, path, local=local, scheme=scheme)
        if status != expected or headers.get('location') != destination:
            raise RuntimeError(f'{scheme} {path}: unexpected redirect')
    # Alias hostnames only redirect; the path and query must survive so shared links keep working.
    for alias in meta.get('alias_domains', []):
        for path, scheme in [('/', 'https'), ('/help', 'https'), ('/stash/download0?x=1', 'https'), ('/', 'http')]:
            status, headers = probe(alias, path, local=local, scheme=scheme)
            wanted = f'https://{domain}{path}' if scheme == 'https' else f'https://{alias}/'
            if status != 308 or headers.get('location') != wanted:
                raise RuntimeError(f'{scheme}://{alias}{path}: expected a 308 redirect to {wanted} (HTTP {status})')
            if not quiet:
                linspace_log('OK', f'{scheme}://{alias}{path} -> {wanted}')
    linspace_log('OK', f'HTTPS verification passed for {domain}' + (' via loopback' if local else '') + '; stash contents unchanged.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--local', action='store_true')
    args = parser.parse_args()
    verify(json.loads((args.release / 'release.json').read_text()), args.local)


if __name__ == '__main__':
    main()
