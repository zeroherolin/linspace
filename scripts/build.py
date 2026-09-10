#!/usr/bin/env python3
"""Generate a configured, offline-buildable deployment release."""
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

ROOT = Path(__file__).resolve().parents[1]
INCLUDE = re.compile(r'^@@include:([^\n]+)@@\n', re.M)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def render(relative, values, stack=()):
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT) or path in stack:
        raise ValueError(f'Unsafe or cyclic include: {relative}')
    text = INCLUDE.sub(lambda m: render(m[1], values, (*stack, path)), path.read_text())
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
    asset = json.loads((ROOT / 'assets/manifest.json').read_text())['geoip']
    compressed = (ROOT / asset['path']).read_bytes()
    if digest(compressed) != asset['compressed_sha256']:
        raise ValueError('Compressed GeoIP checksum mismatch')
    geo = gzip.decompress(compressed)
    if digest(geo) != asset['sha256'] or len(geo) != asset['size']:
        raise ValueError('GeoIP snapshot checksum mismatch')
    key_name = config['ssh_public_key_name']
    values = {'DOMAIN': config['domain'], 'GEO_SHA': asset['sha256'], 'SSH_ROUTE': f' /ssh/{key_name}' if key else ''}
    for name, source in {
        'site/mihomo/install': 'src/mihomo/install.sh.in', 'site/mihomo/sub': 'src/mihomo/sub.sh.in',
        'site/mihomo/restart': 'src/mihomo/restart.sh', 'site/codex/auth': 'src/codex/auth.sh.in',
        'site/stash/clear': 'src/stash/clear.sh',
        'config/Caddyfile': 'config/Caddyfile.in', 'config/stash.caddy.template': 'src/stash/stash.caddy.in',
        'service/stashd.py': 'src/stash/stashd.py', 'service/stashd.service': 'src/stash/stashd.service',
        'service/stashd.socket': 'src/stash/stashd.socket',
    }.items():
        write(release, name, render(source, values))
    for channel in range(8):
        write(release, f'site/stash/upload{channel}', render('src/stash/upload.sh.in', values).replace('__CHANNEL__', str(channel)))
    if key:
        write(release, f'site/ssh/{key_name}', key)
    write(release, 'site/claude/config', claude_settings)
    write(release, 'site/codex/config', codex_config)
    write(release, 'site/codex/models_1m', codex_models)
    write(release, 'site/stash/keys', '\n'.join(stash_keys) + ('\n' if stash_keys else ''))
    write(release, 'config/stash.allowed_signers', ''.join(f'stash namespaces="linspace-stash@{config["domain"]}" {key}\n' for key in stash_keys))
    write(release, 'site/index.html', siteconfig.page(config))
    write(release, f"site/mihomo/assets/geoip-{asset['sha256']}.dat", geo)
    for name in ('deploy.py', 'verify.py'):
        write(release, name, (ROOT / 'scripts' / name).read_bytes())
    write(release, 'install-caddy.sh', (ROOT / 'scripts/install-caddy.sh').read_bytes())
    write(release, 'README.md', (ROOT / 'packaging/site-README.md').read_bytes())
    write(release, 'linspace', '#!/usr/bin/env bash\nset -Eeuo pipefail\ncd -- "$(dirname -- "${BASH_SOURCE[0]}")"\nexec python3 -B deploy.py "$@"\n')
    (release / 'linspace').chmod(0o755)
    write(release, 'release.json', json.dumps({'format': 1, 'domain': config['domain'], 'site_name': config['site_name'], 'icp_number': config['icp_number'], 'ssh_enabled': key is not None, 'ssh_public_key_name': key_name, 'stash_auth': 'ssh-signature-v1', 'stash_key_count': len(stash_keys), 'internal_test': internal, 'geoip_sha256': asset['sha256']}, ensure_ascii=False, indent=2) + '\n')
    checksums(release)
    target = output / 'linspace-mihomo-target'
    shutil.copytree(release / 'site/mihomo', target / 'mihomo')
    write(target, 'README.md', render('packaging/mihomo-README.md', values))
    checksums(target)
    for directory in (release, target):
        archive(directory)
    checksums(output)
    print(f'Built {release} for https://{config["domain"]}' + (' (internal test)' if internal else ''))
    return release
