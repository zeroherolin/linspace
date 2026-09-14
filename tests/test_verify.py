import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import verify


class VerificationTests(unittest.TestCase):
    @staticmethod
    def response(domain, path, method='HEAD', local=False, scheme='https'):
        if scheme == 'http':
            return 308, {'location': f'https://{domain}/'}
        if path == '/not-published':
            return 404, {}
        if method in ('PUT', 'POST'):
            return 401, {}
        asset = '/assets/' in path
        return 200, {'content-type': 'text/html' if path in ('/', '/help') else 'application/octet-stream' if asset else 'text/plain', 'cache-control': 'immutable' if asset else 'no-store', 'x-content-type-options': 'nosniff'}

    def test_codex_config_and_hosted_installer_are_required(self):
        meta = {'domain': 'verify.example.test', 'ssh_enabled': False}
        with patch.object(verify, 'probe', side_effect=self.response) as probe, contextlib.redirect_stdout(io.StringIO()):
            verify.verify(meta)
        self.assertTrue(any(call.args[1] == '/codex/config' for call in probe.call_args_list))
        self.assertTrue(any(call.args[1] == '/codex/install' for call in probe.call_args_list))
        self.assertTrue(any(call.args[1] == '/codex/models_1m' for call in probe.call_args_list))
        self.assertTrue(any(call.args[1] == '/codex/auth' for call in probe.call_args_list))
        self.assertTrue(any(call.args[1] == '/help' for call in probe.call_args_list))
        for broken_path in ['/codex/config', '/codex/models_1m', '/codex/auth', '/codex/install']:
            def broken(domain, path, *args, **kwargs):
                if path == broken_path:
                    return (302, {'location': 'https://wrong.example.test/'}) if path.endswith('/install') else (404, {})
                return self.response(domain, path, *args, **kwargs)
            with self.subTest(path=broken_path), patch.object(verify, 'probe', side_effect=broken), self.assertRaises(RuntimeError):
                verify.verify(meta, quiet=True)

    def test_ssh_verification_uses_the_published_filename_and_supports_older_metadata(self):
        for values, expected in [({}, ['/ssh/key.pub']), ({'ssh_public_key_name': 'team.pub'}, ['/ssh/team.pub']), ({'ssh_enabled': False, 'ssh_public_key_name': 'team.pub'}, [])]:
            meta = {'domain': 'keys.example.test', 'ssh_enabled': True, **values}
            with self.subTest(values=values), patch.object(verify, 'probe', side_effect=self.response) as probe, contextlib.redirect_stdout(io.StringIO()):
                verify.verify(meta)
            self.assertEqual([call.args[1] for call in probe.call_args_list if call.args[1].startswith('/ssh/')], expected)

    def test_all_stash_reads_and_alias_are_checked_without_writes(self):
        meta = {'domain': 'verify.example.test', 'ssh_enabled': False}
        expected = {(method, path) for method in ('HEAD', 'GET')
                    for path in ['/stash/download', *[f'/stash/download{n}' for n in range(8)]]}
        for status in (200, 404):
            requests = []

            def response(domain, path, method='HEAD', local=False, scheme='https'):
                requests.append((method, path))
                result = self.response(domain, path, method, local, scheme)
                if (method, path) in expected:
                    self.assertTrue(local)
                    return status, {**result[1], 'content-length': '0'}
                return result

            with self.subTest(status=status), patch.object(verify, 'probe', side_effect=response), contextlib.redirect_stderr(io.StringIO()):
                verify.verify(meta, local=True, quiet=True)
            self.assertEqual({item for item in requests if item in expected}, expected)
            self.assertEqual([item for item in requests if item[0] in ('PUT', 'POST')],
                             [('POST', '/stash/clear'), ('PUT', '/stash/download0')])

    def test_each_stash_read_failure_is_reported(self):
        for path in ['/stash/download', *[f'/stash/download{n}' for n in range(8)]]:
            for method in ('HEAD', 'GET'):
                for status in (301, 401, 403, 405, 500):
                    def response(domain, requested_path, requested_method='HEAD', local=False, scheme='https'):
                        if (requested_path, requested_method) == (path, method):
                            return status, self.response(domain, path)[1]
                        return self.response(domain, requested_path, requested_method, local, scheme)

                    with self.subTest(path=path, method=method, status=status), patch.object(verify, 'probe', side_effect=response):
                        with self.assertRaisesRegex(RuntimeError, method + ' ' + path):
                            verify.verify({'domain': 'verify.example.test', 'ssh_enabled': False}, quiet=True)

    def test_stash_read_headers_are_required_for_existing_and_missing_channels(self):
        for status in (200, 404):
            for method in ('HEAD', 'GET'):
                for header, value in [('content-type', 'text/html'), ('cache-control', 'public'),
                                      ('x-content-type-options', '')]:
                    def response(domain, path, requested_method='HEAD', local=False, scheme='https'):
                        result = self.response(domain, path, requested_method, local, scheme)
                        if path == '/stash/download7' and requested_method == method:
                            return status, {**result[1], header: value}
                        return result

                    with self.subTest(status=status, method=method, header=header), patch.object(verify, 'probe', side_effect=response):
                        with self.assertRaisesRegex(RuntimeError, method + ' /stash/download7'):
                            verify.verify({'domain': 'verify.example.test', 'ssh_enabled': False}, quiet=True)

    def test_probe_get_discards_and_bounds_body_without_sending_a_write_payload(self):
        def request(command, **kwargs):
            Path(command[command.index('-D') + 1]).write_text('HTTP/1.1 200 OK\nContent-Type: text/plain\n')
            self.assertEqual(command[command.index('-o') + 1], '/dev/null')
            self.assertEqual(command[command.index('-X') + 1], 'GET')
            self.assertEqual(command[command.index('--max-filesize') + 1], str(1024 * 1024))
            self.assertNotIn('-H', command)
            self.assertNotIn('-L', command)
            return type('Response', (), {'returncode': 0, 'stdout': '200'})()

        with patch.object(verify.subprocess, 'run', side_effect=request):
            self.assertEqual(verify.probe('verify.example.test', '/stash/download0', 'GET'),
                             (200, {'content-type': 'text/plain'}))
