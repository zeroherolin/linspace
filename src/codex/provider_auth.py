"""Optional -u support, embedded in the downloadable Codex auth script."""
from linspace_console import linspace_log
import copy
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import urlsplit


def replace_base_url(data, url):
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib
        except ImportError:
            raise ValueError('The bundled TOML parser is unavailable. Download the current auth script again.') from None
    try:
        parsed_url = urlsplit(url)
        parsed_url.port
        valid = parsed_url.scheme in ('https', 'http') and parsed_url.hostname and parsed_url.username is None and not parsed_url.fragment
    except ValueError:
        valid = False
    if not valid or any(c.isspace() or ord(c) < 32 or ord(c) == 127 or c == '\\' for c in url):
        raise ValueError('-u requires an absolute HTTP(S) base URL without userinfo, whitespace or a fragment.')
    try:
        text = data.decode('utf-8')
        original = tomllib.loads(text)
    except (UnicodeError, ValueError):
        raise ValueError('config.toml is not valid UTF-8 TOML.') from None
    provider = original.get('model_provider')
    providers = original.get('model_providers', {})
    settings = providers.get(provider) if isinstance(providers, dict) and isinstance(provider, str) else None
    if not isinstance(settings, dict) or not isinstance(settings.get('base_url'), str):
        raise ValueError('config.toml must select a model_provider with an existing model_providers.<id>.base_url; download /codex/config first.')
    expected = copy.deepcopy(original)
    expected['model_providers'][provider]['base_url'] = url
    if original == expected:
        return data
    # Try only single-line URL assignments. Parsing each candidate proves that
    # exactly the selected provider changed, including with quoted/dotted keys.
    assignment = re.compile(
        r'''(?m)^[ \t]*[^#=\r\n]*\bbase_url["']?[ \t]*=[ \t]*(?P<value>"(?:\\[^\r\n]|[^"\\\r\n])*"|'[^'\r\n]*')(?=[ \t]*(?:\#[^\r\n]*)?\r?$)''')
    for match in assignment.finditer(text):
        candidate = text[:match.start('value')] + json.dumps(url, ensure_ascii=False) + text[match.end('value'):]
        try:
            if tomllib.loads(candidate) == expected:
                return candidate.encode('utf-8')
        except ValueError:
            pass
    raise ValueError('Use a single-line base_url assignment for the selected provider; no files were changed.')


def regular_bytes(path, required=False):
    if path.is_symlink() or path.exists() and not path.is_file():
        raise ValueError(f'{path.name} must be a regular file, not a symbolic link.')
    if not path.exists():
        if required:
            raise ValueError('config.toml is missing; download /codex/config before using -u.')
        return None
    return path.read_bytes()


def private_file(directory, prefix, data):
    descriptor, name = tempfile.mkstemp(dir=directory, prefix=prefix)
    path = Path(name)
    try:
        with os.fdopen(descriptor, 'wb') as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        return path
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def save_pair(config_dir, url, token):
    config = config_dir / 'config.toml'
    auth = config_dir / 'auth.json'
    old_config = regular_bytes(config, required=True)
    updated = replace_base_url(old_config, url)
    old_auth = regular_bytes(auth)
    auth_data = (json.dumps({'auth_mode': 'apikey', 'OPENAI_API_KEY': token}, indent=2) + '\n').encode()
    if old_auth == auth_data:
        auth.chmod(0o600)
    changes = [(path, old, new) for path, old, new in
               ((config, old_config, updated), (auth, old_auth, auth_data)) if old != new]
    temporary, originals, applied = {}, {}, []
    try:
        # Prepare both files before publishing either change; keep rollback bytes only in memory.
        for path, old, new in changes:
            temporary[path] = private_file(config_dir, '.codex-update-', new)
            if old is not None:
                originals[path] = old
        for path, old, _ in changes:
            if regular_bytes(path) != old:
                raise ValueError('Configuration changed during the update; retry after other edits finish.')
        for path, _, _ in changes:
            os.replace(temporary[path], path)
            applied.append(path)
    except BaseException as error:
        rollback_failed = False
        for path in reversed(applied):
            try:
                if path in originals:
                    restore = private_file(config_dir, '.codex-restore-', originals[path])
                    try:
                        os.replace(restore, path)
                    finally:
                        restore.unlink(missing_ok=True)
                else:
                    path.unlink(missing_ok=True)
            except OSError:
                rollback_failed = True
        if rollback_failed:
            raise RuntimeError(f'Write failed and rollback was incomplete in {config_dir}; restore your configuration before retrying.') from error
        raise
    finally:
        for path in temporary.values():
            path.unlink(missing_ok=True)
    linspace_log('OK', 'Saved API credentials and selected provider base_url.' if changes else 'API credentials and base_url are already set.')


def provider_auth_main():
    try:
        if sys.version_info < (3, 9):
            raise ValueError('-u requires Python 3.9 or later.')
        # Keep the token out of Python command arguments and environment variables.
        with os.fdopen(3) as source:
            token = source.read().removesuffix('\n')
        save_pair(Path(sys.argv[1]), sys.argv[2], token)
    except (OSError, ValueError, RuntimeError) as error:
        linspace_log('ERROR', error)
        sys.exit(1)
