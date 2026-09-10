"""Embedded in each downloadable Stash script; only standard-library Python."""
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
PROTOCOL = 'linspace-stash-v1'


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
    command = ['curl', '-q', '-sS', '--globoff', '--proto', '=https', '--connect-timeout', '10',
               '--max-time', '30', '--max-filesize', str(limit), '-X', method,
               '-o', str(response), '-w', '%{http_code}']
    for name, value in headers:
        command += ['-H', name + ': ' + value]
    if data is not None:
        payload = temporary / 'payload'
        payload.write_bytes(data)
        command += ['--data-binary', '@' + str(payload), '-H', 'Content-Type: text/plain; charset=utf-8']
    result = subprocess.run(command + [base_url + path], capture_output=True, text=True, timeout=40)
    if result.returncode:
        raise RuntimeError('HTTPS request failed: ' + result.stderr.strip())
    if not re.fullmatch(r'[0-9]{3}', result.stdout):
        raise RuntimeError('Unexpected response from curl.')
    body = response.read_bytes()
    if len(body) > limit:
        raise RuntimeError('The server response exceeds the allowed size.')
    # Deliberately do not follow redirects with a signed request.
    return int(result.stdout), body


def main(base_url, action, argv=None):
    parser = argparse.ArgumentParser(description='Write public Stash text using an authorized SSH key.')
    if action.startswith('upload'):
        parser.add_argument('file', type=Path)
    parser.add_argument('-i', '--identity', default=os.environ.get('STASH_IDENTITY'),
                        help='optional SSH key path; default: matching agent key, then ~/.ssh key pairs')
    args = parser.parse_args(argv)
    try:
        for command in ('curl', 'ssh-keygen', 'ssh-add'):
            if not shutil.which(command):
                raise ValueError(f'{command} is required; install curl and OpenSSH client tools.')
        os.umask(0o077)
        if action.startswith('upload'):
            if not args.file.is_file():
                raise ValueError('Upload a regular UTF-8 text file.')
            with args.file.open('rb') as source:
                data = source.read(MAX_SIZE + 1)
            if len(data) > MAX_SIZE:
                raise ValueError('The file exceeds 1 MiB.')
            if b'\0' in data:
                raise ValueError('NUL bytes are not accepted.')
            data.decode('utf-8')
            method, path = 'PUT', '/stash/download' + action.removeprefix('upload')
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
            status, challenge_bytes = request(base_url, '/stash/challenge', temporary, limit=512)
            challenge = challenge_bytes.decode('ascii').strip()
            if status != 200 or not re.fullmatch(r'[0-9a-f]{64}\.[0-9]{10,12}\.[0-9a-f]{64}', challenge):
                raise RuntimeError(f'Cannot obtain an SSH signing challenge (HTTP {status}).')
            message = temporary / 'message'
            message.write_text('\n'.join((PROTOCOL, base_url, method, path, hashlib.sha256(data).hexdigest(), challenge, '')), encoding='ascii')
            signed = subprocess.run(['ssh-keygen', '-Y', 'sign', '-f', str(identity), '-n',
                                     'linspace-stash@' + domain, str(message)], timeout=120)
            if signed.returncode:
                raise RuntimeError('SSH signing failed. Unlock the selected key or load it into ssh-agent.')
            sigfile = temporary / 'message.sig'
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
            if status != 204:
                detail = {401: 'signature rejected or challenge expired; rerun with an authorized key',
                          429: 'server busy; retry shortly', 413: 'file exceeds 1 MiB',
                          415: 'file is not valid UTF-8 text', 503: 'authentication service unavailable'}.get(status, 'unexpected response')
                raise RuntimeError(f'Stash write failed (HTTP {status}): {detail}.')
        if method == 'PUT':
            print(f'Uploaded {len(data)} bytes; anyone can read {base_url}{path}')
        else:
            print(f'Cleared all eight channels of {base_url}/stash')
    except (ValueError, OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f'Error: {error}', file=sys.stderr)
        sys.exit(1)
