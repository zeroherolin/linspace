#!/usr/bin/env python3
"""Generate a configured, offline-buildable deployment release."""
from linspace_console import linspace_log
import gzip
import hashlib
import io
import json
import re
import shutil
import tarfile
from pathlib import Path
import siteconfig
import codex_catalog
import downloads
import helppage

ROOT = Path(__file__).resolve().parents[1]
INCLUDE = re.compile(r'^@@include:([^\n]+)@@\n', re.M)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def render(relative, values, stack=()):
    if not stack and 'ASSET_CASES' not in values:
        values = {**downloads.values(), **values}
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT) or path in stack:
        raise ValueError(f'Unsafe or cyclic include: {relative}')
    text = INCLUDE.sub(lambda m: render(m[1], values, (*stack, path)), path.read_text())
    if relative.startswith('src/') and path.suffix == '.py':
        text = text.replace('from linspace_console import linspace_log', render('scripts/linspace_console.py', values, (*stack, path)))
        if 'from common import *' in text:
            text = text.replace('from common import *', render('src/lifecycle/common.py', values, (*stack, path)))
    for key, value in values.items():
        text = text.replace('@@' + key + '@@', value)
    if re.search(r'@@[A-Z_]+@@|@@include:', text):
        raise ValueError(f'Unresolved template token in {relative}')
    return text


def write(root, relative, data):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode())
    path.chmod(0o644)


def alias_block(config):
    """Caddy site block that sends every alias hostname to the canonical domain.

    Aliases exist for filings and typed URLs, not for serving content: a single
    permanent redirect keeps one origin for scripts, signatures and caches."""
    aliases = config.get('alias_domains') or []
    if not aliases:
        return ''
    return ', '.join(aliases) + ' {\n    redir https://' + config['domain'] + '{uri} 308\n}\n\n'


def checksums(root):
    entries = {p.relative_to(root).as_posix(): digest(p.read_bytes()) for p in sorted(root.rglob('*')) if p.is_file() and p.name != 'SHA256SUMS'}
    write(root, 'SHA256SUMS', ''.join(f'{sha}  {name}\n' for name, sha in entries.items()))
    return entries


def archive(directory):
    path = directory.with_name(directory.name + '.tar.gz')
    with path.open('wb') as output, gzip.GzipFile(filename='', mode='wb', fileobj=output, mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode='w', format=tarfile.USTAR_FORMAT) as tar:
            for p in [directory, *sorted(directory.rglob('*'))]:
                entry = tarfile.TarInfo(p.relative_to(directory.parent).as_posix())
                entry.uid = entry.gid = entry.mtime = 0
                entry.uname = entry.gname = ''
                if p.is_dir():
                    entry.type, entry.mode = tarfile.DIRTYPE, 0o755
                    tar.addfile(entry)
                else:
                    data = p.read_bytes()
                    entry.size, entry.mode = len(data), 0o755 if p.name == 'linspace' else 0o644
                    tar.addfile(entry, io.BytesIO(data))


def build(config_path, output=None, internal=False):
    config, key, claude_settings, codex_config = siteconfig.load(config_path, internal)
    stash_keys = siteconfig.stash_keys(config, key)
    codex_models, _ = codex_catalog.load_catalog(ROOT)
    output = Path(output or ROOT / 'dist').absolute()
    if output.is_symlink() or output == ROOT or not (output.name == 'dist' or output.name.startswith('linspace-build-')):
        raise ValueError('Build output must be a dist directory or a linspace-build-* temporary directory, never a symlink')
    if output.exists():
        shutil.rmtree(output)
    release = output / 'linspace-site'
    release.mkdir(parents=True)
    published_key = config['ssh_public_key_name'] if key else None
    values = {'DOMAIN': config['domain'], 'SSH_ROUTE': f' /ssh/{published_key}' if published_key else '', 'ALIAS_BLOCK': alias_block(config), **downloads.values()}
    for client, title in [('claude', 'Claude Code'), ('codex', 'Codex')]:
        write(release, f'site/{client}/install', render('src/lifecycle/install.sh.in', {**values, 'CLIENT': client, 'CLIENT_NAME': title}))
    resources = json.loads((ROOT / 'config/downloads.json').read_text())['assets']
    for client, title in [('mihomo', 'Mihomo'), ('claude', 'Claude Code'), ('codex', 'Codex')]:
        hashes = {digest for name, entry in resources.items() if name.startswith(client + '-')
                  for digest in [entry['sha256'], *(part['sha256'] for part in entry['parts'])]}
        uninstall_values = {**values, 'CLIENT': client, 'CLIENT_NAME': title, 'CLIENT_CACHE_HASHES': ' '.join(sorted(hashes))}
        uninstall_values['UNINSTALL_RETENTION'] = {
            'mihomo': 'No proxy data is retained.',
            'claude': 'Keeps Claude Code session records only.',
            'codex': 'Keeps Codex session records only.',
        }[client]
        uninstall_values['UNINSTALL_BODY'] = render('src/lifecycle/mihomo.py' if client == 'mihomo' else 'src/lifecycle/clients.py', uninstall_values)
        write(release, f'site/{client}/uninstall', render('src/lifecycle/uninstall.sh.in', uninstall_values))
    for name, source in {
        'site/mihomo/install': 'src/mihomo/install.sh.in', 'site/mihomo/sub': 'src/mihomo/sub.sh.in',
        'site/mihomo/restart': 'src/mihomo/restart.sh',
        'site/tmux/install': 'src/tmux/install.sh.in', 'site/tmux/uninstall': 'src/tmux/uninstall.sh.in',
        'site/codex/auth': 'src/codex/auth.sh.in', 'site/stash/clear': 'src/stash/clear.sh',
        'config/Caddyfile': 'config/Caddyfile.in', 'config/stash.caddy.template': 'src/stash/stash.caddy.in',
        'service/stashd.py': 'src/stash/stashd.py', 'service/stashd.service': 'src/stash/stashd.service',
        'service/stashd.socket': 'src/stash/stashd.socket',
    }.items():
        write(release, name, render(source, values))
    for channel in range(8):
        write(release, f'site/stash/upload{channel}', render('src/stash/upload.sh.in', values).replace('__CHANNEL__', str(channel)))
    if published_key:
        write(release, f'site/ssh/{published_key}', key)
    write(release, 'site/claude/config', claude_settings)
    write(release, 'site/codex/config', codex_config)
    write(release, 'site/codex/models_1m', codex_models)
    write(release, 'site/tmux/config', siteconfig.tmux_config(config))
    write(release, 'site/stash/keys', '\n'.join(stash_keys) + ('\n' if stash_keys else ''))
    write(release, 'config/stash.allowed_signers', ''.join(f'stash namespaces="linspace-stash@{config["domain"]}" {key}\n' for key in stash_keys))
    write(release, 'site/index.html', siteconfig.page(config))
    write(release, 'site/help', helppage.help_page(config, ssh_key_name=published_key))
    # The complete page is not linked from the home page and carries only the site link in its footer.
    write(release, 'site/help2', helppage.help_page(config, helppage.COMPLETE_SOURCE, ssh_key_name=published_key, icp_footer=False))
    for name in ('deploy.py', 'verify.py', 'linspace_console.py'):
        write(release, name, (ROOT / 'scripts' / name).read_bytes())
    write(release, 'install-caddy.sh', render('scripts/install-caddy.sh.in', values))
    write(release, 'README.md', (ROOT / 'docs/site-bundle.md').read_bytes())
    write(release, 'linspace', '#!/usr/bin/env bash\nset -Eeuo pipefail\ncd -- "$(dirname -- "${BASH_SOURCE[0]}")"\nexec python3 -B deploy.py "$@"\n')
    (release / 'linspace').chmod(0o755)
    write(release, 'release.json', json.dumps({'format': 1, 'domain': config['domain'], 'alias_domains': config['alias_domains'], 'site_name': config['site_name'], 'icp_number': config['icp_number'], 'ssh_enabled': key is not None, 'ssh_public_key_name': config['ssh_public_key_name'], 'stash_auth': 'ssh-signature-v1', 'stash_key_count': len(stash_keys), 'internal_test': internal}, ensure_ascii=False, indent=2) + '\n')
    checksums(release)
    target = output / 'linspace-mihomo-target'
    shutil.copytree(release / 'site/mihomo', target / 'mihomo')
    write(target, 'README.md', render('docs/mihomo-bundle.md', values))
    checksums(target)
    for directory in (release, target):
        archive(directory)
    checksums(output)
    linspace_log('OK', f'Built release for https://{config["domain"]}')
    return release
