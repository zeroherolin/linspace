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
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.fragment or any(c.isspace() for c in value):
        raise ValueError('Download URLs must use HTTPS without credentials or whitespace')
    return value


def values():
    lock = json.loads((ROOT / 'config/downloads.json').read_text())
    if lock['schema'] != 1:
        raise ValueError('Unsupported download manifest')
    cases = []
    for name, entry in lock['assets'].items():
        if not re.fullmatch(r'[a-z0-9-]+', name):
            raise ValueError('Invalid asset name')
        urls, hashes, sizes = [], [], []
        for part in entry['parts']:
            if not re.fullmatch(r'[0-9a-f]{64}', part['sha256']) or not isinstance(part['size'], int) or not 0 < part['size'] <= 536870912:
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
    geo = lock['assets']['geoip']['raw_sha256']
    if not re.fullmatch(r'[0-9a-f]{64}', geo):
        raise ValueError('Invalid GeoIP checksum')
    return {'TOMLI_ZIP': base64.b64encode(vendor.zip_bytes('tomli')).decode(), 'ASSET_CASES': '\n'.join(cases), 'PYYAML_ZIP': base64.b64encode(vendor.zip_bytes('pyyaml')).decode(), 'ASSET_SOURCE': https_url(lock['source_url']), 'GEO_SHA': geo}
