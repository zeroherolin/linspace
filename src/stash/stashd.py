#!/usr/bin/env python3
"""Write side of linspace stash.

Caddy terminates TLS and limits request bodies. This service verifies SSH
signatures with short-lived, single-use challenges before changing public data.
It listens on a systemd-activated Unix socket (fd 3), or on --socket PATH.
"""
import argparse
import base64
import hashlib
import hmac
import http.server
import os
import socket
import socketserver
import secrets
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
import re

MAX_SIZE = 1024 * 1024
CHANNEL = re.compile(r'^/stash/download([0-7])$')
CLEAR = '/stash/clear'
DATA = Path('/var/lib/stashd')
PROTOCOL = 'linspace-stash-v1'
CHALLENGE_TTL = 90


def signing_message(domain, method, path, data, challenge):
    return '\n'.join((PROTOCOL, 'https://' + domain, method, path,
                      hashlib.sha256(data).hexdigest(), challenge, '')).encode('ascii')


class Authentication:
    """Stateless issuance, bounded replay tracking, and OpenSSH verification."""

    def __init__(self, domain, allowed_signers, clock=time.time):
        self.domain = domain
        self.allowed_signers = Path(allowed_signers)
        self.clock = clock
        # Restarting invalidates all outstanding challenges, including used ones.
        self.secret = secrets.token_bytes(32)
        self.used = {}
        self.lock = threading.Lock()
        self.verifiers = threading.BoundedSemaphore(4)

    def challenge(self):
        value = f'{secrets.token_hex(32)}.{int(self.clock()) + CHALLENGE_TTL}'
        return value + '.' + hmac.new(self.secret, value.encode(), 'sha256').hexdigest()

    def valid_challenge(self, challenge):
        if not re.fullmatch(r'[0-9a-f]{64}\.[0-9]{10,12}\.[0-9a-f]{64}', challenge):
            return False
        value, mac = challenge.rsplit('.', 1)
        expires = int(value.split('.')[1])
        now = self.clock()
        return now < expires <= now + CHALLENGE_TTL and hmac.compare_digest(
            mac, hmac.new(self.secret, value.encode(), 'sha256').hexdigest())

    def authorize(self, method, path, data, challenge, encoded_signature):
        if not self.valid_challenge(challenge) or not 0 < len(encoded_signature) <= 8192:
            return 401
        try:
            signature = base64.b64decode(encoded_signature, validate=True)
        except ValueError:
            return 401
        if not signature.startswith(b'-----BEGIN SSH SIGNATURE-----\n') or len(signature) > 6144:
            return 401
        with self.lock:
            if challenge in self.used:
                return 401
        if not self.verifiers.acquire(blocking=False):
            return 429
        try:
            with tempfile.TemporaryDirectory(prefix='stash-signature-') as temporary:
                sigfile = Path(temporary) / 'signature'
                sigfile.write_bytes(signature)
                result = subprocess.run(['ssh-keygen', '-Y', 'verify', '-f', str(self.allowed_signers),
                                         '-I', 'stash', '-n', 'linspace-stash@' + self.domain,
                                         '-s', str(sigfile)],
                                        input=signing_message(self.domain, method, path, data, challenge),
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
                if result.returncode:
                    return 401
        except (OSError, subprocess.TimeoutExpired):
            return 503
        finally:
            self.verifiers.release()
        # Two parallel copies may both verify, but only one can consume a challenge.
        with self.lock:
            now = self.clock()
            self.used = {nonce: expiry for nonce, expiry in self.used.items() if expiry > now}
            if challenge in self.used or not self.valid_challenge(challenge):
                return 401
            if len(self.used) >= 8192:
                return 429
            self.used[challenge] = int(challenge.split('.')[1])
        return 204


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'stashd/1'
    sys_version = ''
    timeout = 30

    def log_message(self, format, *args):
        print(format % args, file=sys.stderr, flush=True)

    def reply(self, code, text='', close=False):
        body = (text + '\n').encode() if text else b''
        if close:
            self.close_connection = True
        self.send_response(code)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if code == 401:
            self.send_header('WWW-Authenticate', 'SSH-Signature realm="linspace-stash"')
        if code != 204:
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
        if close:
            self.send_header('Connection', 'close')
        self.end_headers()
        if body and self.command != 'HEAD':
            self.wfile.write(body)

    def request_path(self):
        # Exact origin-form targets only: queries and encoded aliases are not signed routes.
        return self.path

    def declared_length(self):
        """Return the Content-Length, or None when the body length cannot be trusted."""
        if self.headers.get_all('Transfer-Encoding') or len(self.headers.get_all('Content-Length', [])) != 1:
            return None
        try:
            value = self.headers['Content-Length']
            if not re.fullmatch(r'[0-9]+', value):
                return None
            length = int(value)
        except ValueError:
            return None
        return length if length >= 0 else None

    def authenticate(self, data):
        headers = ('X-Linspace-Challenge', 'X-Linspace-Signature')
        if any(len(self.headers.get_all(name, [])) != 1 for name in headers):
            self.reply(401, 'An authorized SSH signature is required.', close=True)
            return False
        code = self.server.auth.authorize(self.command, self.path, data, *(self.headers[name] for name in headers))
        if code != 204:
            self.reply(code, 'SSH authorization failed; obtain a new challenge and retry.' if code == 401 else 'Authentication is busy or unavailable.', close=True)
            return False
        return True

    def do_PUT(self):
        match = CHANNEL.match(self.request_path())
        if not match:
            return self.reply(404, 'Unknown channel.', close=True)
        length = self.declared_length()
        if length is None:
            return self.reply(411, 'A valid Content-Length is required.', close=True)
        if length > MAX_SIZE:
            return self.reply(413, 'The body exceeds 1 MiB.', close=True)
        if not self.headers.get('X-Linspace-Signature'):
            return self.reply(401, 'An authorized SSH signature is required.', close=True)
        data = self.rfile.read(length)
        if len(data) != length:
            return self.reply(400, 'The body is shorter than Content-Length.', close=True)
        if b'\0' in data:
            return self.reply(415, 'Only text is accepted; the body contains NUL bytes.')
        try:
            data.decode('utf-8')
        except UnicodeDecodeError:
            return self.reply(415, 'Only UTF-8 text is accepted.')
        if not self.authenticate(data):
            return
        target = DATA / f'download{match.group(1)}'
        descriptor, temporary = tempfile.mkstemp(prefix='.new-', dir=DATA)
        try:
            with os.fdopen(descriptor, 'wb') as out:
                out.write(data)
                out.flush()
                os.fsync(out.fileno())
            os.chmod(temporary, 0o644)
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
        self.reply(204)

    def do_POST(self):
        if self.request_path() != CLEAR:
            return self.reply(404, 'Not found.', close=True)
        if self.declared_length() != 0:
            return self.reply(400, 'No body is expected.', close=True)
        if not self.authenticate(b''):
            return
        for index in range(8):
            (DATA / f'download{index}').unlink(missing_ok=True)
        self.reply(204)

    def do_GET(self):
        if self.path == '/stash/challenge':
            return self.reply(200, self.server.auth.challenge(), close=True)
        self.reply(405, 'Only PUT and POST are served here.', close=True)

    def do_HEAD(self):
        if self.path == '/stash/challenge':
            return self.reply(200, '', close=True)
        self.reply(405, close=True)

    def do_unsupported(self):
        self.reply(405, close=True)

    do_DELETE = do_PATCH = do_OPTIONS = do_unsupported


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    address_family = socket.AF_UNIX
    daemon_threads = True

    def __init__(self, *args, **kwargs):
        self.connections = threading.BoundedSemaphore(32)
        super().__init__(*args, **kwargs)

    def process_request(self, request, address):
        if not self.connections.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except BaseException:
            self.connections.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.connections.release()

    def handle_error(self, request, client_address):
        error = sys.exc_info()[1]
        if isinstance(error, (BrokenPipeError, ConnectionResetError, TimeoutError)):
            print(f'client connection dropped: {error}', file=sys.stderr, flush=True)
        else:
            super().handle_error(request, client_address)


def main():
    global DATA
    parser = argparse.ArgumentParser(description='Write side of linspace stash.')
    parser.add_argument('--socket', help='listen on this Unix socket instead of the systemd-activated one')
    parser.add_argument('--data', default=str(DATA), help='directory holding download0..download7')
    parser.add_argument('--domain', required=True, help='exact HTTPS hostname bound into every signature')
    parser.add_argument('--allowed-signers', type=Path, required=True)
    args = parser.parse_args()
    DATA = Path(args.data)
    if os.geteuid() == 0:
        sys.exit('Error: refusing to run as root.')
    os.umask(0o022)
    DATA.mkdir(mode=0o755, exist_ok=True)
    if not re.fullmatch(r'[a-z0-9.-]+', args.domain) or not args.allowed_signers.is_file():
        sys.exit('Error: valid domain and allowed-signers file are required.')
    server = Server('', Handler, bind_and_activate=False)
    server.auth = Authentication(args.domain, args.allowed_signers)
    server.socket.close()
    if os.environ.get('LISTEN_FDS') == '1' and os.environ.get('LISTEN_PID') == str(os.getpid()):
        server.socket = socket.socket(fileno=3)
    elif args.socket:
        Path(args.socket).unlink(missing_ok=True)
        server.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.socket.bind(args.socket)
        os.chmod(args.socket, 0o660)
        server.socket.listen(16)
    else:
        sys.exit('Error: no systemd socket was passed; use --socket PATH to run by hand.')
    server.server_address = server.socket.getsockname()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
