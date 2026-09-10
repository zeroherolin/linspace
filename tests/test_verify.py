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
        return 200, {'content-type': 'text/html' if path == '/' else 'application/octet-stream' if asset else 'text/plain', 'cache-control': 'immutable' if asset else 'no-store', 'x-content-type-options': 'nosniff'}

    def test_codex_config_and_hosted_installer_are_required(self):
        meta = {'domain': 'verify.example.test', 'ssh_enabled': False}
        with patch.object(verify, 'probe', side_effect=self.response) as probe, contextlib.redirect_stdout(io.StringIO()):
            verify.verify(meta)
        self.assertTrue(any(call.args[1] == '/codex/config' for call in probe.call_args_list))
        self.assertTrue(any(call.args[1] == '/codex/install' for call in probe.call_args_list))
        self.assertTrue(any(call.args[1] == '/codex/models_1m' for call in probe.call_args_list))
        self.assertTrue(any(call.args[1] == '/codex/auth' for call in probe.call_args_list))
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
