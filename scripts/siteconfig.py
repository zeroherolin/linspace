"""Read user configuration as data; never source it as shell code."""
import base64
import html
import ipaddress
import json
import re
import struct
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELDS = {'domain', 'site_name', 'icp_number', 'ssh_public_key_file', 'claude_settings_file'}


def domain_name(value, internal=False):
    if not isinstance(value, str) or value != value.strip() or any(c in value for c in '/:@*{}\\\n\r\t '):
        raise ValueError('domain must be a hostname only, without https://, a port, or a path')
    try:
        domain = value.encode('idna').decode('ascii').lower()
    except UnicodeError as exc:
        raise ValueError('domain is not a valid DNS hostname') from exc
    if len(domain) > 253 or '.' not in domain or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in domain.split('.')):
        raise ValueError('domain must be a fully qualified DNS hostname')
    try:
        ipaddress.ip_address(domain)
    except ValueError:
        pass
    else:
        raise ValueError('Use a domain name, not an IP address')
    reserved = domain in {'example.com', 'example.net', 'example.org'} or domain.endswith(('.example', '.invalid', '.test', '.localhost'))
    if reserved and not internal:
        raise ValueError('Replace the example domain with your resolved, ICP-filed domain')
    return domain


def public_key(data):
    try:
        text = data.decode('utf-8').strip()
        parts = text.split()
        allowed = {'ssh-ed25519', 'ssh-rsa', 'ecdsa-sha2-nistp256', 'ecdsa-sha2-nistp384', 'ecdsa-sha2-nistp521', 'sk-ssh-ed25519@openssh.com', 'sk-ecdsa-sha2-nistp256@openssh.com'}
        if '\n' in text or len(parts) < 2 or parts[0] not in allowed or len(data) > 16384:
            raise ValueError()
        decoded = base64.b64decode(parts[1], validate=True)
        length = struct.unpack('>I', decoded[:4])[0]
        if decoded[4:4 + length].decode('ascii') != parts[0] or len(decoded) <= 4 + length:
            raise ValueError()
    except (ValueError, UnicodeError, struct.error) as exc:
        raise ValueError('SSH file must contain one OpenSSH public key, never a private key or authorized_keys options') from exc
    normalized = (text + '\n').encode()
    checked = subprocess.run(['ssh-keygen', '-l', '-f', '-'], input=normalized, capture_output=True)
    if checked.returncode:
        raise ValueError('ssh-keygen could not validate the public key')
    return normalized


def load(path, internal=False, root=ROOT):
    path = Path(path)
    raw = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(raw, dict) or set(raw) - FIELDS:
        raise ValueError('Unknown configuration fields; use config/site.example.json as the schema')
    config = dict(raw)
    config['domain'] = domain_name(raw.get('domain', ''), internal)
    for key in ('site_name', 'icp_number'):
        value = raw.get(key, '')
        if not isinstance(value, str) or len(value) > 200 or any(ord(c) < 32 for c in value):
            raise ValueError(f'{key} must be a single line of text, at most 200 characters')
        value = value.strip()
        if not value and not (internal and key == 'icp_number'):
            raise ValueError(f'{key} is required')
        if not internal and re.search(r'YOUR_[A-Z_]+|X{4,}|\b(?:REPLACE_ME|PLACEHOLDER)\b', value, re.I):
            raise ValueError(f'Replace the placeholder in {key}')
        config[key] = value
    if not internal and not re.search(r'ICP.*\d.*号', config['icp_number'], re.I):
        raise ValueError('icp_number must contain your complete issued ICP filing number, including its site suffix')
    for key, fallback in [('ssh_public_key_file', ''), ('claude_settings_file', 'config/claude/settings.json')]:
        value = raw.get(key, fallback)
        if not isinstance(value, str):
            raise ValueError(f'{key} must be a file path')
        config[key] = value
    key_data = None
    if config['ssh_public_key_file']:
        p = Path(config['ssh_public_key_file']).expanduser()
        key_data = public_key((p if p.is_absolute() else root / p).read_bytes())
    p = Path(config['claude_settings_file']).expanduser()
    if not config['claude_settings_file']:
        raise ValueError('claude_settings_file must point to a JSON settings file')
    settings = json.loads((p if p.is_absolute() else root / p).read_text())
    if not isinstance(settings, dict):
        raise ValueError('Claude settings must be a JSON object')
    return config, key_data, (json.dumps(settings, ensure_ascii=False, indent=2) + '\n').encode()


def page(config):
    template = (ROOT / 'config/index.html.in').read_text()
    return template.replace('@@SITE_NAME@@', html.escape(config['site_name'], quote=True)).replace('@@ICP_NUMBER@@', html.escape(config['icp_number'] or 'Internal test — not for public deployment', quote=True))
