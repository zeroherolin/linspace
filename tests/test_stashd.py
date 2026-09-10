"""Exercise the stash writer over a temporary Unix socket, without Caddy or root."""
import http.client
import base64
import concurrent.futures
import importlib.util
import socket
import subprocess
import tempfile
import threading
import unittest
import time
from pathlib import Path

spec = importlib.util.spec_from_file_location('stashd', Path(__file__).resolve().parents[1] / 'src/stash/stashd.py')
stashd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stashd)


class QuietHandler(stashd.Handler):
    def log_message(self, format, *args):
        pass


class UnixConnection(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__('stashd', timeout=5)
        self.path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)


class StashProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='linspace-test-', dir='/tmp')
        cls.root = Path(cls.temporary.name)
        cls.key = cls.root / 'signer'
        cls.other_key = cls.root / 'unauthorized'
        for key in (cls.key, cls.other_key):
            subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)], check=True)
        cls.signers = cls.root / 'allowed_signers'
        cls.signers.write_text('stash namespaces="linspace-stash@stash.example.test" ' + Path(str(cls.key) + '.pub').read_text())
        stashd.DATA = cls.root / 'data'
        stashd.DATA.mkdir()
        cls.path = str(cls.root / 'writer.sock')
        cls.server = stashd.Server('', QuietHandler, bind_and_activate=False)
        cls.server.socket.bind(cls.path)
        cls.server.socket.listen(16)
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join(timeout=5)
        cls.temporary.cleanup()

    def setUp(self):
        self.server.auth = stashd.Authentication('stash.example.test', self.signers)
        for path in stashd.DATA.iterdir():
            path.unlink()

    def signed_headers(self, method, path, body=b'', key=None, challenge=None, domain='stash.example.test'):
        challenge = challenge or self.server.auth.challenge()
        result = subprocess.run(['ssh-keygen', '-Y', 'sign', '-f', str(key or self.key),
                                 '-n', 'linspace-stash@stash.example.test', '-'],
                                input=stashd.signing_message(domain, method, path, body, challenge), capture_output=True, check=True)
        return {'X-Linspace-Challenge': challenge, 'X-Linspace-Signature': base64.b64encode(result.stdout).decode()}

    def request(self, method, path, body=None, headers=None, signed=True):
        headers = dict(headers or {})
        if signed and method in ('PUT', 'POST') and 'X-Linspace-Signature' not in headers:
            headers.update(self.signed_headers(method, path, body or b''))
        connection = UnixConnection(self.path)
        try:
            try:
                connection.request(method, path, body=body, headers=headers)
            except BrokenPipeError:
                # A handler can reject the headers and close before the body is sent.
                # Read its response so assertions still check the actual HTTP status.
                pass
            response = connection.getresponse()
            result = response.status, response.read()
            return result
        finally:
            connection.close()

    def test_all_channels_and_overwrite(self):
        for channel in range(8):
            value = f'channel {channel}: \u2603\n'.encode()
            self.assertEqual(self.request('PUT', f'/stash/download{channel}', value)[0], 204)
            self.assertEqual((stashd.DATA / f'download{channel}').read_bytes(), value)
        self.assertEqual(self.request('PUT', '/stash/download7', b'replaced')[0], 204)
        target = stashd.DATA / 'download7'
        self.assertEqual(target.read_bytes(), b'replaced')
        self.assertEqual(target.stat().st_mode & 0o777, 0o644)
        self.assertFalse(list(stashd.DATA.glob('.new-*')))

    def test_invalid_text_preserves_previous_file(self):
        self.request('PUT', '/stash/download0', b'original')
        for data in (b'bad\x00text', b'\xff'):
            self.assertEqual(self.request('PUT', '/stash/download0', data)[0], 415)
            self.assertEqual((stashd.DATA / 'download0').read_bytes(), b'original')

    def test_size_boundary(self):
        self.assertEqual(self.request('PUT', '/stash/download0', b'a' * stashd.MAX_SIZE)[0], 204)
        self.assertEqual(self.request('PUT', '/stash/download0', b'b' * (stashd.MAX_SIZE + 1))[0], 413)
        self.assertEqual((stashd.DATA / 'download0').stat().st_size, stashd.MAX_SIZE)

    def test_empty_file_and_clear(self):
        self.assertEqual(self.request('PUT', '/stash/download0', b'')[0], 204)
        self.assertTrue((stashd.DATA / 'download0').exists())
        self.request('PUT', '/stash/download7', b'hello')
        self.assertEqual(self.request('POST', '/stash/clear')[0], 204)
        self.assertFalse(list(stashd.DATA.iterdir()))

    def test_route_and_method_boundaries(self):
        self.assertEqual(self.request('GET', '/')[0], 405)
        self.assertEqual(self.request('PUT', '/stash/download8', b'x')[0], 404)
        self.assertEqual(self.request('POST', '/stash/clear', b'x')[0], 400)
        self.assertEqual(self.request('POST', '/other')[0], 404)

    def test_chunked_input_rejected(self):
        status, _ = self.request('PUT', '/stash/download0', b'0\r\n\r\n', {'Transfer-Encoding': 'chunked'})
        self.assertEqual(status, 411)
        self.assertFalse((stashd.DATA / 'download0').exists())

    def test_unsigned_legacy_and_untrusted_key_writes_are_rejected(self):
        for method, path, body in [('PUT', '/stash/download0', b'data'), ('POST', '/stash/clear', b'')]:
            for headers in ({}, {'Authorization': 'Basic c3Rhc2g6dG9rZW4='}, self.signed_headers(method, path, body, key=self.other_key)):
                with self.subTest(method=method, headers=list(headers)):
                    self.assertEqual(self.request(method, path, body, headers, signed=False)[0], 401)
        self.assertFalse(list(stashd.DATA.iterdir()))

    def test_signature_binds_content_path_method_and_domain(self):
        path = '/stash/download0'
        headers = self.signed_headers('PUT', path, b'original')
        self.assertEqual(self.request('PUT', path, b'tampered', headers)[0], 401)
        self.assertEqual(self.request('PUT', '/stash/download1', b'original', headers)[0], 401)
        self.assertEqual(self.request('POST', '/stash/clear', b'', headers)[0], 401)
        wrong_site = self.signed_headers('PUT', path, b'original', domain='other.example.test')
        self.assertEqual(self.request('PUT', path, b'original', wrong_site)[0], 401)
        self.assertEqual(self.request('PUT', path, b'original', headers)[0], 204)
        self.assertEqual(self.request('PUT', path, b'original', headers)[0], 401)
        self.assertEqual((stashd.DATA / 'download0').read_bytes(), b'original')

    def test_replayed_parallel_write_succeeds_only_once(self):
        headers = self.signed_headers('PUT', '/stash/download0', b'one write')
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.request('PUT', '/stash/download0', b'one write', headers)[0], range(2)))
        self.assertEqual(sorted(results), [204, 401])

    def test_expired_forged_and_pre_restart_challenges_fail(self):
        now = time.time()
        self.server.auth.clock = lambda: now
        headers = self.signed_headers('POST', '/stash/clear')
        self.server.auth.clock = lambda: now + stashd.CHALLENGE_TTL + 1
        self.assertEqual(self.request('POST', '/stash/clear', b'', headers)[0], 401)
        self.server.auth = stashd.Authentication('stash.example.test', self.signers)
        self.assertEqual(self.request('POST', '/stash/clear', b'', headers)[0], 401)
        for challenge in ('x', self.server.auth.challenge()[:-1] + 'z'):
            forged = self.signed_headers('POST', '/stash/clear', challenge=challenge)
            self.assertEqual(self.request('POST', '/stash/clear', b'', forged)[0], 401)
        for signature in ('not base64!', base64.b64encode(b'not an SSH signature').decode()):
            headers = {'X-Linspace-Challenge': self.server.auth.challenge(), 'X-Linspace-Signature': signature}
            self.assertEqual(self.request('POST', '/stash/clear', b'', headers)[0], 401)

    def test_challenge_endpoint_is_stateless_and_replay_storage_is_bounded(self):
        for _ in range(10):
            code, body = self.request('GET', '/stash/challenge')
            self.assertEqual(code, 200)
            self.assertTrue(self.server.auth.valid_challenge(body.decode().strip()))
        self.assertEqual(self.server.auth.used, {})
        self.server.auth.used = {str(i): time.time() + 60 for i in range(8192)}
        self.assertEqual(self.request('POST', '/stash/clear', b'')[0], 429)
        self.assertEqual(len(self.server.auth.used), 8192)

    def test_exact_signed_routes_and_missing_content_length(self):
        self.assertEqual(self.request('PUT', '/stash/download0?extra=1', b'x')[0], 404)
        connection = UnixConnection(self.path)
        try:
            connection.putrequest('PUT', '/stash/download0')
            connection.endheaders()
            response = connection.getresponse()
            self.assertEqual(response.status, 411)
            response.read()
        finally:
            connection.close()


if __name__ == '__main__':
    unittest.main()
