#!/usr/bin/env python3
"""Write side of linspace stash.

Caddy terminates TLS, authenticates every request with basic_auth and limits the
body size before proxying PUT /stash/download[0-7] and POST /stash/clear here.
This service only validates that the body is UTF-8 text and writes the channel
file atomically. It listens on the systemd-activated Unix socket (fd 3), or on
--socket PATH when started by hand.
"""
import argparse
import http.server
import os
import socket
import socketserver
import sys
import tempfile
import urllib.parse
from pathlib import Path
import re

MAX_SIZE = 1024 * 1024
CHANNEL = re.compile(r'^/stash/download([0-7])$')
CLEAR = '/stash/clear'
DATA = Path('/var/lib/stashd')


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
        if code != 204:
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
        if close:
            self.send_header('Connection', 'close')
        self.end_headers()
        if body and self.command != 'HEAD':
            self.wfile.write(body)

    def request_path(self):
        """Return the path component; the proxy may send an absolute-form request target."""
        return urllib.parse.urlsplit(self.path).path

    def declared_length(self):
        """Return the Content-Length, or None when the body length cannot be trusted."""
        if 'chunked' in self.headers.get('Transfer-Encoding', '').lower():
            return None
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            return None
        return length if length >= 0 else None

    def do_PUT(self):
        match = CHANNEL.match(self.request_path())
        if not match:
            return self.reply(404, 'Unknown channel.', close=True)
        length = self.declared_length()
        if length is None:
            return self.reply(411, 'A valid Content-Length is required.', close=True)
        if length > MAX_SIZE:
            # Drain what the proxy is willing to forward so that it can report 413 itself.
            self.rfile.read(MAX_SIZE + 1)
            return self.reply(413, 'The body exceeds 1 MiB.', close=True)
        data = self.rfile.read(length)
        if len(data) != length:
            return self.reply(400, 'The body is shorter than Content-Length.', close=True)
        if b'\0' in data:
            return self.reply(415, 'Only text is accepted; the body contains NUL bytes.')
        try:
            data.decode('utf-8')
        except UnicodeDecodeError:
            return self.reply(415, 'Only UTF-8 text is accepted.')
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
        for index in range(8):
            (DATA / f'download{index}').unlink(missing_ok=True)
        self.reply(204)

    def do_GET(self):
        self.reply(405, 'Only PUT and POST are served here.', close=True)

    def do_HEAD(self):
        self.reply(405, close=True)

    do_DELETE = do_PATCH = do_OPTIONS = do_GET


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    address_family = socket.AF_UNIX
    daemon_threads = True

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
    args = parser.parse_args()
    DATA = Path(args.data)
    if os.geteuid() == 0:
        sys.exit('Error: refusing to run as root.')
    os.umask(0o022)
    DATA.mkdir(mode=0o755, exist_ok=True)
    server = Server('', Handler, bind_and_activate=False)
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
