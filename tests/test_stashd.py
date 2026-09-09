"""Exercise the stash writer over a temporary Unix socket, without Caddy or root."""
import http.client
import importlib.util
import socket
import tempfile
import threading
import unittest
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
        for path in stashd.DATA.iterdir():
            path.unlink()

    def request(self, method, path, body=None, headers=None):
        connection = UnixConnection(self.path)
        try:
            try:
                connection.request(method, path, body=body, headers=headers or {})
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


if __name__ == '__main__':
    unittest.main()
