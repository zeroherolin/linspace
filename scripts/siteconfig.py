"""Read user configuration as data; never source it as shell code."""
import base64
import html
import ipaddress
import json
import re
import struct
import subprocess
from pathlib import Path
import codex_catalog

try:
    import tomllib
except ImportError:  # Python 3.9/3.10 on older deployment hosts.
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ('domain', 'site_name', 'icp_number', 'ssh_public_key_file', 'ssh_public_key_name', 'claude_settings_file', 'codex_config_file')


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


def public_key_name(value):
    if not isinstance(value, str) or len(value) > 128 or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*\.pub', value):
        raise ValueError('ssh_public_key_name must be a filename such as key.pub or team.pub: ASCII letters, digits, dots, underscores and hyphens; at most 128 characters')
    return value


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
    if not isinstance(raw, dict) or set(raw) - set(FIELDS):
        raise ValueError('Unknown configuration fields; use config/site.example.json as the schema')
    config = dict(raw)
    config['domain'] = domain_name(raw.get('domain', ''), internal)
    config['ssh_public_key_name'] = public_key_name(raw.get('ssh_public_key_name', 'key.pub'))
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
    for key, fallback in [('ssh_public_key_file', ''), ('claude_settings_file', 'config/claude/settings.json'), ('codex_config_file', 'config/codex/config.toml')]:
        value = raw.get(key, fallback)
        if not isinstance(value, str):
            raise ValueError(f'{key} must be a file path')
        # Freeze user-home inputs when configure saves the profile, before sudo
        # can resolve the same spelling against a different account's home.
        config[key] = str(Path(value).expanduser()) if value.startswith('~') else value
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
    if not config['codex_config_file']:
        raise ValueError('codex_config_file must point to a TOML configuration file')
    p = Path(config['codex_config_file']).expanduser()
    codex = (p if p.is_absolute() else root / p).read_bytes()
    if tomllib is None:
        raise ValueError('TOML validation needs Python 3.11+ or tomli: install python3-tomli on Debian/Ubuntu, or requirements.txt in a Python virtual environment')
    try:
        codex_settings = tomllib.loads(codex.decode('utf-8'))
    except (UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError('Codex configuration must be valid UTF-8 TOML') from exc
    _, catalog = codex_catalog.load_catalog()
    codex_catalog.validate_settings(codex_settings, catalog)
    return config, key_data, (json.dumps(settings, ensure_ascii=False, indent=2) + '\n').encode(), codex


def page(config):
    template = (ROOT / 'config/index.html.in').read_text()
    return template.replace('@@SITE_NAME@@', html.escape(config['site_name'], quote=True)).replace('@@ICP_NUMBER@@', html.escape(config['icp_number'] or 'Internal test — not for public deployment', quote=True))
