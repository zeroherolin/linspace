"""Run rendered curl | bash clients against an isolated TLS writer and SSH agent."""
import importlib.util
import os
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build

spec = importlib.util.spec_from_file_location('client_test_writer', ROOT / 'src/stash/stashd.py')
writer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(writer)


class TLSHandler(writer.Handler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == '/stash/keys':
            return self.reply(200, self.server.public_key.strip())
        if self.path == '/stash/clear' or self.path.startswith('/stash/upload'):
            action = self.path.rsplit('/', 1)[1]
            source = 'src/stash/clear.sh' if action == 'clear' else 'src/stash/upload.sh.in'
            script = build.render(source, {'DOMAIN': self.server.auth.domain}).replace('__CHANNEL__', action.removeprefix('upload'))
            return self.reply(200, script)
        super().do_GET()


class TLSServer(writer.Server):
    address_family = socket.AF_INET


class StashClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='stash-tls-', dir='/tmp')
        cls.root = Path(cls.temporary.name)
        cls.key = cls.root / 'signer'
        cls.other_key = cls.root / 'other'
        for key in (cls.key, cls.other_key):
            subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)], check=True)
        cert_config = cls.root / 'openssl.cnf'
        cert_config.write_text('[req]\ndistinguished_name=dn\nx509_extensions=ext\nprompt=no\n[dn]\nCN=localhost\n[ext]\nsubjectAltName=DNS:localhost\nbasicConstraints=critical,CA:TRUE\n')
        cls.certificate = cls.root / 'certificate.pem'
        private = cls.root / 'certificate.key'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                        '-config', str(cert_config), '-keyout', str(private), '-out', str(cls.certificate)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        writer.DATA = cls.root / 'data'
        writer.DATA.mkdir()
        cls.server = TLSServer(('127.0.0.1', 0), TLSHandler)
        cls.domain = 'localhost:' + str(cls.server.server_port)
        cls.server.public_key = Path(str(cls.key) + '.pub').read_text()
        cls.signers = cls.root / 'allowed_signers'
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cls.certificate, private)
        cls.server.socket = context.wrap_socket(cls.server.socket, server_side=True)
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join(timeout=5)
        cls.temporary.cleanup()

    def setUp(self):
        self.signers.write_text(f'stash namespaces="linspace-stash@{self.domain}" {self.server.public_key}')
        self.server.auth = writer.Authentication(self.domain, self.signers)
        for path in writer.DATA.iterdir():
            path.unlink()
        self.client_dir = tempfile.TemporaryDirectory(prefix='client-', dir=self.root)
        self.addCleanup(self.client_dir.cleanup)
        self.client_home = Path(self.client_dir.name) / 'home with spaces'
        self.client_home.mkdir()
        self.env = dict(os.environ, HOME=str(self.client_home), SSH_AUTH_SOCK='',
                        PATH=str(Path(sys.executable).parent) + os.pathsep + os.environ['PATH'],
                        CURL_CA_BUNDLE=str(self.certificate), NO_PROXY='localhost', no_proxy='localhost')
        self.env.pop('STASH_IDENTITY', None)
        self.env.pop('BASH_ENV', None)
        self.env.pop('ENV', None)
        self.input = Path(self.client_dir.name) / 'text with spaces.txt'
        self.input.write_bytes('hello\n雪\n'.encode())

    def install_key(self, name='id_ed25519', key=None):
        directory = self.client_home / '.ssh'
        directory.mkdir(exist_ok=True)
        destination = directory / name
        shutil.copy2(key or self.key, destination)
        shutil.copy2(str(key or self.key) + '.pub', str(destination) + '.pub')
        return destination

    def run_client(self, action, *args):
        return subprocess.run(['bash', '-c', 'set -o pipefail; curl -q -fsSL "$1" | bash -s -- "${@:2}"',
                               'stash-test', f'https://{self.domain}/stash/{action}', *map(str, args)],
                              env=self.env, cwd=self.client_home, capture_output=True, text=True, timeout=30)

    def test_default_key_uploads_every_channel_and_clears_without_identity_argument(self):
        self.install_key()
        for channel in range(8):
            result = self.run_client(f'upload{channel}', self.input)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((writer.DATA / f'download{channel}').read_bytes(), self.input.read_bytes())
        result = self.run_client('clear')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(list(writer.DATA.iterdir()))

    def test_custom_key_pair_is_discovered_and_standard_key_can_derive_missing_public_file(self):
        custom = self.install_key('work identity')
        result = self.run_client('upload0', self.input)
        self.assertEqual(result.returncode, 0, result.stderr)
        custom.unlink()
        Path(str(custom) + '.pub').unlink()
        standard = self.install_key()
        Path(str(standard) + '.pub').unlink()
        result = self.run_client('upload1', self.input)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unrelated_invalid_public_file_does_not_block_key_discovery(self):
        unrelated = self.install_key(key=self.other_key)
        Path(str(unrelated) + '.pub').write_bytes(b'\xffinvalid public key')
        self.install_key('work identity')
        result = self.run_client('upload0', self.input)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_agent_only_signing_without_a_local_key_pair(self):
        agent_socket = Path(self.client_dir.name) / 'agent.sock'
        agent = subprocess.Popen(['ssh-agent', '-D', '-a', str(agent_socket)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 5
            while not agent_socket.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(agent_socket.exists())
            self.env['SSH_AUTH_SOCK'] = str(agent_socket)
            subprocess.run(['ssh-add', str(self.other_key), str(self.key)], env=self.env, check=True, capture_output=True)
            result = self.run_client('upload0', self.input)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((self.client_home / '.ssh').exists())
            self.assertEqual((writer.DATA / 'download0').read_bytes(), self.input.read_bytes())
        finally:
            agent.terminate()
            agent.wait(timeout=5)

    def test_explicit_identity_environment_and_revocation(self):
        self.env['STASH_IDENTITY'] = str(self.key)
        result = self.run_client('upload0', self.input)
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.run_client('upload1', self.input, '-i', self.other_key)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('not authorized', result.stderr)
        self.signers.write_text('')
        result = self.run_client('clear')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('401', result.stderr)
        self.assertEqual((writer.DATA / 'download0').read_bytes(), self.input.read_bytes())

    def test_public_key_alone_and_legacy_token_do_not_authorize_uploads(self):
        self.install_key(key=self.other_key)
        (self.client_home / '.ssh/authorized_keys').write_text(self.server.public_key)
        result = self.run_client('upload0', self.input)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('No authorized SSH identity', result.stderr)
        result = self.run_client('upload0', self.input, '-t', 'legacy-token')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(list(writer.DATA.iterdir()))

    def test_invalid_files_are_rejected_before_upload(self):
        self.install_key()
        for data in (b'a' * (writer.MAX_SIZE + 1), b'bad\0text', b'\xff'):
            with self.subTest(size=len(data)):
                self.input.write_bytes(data)
                result = self.run_client('upload0', self.input)
                self.assertNotEqual(result.returncode, 0)
        self.assertFalse(list(writer.DATA.iterdir()))
