"""Render a verified download manifest without knowing its hosting provider."""
import base64
import json
from pathlib import Path
import re
import shlex
from urllib.parse import urlsplit
import vendor

ROOT = Path(__file__).resolve().parents[1]


def https_url(value, optional=False):
    if optional and value == '':
        return value
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.fragment or any(c.isspace() or ord(c) < 32 for c in value):
        raise ValueError('Download URLs must use HTTPS without credentials or whitespace')
    return value


def values():
    lock = json.loads((ROOT / 'config/downloads.json').read_text())
    if lock['schema'] != 1:
        raise ValueError('Unsupported download manifest')
    cases = []
    required = {'geoip', 'mihomo-amd64-v1', 'mihomo-arm64'} | {f'{client}-linux-{arch}' for client in ('claude','codex','python','caddy') for arch in ('x64','arm64')}
    if not required <= lock['assets'].keys():
        raise ValueError('The download manifest is missing required Linux packages')
    for name, entry in lock['assets'].items():
        if not isinstance(entry.get('version'), str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.+_-]{0,127}', entry['version']):
            raise ValueError(f'Invalid asset version: {name}')
        if type(entry.get('size')) is not int or entry['size'] <= 0:
            raise ValueError(f'Invalid asset size: {name}')
        if 'raw_sha256' in entry and not re.fullmatch(r'[0-9a-f]{64}', entry['raw_sha256']):
            raise ValueError(f'Invalid decompressed checksum: {name}')
        if not re.fullmatch(r'[a-z0-9-]+', name):
            raise ValueError('Invalid asset name')
        urls, hashes, sizes = [], [], []
        for part in entry['parts']:
            if not re.fullmatch(r'[0-9a-f]{64}', part['sha256']) or type(part['size']) is not int or not 0 < part['size'] <= 536870912:
                raise ValueError(f'Invalid asset part: {name}')
            urls.append(https_url(part['url']))
            hashes.append(part['sha256'])
            sizes.append(str(part['size']))
        url = https_url(entry.get('url', ''), optional=True)
        if not urls or not re.fullmatch(r'[0-9a-f]{64}', entry['sha256']) or sum(map(int, sizes)) != entry['size']:
            raise ValueError(f'Invalid asset: {name}')
        assignments = {'ASSET_SHA': entry['sha256'], 'ASSET_SIZE': str(entry['size']), 'ASSET_URL': url, 'ASSET_VERSION': entry['version'], 'ASSET_RAW_SHA': entry.get('raw_sha256',''), 'ASSET_TARGET': entry.get('target','')}
        line = '        ' + name + ') ' + '; '.join(f'{k}={shlex.quote(v)}' for k,v in assignments.items()) + '; '
        line += '; '.join(f'{k}=({" ".join(shlex.quote(v) for v in seq)})' for k,seq in [('ASSET_PART_URLS',urls),('ASSET_PART_SHAS',hashes),('ASSET_PART_SIZES',sizes)]) + ' ;;'
        cases.append(line)
    engines = [lock['assets'][name] for name in ('mihomo-amd64-v1','mihomo-arm64')]
    if engines[0]['version'] != engines[1]['version'] or any('raw_sha256' not in entry for entry in engines):
        raise ValueError('Mihomo architectures need matching versions and decompressed checksums')
    geo = lock['assets']['geoip']['raw_sha256']
    if not re.fullmatch(r'[0-9a-f]{64}', geo):
        raise ValueError('Invalid GeoIP checksum')
    return {'MIHOMO_VERSION': 'v' + engines[0]['version'], 'TOMLI_ZIP': base64.b64encode(vendor.zip_bytes('tomli')).decode(), 'ASSET_CASES': '\n'.join(cases), 'PYYAML_ZIP': base64.b64encode(vendor.zip_bytes('pyyaml')).decode(), 'ASSET_SOURCE': https_url(lock['source_url']), 'GEO_SHA': geo}
