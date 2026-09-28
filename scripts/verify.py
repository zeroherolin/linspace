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

# Public client routes in feature order; the Caddy allowlist and the URL listing follow it.
CLIENT_ROUTES = ('mihomo/install', 'mihomo/sub', 'mihomo/restart', 'mihomo/uninstall',
                 'tmux/install', 'tmux/config', 'tmux/uninstall',
                 'claude/install', 'claude/config', 'claude/uninstall',
                 'codex/install', 'codex/config', 'codex/models_1m', 'codex/auth', 'codex/uninstall')
# A page name used only for read-only checks; the name may exist, so its page is accepted either way.
PROBE_PAGE = 'linspace-verify'


def probe(domain, path, method='HEAD', local=False, scheme='https', output='/dev/null'):
    with tempfile.TemporaryDirectory(prefix='linspace-http-') as temporary:
        headers = Path(temporary) / 'headers'
        command = ['curl', '-q', '-sS', '--globoff', '--noproxy', '*', '--proxy', '', '--connect-timeout', '5', '--max-time', '20',
                   '-D', str(headers), '-o', output, '-w', '%{http_code}']
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


def fetch(domain, path, local=False):
    """GET a text response of at most 1 MiB, for checks that depend on the rendered content."""
    with tempfile.TemporaryDirectory(prefix='linspace-body-') as temporary:
        body = Path(temporary) / 'body'
        status, headers = probe(domain, path, 'GET', local, output=str(body))
        return status, headers, body.read_text(encoding='utf-8', errors='replace') if body.exists() else ''


def verify_pages(domain, page, local=False, quiet=False):
    """Pages are read on their own host and written through the canonical site's signed Stash API."""
    for method in ('PUT', 'DELETE'):
        status, _ = probe(domain, f'/stash/page/{PROBE_PAGE}', method, local)
        if status != 401:
            raise RuntimeError(f'{method} /stash/page/{PROBE_PAGE}: expected 401, got {status}')
    for action in ('upload', 'delete'):
        path = f'/{PROBE_PAGE}/{action}'
        status, headers, text = fetch(page, path, local)
        if status != 200 or not headers.get('content-type', '').startswith('text/plain') or 'no-store' not in headers.get('cache-control', '') or headers.get('x-content-type-options') != 'nosniff':
            raise RuntimeError(f'https://{page}{path}: unexpected status or headers (HTTP {status})')
        # The page host must render the name into the script; a raw template cannot publish anything.
        if f"page='{PROBE_PAGE}'" not in text or '[[linspace:' in text:
            raise RuntimeError(f'https://{page}{path}: the script was not rendered for its page name; check the Caddy templates handler')
    # An invalid name must still reach bash as a script that explains the rule and fails.
    status, headers, text = fetch(page, '/Not_A_Page/upload', local)
    if status != 200 or not headers.get('content-type', '').startswith('text/plain') or 'Invalid page name' not in text or 'exit 1' not in text:
        raise RuntimeError(f'https://{page}/Not_A_Page/upload: expected a script that rejects the name (HTTP {status})')
    status, headers = probe(page, '/' + PROBE_PAGE, local=local)
    media = 'text/html' if status == 200 else 'text/plain'
    if status not in (200, 404) or not headers.get('content-type', '').startswith(media) or 'no-store' not in headers.get('cache-control', '') or headers.get('x-content-type-options') != 'nosniff' or 'noindex' not in headers.get('x-robots-tag', ''):
        raise RuntimeError(f'https://{page}/{PROBE_PAGE}: unexpected status or headers (HTTP {status})')
    for path, expected in [('/robots.txt', 200), ('/Not_A_Page', 404), (f'/{PROBE_PAGE}/source', 404)]:
        status, _ = probe(page, path, local=local)
        if status != expected:
            raise RuntimeError(f'https://{page}{path}: expected {expected}, got {status}')
    status, headers = probe(page, '/', local=local)
    if status != 308 or headers.get('location') != f'https://{domain}/':
        raise RuntimeError(f'https://{page}/: expected a 308 redirect to https://{domain}/ (HTTP {status})')
    if not quiet:
        linspace_log('OK', f'https://{page}: page scripts, headers and redirect')


def verify(meta, local=False, quiet=False):
    domain = meta['domain']
    paths = ['ssh/' + meta.get('ssh_public_key_name', 'key.pub')] if meta['ssh_enabled'] else []
    paths += [*CLIENT_ROUTES, 'stash/upload', 'stash/clear', *[f'stash/upload{n}' for n in range(8)], 'stash/keys', 'stash/challenge']
    checks = [('/', 200, 'text/html', 'no-store')]
    checks += [('/help', 200, 'text/html', 'no-store'), ('/help2', 200, 'text/html', 'no-store')]
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
    if meta.get('page_domain'):
        verify_pages(domain, meta['page_domain'], local, quiet)
    linspace_log('OK', f'HTTPS verification passed for {domain}' + (f' and {meta["page_domain"]}' if meta.get('page_domain') else '')
                 + (' via loopback' if local else '') + '; stash contents unchanged.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--local', action='store_true')
    args = parser.parse_args()
    verify(json.loads((args.release / 'release.json').read_text()), args.local)


if __name__ == '__main__':
    main()
