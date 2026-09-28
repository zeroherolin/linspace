"""Embedded in each downloadable Stash script; only standard-library Python."""
from linspace_console import linspace_log
import argparse
import base64
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

MAX_SIZE = 1024 * 1024
MAX_PAGE_SIZE = 4 * 1024 * 1024
PAGE_NAME = re.compile(r'[a-z0-9][a-z0-9_-]{0,47}')
PROTOCOL = 'linspace-stash-v1'
CHALLENGE_TTL = 90
# Signing must finish well inside the challenge lifetime, including a passphrase or FIDO touch.
SIGN_TIMEOUT = 60


def key_identity(text):
    fields = text.strip().split()
    return ' '.join(fields[:2]) if len(fields) >= 2 else ''


def choose_identity(authorized, temporary, explicit=None):
    if explicit:
        path = Path(explicit).expanduser().absolute()
        if not path.is_file():
            raise ValueError('The selected SSH identity is not a regular file.')
        return path
    # An agent can hold hardware-backed keys or a forwarded key without a local private file.
    if os.environ.get('SSH_AUTH_SOCK'):
        try:
            listed = subprocess.run(['ssh-add', '-L'], capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            listed = None
        if listed is not None and listed.returncode == 0:
            for line in listed.stdout.splitlines():
                if key_identity(line) in authorized:
                    path = temporary / 'agent-key.pub'
                    path.write_text(key_identity(line) + '\n')
                    return path
    directory = Path.home() / '.ssh'
    candidates = [directory / name for name in ('id_ed25519', 'id_ecdsa', 'id_rsa', 'id_ed25519_sk', 'id_ecdsa_sk')]
    candidates += [path.with_suffix('') for path in sorted(directory.glob('*.pub'))]
    for private in dict.fromkeys(candidates):
        if not private.is_file():
            continue
        public = Path(str(private) + '.pub')
        try:
            if public.is_file():
                identity = key_identity(public.read_text())
            else:
                # Never prompt for unrelated keys while discovering an identity.
                derived = subprocess.run(['ssh-keygen', '-y', '-P', '', '-f', str(private)],
                                         capture_output=True, text=True, timeout=5)
                identity = key_identity(derived.stdout) if derived.returncode == 0 else ''
        except (OSError, UnicodeError, subprocess.TimeoutExpired):
            continue
        if identity in authorized:
            return private
    raise ValueError('No authorized SSH identity found. Load your key with ssh-add, place its key pair in ~/.ssh, '
                     'or set STASH_IDENTITY / use -i. A remote authorized_keys file alone cannot sign.')


def request(base_url, path, temporary, method='GET', data=None, headers=(), limit=MAX_SIZE):
    response = temporary / 'response'
    # Writes get the server's 60-second body deadline plus time to verify and answer.
    max_time = 30 if data is None else 90
    command = ['curl', '-q', '-sS', '--globoff', '--proto', '=https', '--connect-timeout', '10',
               '--max-time', str(max_time), '--max-filesize', str(limit), '-X', method,
               '-o', str(response), '-w', '%{http_code}']
    for name, value in headers:
        command += ['-H', name + ': ' + value]
    if data is not None:
        payload = temporary / 'payload'
        payload.write_bytes(data)
        command += ['--data-binary', '@' + str(payload), '-H', 'Content-Type: text/plain; charset=utf-8']
    result = subprocess.run(command + [base_url + path], capture_output=True, text=True, timeout=max_time + 10)
    if result.returncode:
        raise RuntimeError('HTTPS request failed: ' + result.stderr.strip())
    if not re.fullmatch(r'[0-9]{3}', result.stdout):
        raise RuntimeError('Unexpected response from curl.')
    body = response.read_bytes()
    if len(body) > limit:
        raise RuntimeError('The server response exceeds the allowed size.')
    # Deliberately do not follow redirects with a signed request.
    return int(result.stdout), body


def signed_write(base_url, domain, method, path, data, identity, authorized, temporary):
    """Fetch a challenge, sign it, verify locally and send the write. Returns the HTTP status."""
    status, challenge_bytes = request(base_url, '/stash/challenge', temporary, limit=512)
    challenge = challenge_bytes.decode('ascii').strip()
    if status != 200 or not re.fullmatch(r'[0-9a-f]{64}\.[0-9]{10,12}\.[0-9a-f]{64}', challenge):
        raise RuntimeError(f'Cannot obtain an SSH signing challenge (HTTP {status}).')
    message = temporary / 'message'
    message.write_text('\n'.join((PROTOCOL, base_url, method, path, hashlib.sha256(data).hexdigest(), challenge, '')), encoding='ascii')
    sigfile = temporary / 'message.sig'
    sigfile.unlink(missing_ok=True)
    try:
        signed = subprocess.run(['ssh-keygen', '-q', '-Y', 'sign', '-f', str(identity), '-n',
                                 'linspace-stash@' + domain, str(message)], timeout=SIGN_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f'SSH signing did not finish within {SIGN_TIMEOUT} seconds; unlock the key or load it into ssh-agent first.') from None
    if signed.returncode:
        raise RuntimeError('SSH signing failed. Unlock the selected key or load it into ssh-agent.')
    allowed = temporary / 'allowed_signers'
    allowed.write_text(''.join(f'stash namespaces="linspace-stash@{domain}" {key}\n' for key in sorted(authorized)))
    verified = subprocess.run(['ssh-keygen', '-Y', 'verify', '-f', str(allowed), '-I', 'stash',
                               '-n', 'linspace-stash@' + domain, '-s', str(sigfile)],
                              input=message.read_bytes(), capture_output=True, timeout=10)
    if verified.returncode:
        raise ValueError('The selected SSH key is not authorized by this site.')
    signature = base64.b64encode(sigfile.read_bytes()).decode('ascii')
    status, _ = request(base_url, path, temporary, method, data,
                        [('X-Linspace-Challenge', challenge), ('X-Linspace-Signature', signature)], limit=4096)
    return status


def main(base_url, action, argv=None, page=None, page_url=None):
    """Run one write: uploadN or clear for Stash, page-upload or page-delete for the named page."""
    uploading = action.startswith('upload') or action == 'page-upload'
    parser = argparse.ArgumentParser(description='Publish a single HTML page using an authorized SSH key.' if action.startswith('page-')
                                     else 'Write public Stash text using an authorized SSH key.')
    if uploading:
        parser.add_argument('file', type=Path)
    parser.add_argument('-i', '--identity', default=os.environ.get('STASH_IDENTITY'),
                        help='optional SSH key path; default: matching agent key, then ~/.ssh key pairs')
    args = parser.parse_args(argv)
    limit = MAX_PAGE_SIZE if action == 'page-upload' else MAX_SIZE
    try:
        for command in ('curl', 'ssh-keygen', 'ssh-add'):
            if not shutil.which(command):
                raise ValueError(f'{command} is required; install curl and OpenSSH client tools.')
        if action.startswith('page-') and not PAGE_NAME.fullmatch(page or ''):
            raise ValueError(f'This script carries no valid page name. Download it from {page_url}/NAME/{action.removeprefix("page-")}, '
                             'where NAME has up to 48 lowercase letters, digits, hyphens or underscores and starts with a letter or digit.')
        os.umask(0o077)
        if uploading:
            if not args.file.is_file():
                raise ValueError('Upload a regular UTF-8 text file.')
            with args.file.open('rb') as source:
                data = source.read(limit + 1)
            if len(data) > limit:
                raise ValueError(f'The file exceeds {limit // (1024 * 1024)} MiB.')
            if b'\0' in data:
                raise ValueError('NUL bytes are not accepted.')
            data.decode('utf-8')
            if action == 'page-upload':
                if not data.lstrip(b'\xef\xbb\xbf \t\r\n').startswith(b'<'):
                    linspace_log('WARN', 'The file does not start with an HTML tag; it is still published as an HTML page.')
                method, path = 'PUT', '/stash/page/' + page
            else:
                method, path = 'PUT', '/stash/download' + action.removeprefix('upload')
        elif action == 'page-delete':
            data, method, path = b'', 'DELETE', '/stash/page/' + page
        else:
            data, method, path = b'', 'POST', '/stash/clear'
        domain = base_url.removeprefix('https://')
        with tempfile.TemporaryDirectory(prefix='linspace-stash-') as task_dir:
            temporary = Path(task_dir)
            status, keys = request(base_url, '/stash/keys', temporary)
            if status != 200:
                raise RuntimeError(f'Cannot load authorized keys (HTTP {status}); download the current client script.')
            authorized = {key_identity(line) for line in keys.decode('utf-8').splitlines() if line.strip()}
            if not authorized:
                raise ValueError('Stash writes are disabled: no public keys are authorized on this site.')
            if len(authorized) > 64 or '' in authorized:
                raise ValueError('Invalid authorized-key list from the site.')
            identity = choose_identity(authorized, temporary, args.identity)
            status = signed_write(base_url, domain, method, path, data, identity, authorized, temporary)
            if status == 401:
                # A slow passphrase or FIDO touch can outlive the first challenge; the key is now unlocked.
                linspace_log('WARN', 'The site rejected the signature (HTTP 401); retrying once with a fresh challenge.')
                status = signed_write(base_url, domain, method, path, data, identity, authorized, temporary)
            if status != 204:
                detail = {401: 'signature rejected or challenge expired; rerun with an authorized key',
                          408: 'upload timed out; check the connection and retry',
                          429: 'server busy; retry shortly', 413: f'file exceeds {limit // (1024 * 1024)} MiB',
                          415: 'file is not valid UTF-8 text', 503: 'authentication service unavailable',
                          507: 'the site holds its maximum number of pages; delete one first'}.get(status, 'unexpected response')
                if status == 404 and action == 'page-delete':
                    detail = f'no page is published at {page_url}/{page}'
                elif status == 404 and action == 'page-upload':
                    detail = 'this site does not publish pages'
                raise RuntimeError(f'{"Page" if action.startswith("page-") else "Stash"} write failed (HTTP {status}): {detail}.')
        if action == 'page-upload':
            linspace_log('OK', f'Published {len(data)} bytes: {page_url}/{page}')
        elif action == 'page-delete':
            linspace_log('OK', f'Deleted {page_url}/{page}')
        elif method == 'PUT':
            linspace_log('OK', f'Uploaded {len(data)} bytes; public URL: {base_url}{path}')
        else:
            linspace_log('OK', f'Cleared all eight channels of {base_url}/stash')
    except (ValueError, OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        linspace_log('ERROR', error)
        sys.exit(1)
