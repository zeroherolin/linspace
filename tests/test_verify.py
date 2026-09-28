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
        return 200, {'content-type': 'text/html' if path in ('/', '/help', '/help2') else 'application/octet-stream' if asset else 'text/plain', 'cache-control': 'immutable' if asset else 'no-store', 'x-content-type-options': 'nosniff'}

    def test_codex_config_and_hosted_installer_are_required(self):
        meta = {'domain': 'verify.example.test', 'ssh_enabled': False}
        with patch.object(verify, 'probe', side_effect=self.response) as probe, contextlib.redirect_stdout(io.StringIO()):
            verify.verify(meta)
        self.assertTrue(any(call.args[1] == '/codex/config' for call in probe.call_args_list))
        self.assertTrue(any(call.args[1] == '/codex/install' for call in probe.call_args_list))
        self.assertTrue(any(call.args[1] == '/codex/models_1m' for call in probe.call_args_list))
        self.assertTrue(any(call.args[1] == '/codex/auth' for call in probe.call_args_list))
        self.assertTrue(any(call.args[1] == '/tmux/install' for call in probe.call_args_list))
        self.assertTrue(any(call.args[1] == '/tmux/uninstall' for call in probe.call_args_list))
        self.assertTrue(any(call.args[1] == '/tmux/config' for call in probe.call_args_list))
        self.assertTrue(any(call.args[1] == '/help' for call in probe.call_args_list))
        self.assertTrue(any(call.args[1] == '/help2' for call in probe.call_args_list))
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

    def test_alias_hostnames_must_redirect_to_the_canonical_domain(self):
        meta = {'domain': 'verify.example.test', 'alias_domains': ['www.verify.example.test'], 'ssh_enabled': False}
        seen = []

        def redirecting(domain, path, method='HEAD', local=False, scheme='https'):
            if domain == 'www.verify.example.test':
                seen.append((scheme, path))
                target = f'https://verify.example.test{path}' if scheme == 'https' else f'https://{domain}/'
                return 308, {'location': target}
            return self.response(domain, path, method, local, scheme)

        with patch.object(verify, 'probe', side_effect=redirecting), contextlib.redirect_stderr(io.StringIO()):
            verify.verify(meta, quiet=True)
        self.assertIn(('https', '/stash/download0?x=1'), seen)
        self.assertIn(('http', '/'), seen)

        def serving(domain, path, method='HEAD', local=False, scheme='https'):
            if domain == 'www.verify.example.test':
                return 200, {'content-type': 'text/html'}
            return self.response(domain, path, method, local, scheme)

        with patch.object(verify, 'probe', side_effect=serving), self.assertRaisesRegex(RuntimeError, 'www.verify.example.test'):
            verify.verify(meta, quiet=True)

        def dropping_path(domain, path, method='HEAD', local=False, scheme='https'):
            if domain == 'www.verify.example.test':
                return 308, {'location': 'https://verify.example.test/'}
            return self.response(domain, path, method, local, scheme)

        with patch.object(verify, 'probe', side_effect=dropping_path), self.assertRaisesRegex(RuntimeError, '/help'):
            verify.verify(meta, quiet=True)

    PAGE_META = {'domain': 'verify.example.test', 'ssh_enabled': False, 'page_domain': 'page.verify.example.test'}
    PAGE_HEADERS = {'cache-control': 'no-store', 'x-content-type-options': 'nosniff', 'x-robots-tag': 'noindex, nofollow'}

    def page_response(self, domain, path, method='HEAD', local=False, scheme='https', output='/dev/null'):
        if domain == 'page.verify.example.test':
            if path == '/':
                return 308, {**self.PAGE_HEADERS, 'location': 'https://verify.example.test/'}
            if path == '/robots.txt':
                return 200, {**self.PAGE_HEADERS, 'content-type': 'text/plain'}
            return 404, {**self.PAGE_HEADERS, 'content-type': 'text/plain; charset=utf-8'}
        if method == 'DELETE':
            return 401, {}
        return self.response(domain, path, method, local, scheme)

    @classmethod
    def page_script(cls, domain, path, local=False):
        name, action = path.strip('/').split('/')
        headers = {**cls.PAGE_HEADERS, 'content-type': 'text/plain; charset=utf-8'}
        if name == 'Not_A_Page':
            return 200, headers, "echo '[linspace] ERROR Invalid page name. Use ...' >&2\nexit 1\n"
        return 200, headers, f"main('https://verify.example.test', 'page-{action}', page='{name}')\n"

    def test_page_host_is_checked_read_only_and_the_scripts_must_carry_the_name(self):
        with patch.object(verify, 'probe', side_effect=self.page_response) as probe, \
             patch.object(verify, 'fetch', side_effect=self.page_script) as fetch, contextlib.redirect_stderr(io.StringIO()):
            verify.verify(self.PAGE_META, quiet=True)
        writes = [(call.args[2], call.args[1]) for call in probe.call_args_list if len(call.args) > 2 and call.args[2] not in ('HEAD', 'GET')]
        self.assertEqual(writes, [('POST', '/stash/clear'), ('PUT', '/stash/download0'),
                                  ('PUT', '/stash/page/linspace-verify'), ('DELETE', '/stash/page/linspace-verify')])
        self.assertEqual([call.args[1] for call in fetch.call_args_list], ['/linspace-verify/upload', '/linspace-verify/delete', '/Not_A_Page/upload'])
        page_paths = {call.args[1] for call in probe.call_args_list if call.args[0] == 'page.verify.example.test'}
        self.assertEqual(page_paths, {'/linspace-verify', '/robots.txt', '/Not_A_Page', '/linspace-verify/source', '/'})

    def test_page_host_failures_are_reported(self):
        def unrendered(domain, path, local=False):
            status, headers, _ = self.page_script(domain, path, local)
            return status, headers, "page='[[linspace: placeholder \"http.regexp.page.1\" ]]'\n"

        def bare_invalid_name(domain, path, local=False):
            # The invalid-name handler is missing, so the name falls through to the 404 route.
            return (404, {**self.PAGE_HEADERS, 'content-type': 'text/plain'}, 'Not found') if path.startswith('/Not_A_Page/') else self.page_script(domain, path, local)

        def replace(target, status=None, headers=None):
            def response(domain, path, method='HEAD', local=False, scheme='https', output='/dev/null'):
                result = self.page_response(domain, path, method, local, scheme)
                if (domain, path, method) == target:
                    return status if status is not None else result[0], {**result[1], **(headers or {})}
                return result
            return response

        page = 'page.verify.example.test'
        cases = [('unrendered script', self.page_response, unrendered),
                 ('invalid name without explanation', self.page_response, bare_invalid_name),
                 ('indexable page', replace((page, '/linspace-verify', 'HEAD'), headers={'x-robots-tag': ''}), self.page_script),
                 ('cached page', replace((page, '/linspace-verify', 'HEAD'), 200, {'content-type': 'text/html', 'cache-control': 'max-age=60'}), self.page_script),
                 ('page served as text', replace((page, '/linspace-verify', 'HEAD'), 200), self.page_script),
                 ('root serves content', replace((page, '/', 'HEAD'), 200), self.page_script),
                 ('extra route', replace((page, '/linspace-verify/source', 'HEAD'), 200), self.page_script),
                 ('pages disabled in stashd', replace(('verify.example.test', '/stash/page/linspace-verify', 'DELETE'), 405), self.page_script)]
        for name, probe, fetch in cases:
            with self.subTest(name), patch.object(verify, 'probe', side_effect=probe), patch.object(verify, 'fetch', side_effect=fetch):
                with self.assertRaises(RuntimeError):
                    verify.verify(self.PAGE_META, quiet=True)
        accepted = replace((page, '/linspace-verify', 'HEAD'), 200, {'content-type': 'text/html; charset=utf-8'})
        with patch.object(verify, 'probe', side_effect=accepted), patch.object(verify, 'fetch', side_effect=self.page_script), contextlib.redirect_stderr(io.StringIO()):
            verify.verify(self.PAGE_META, quiet=True)

    def test_sites_without_a_page_host_never_probe_pages(self):
        with patch.object(verify, 'probe', side_effect=self.response) as probe, patch.object(verify, 'fetch') as fetch, contextlib.redirect_stderr(io.StringIO()):
            verify.verify({'domain': 'verify.example.test', 'ssh_enabled': False, 'page_domain': None}, quiet=True)
        fetch.assert_not_called()
        self.assertFalse([call for call in probe.call_args_list if '/stash/page/' in call.args[1]])

    def test_fetch_keeps_the_body_for_content_checks(self):
        def request(command, **kwargs):
            Path(command[command.index('-D') + 1]).write_text('HTTP/1.1 200 OK\nContent-Type: text/plain\n')
            Path(command[command.index('-o') + 1]).write_text("page='linspace-verify'\n")
            self.assertEqual(command[command.index('--max-filesize') + 1], str(1024 * 1024))
            return type('Response', (), {'returncode': 0, 'stdout': '200'})()

        with patch.object(verify.subprocess, 'run', side_effect=request):
            self.assertEqual(verify.fetch('page.verify.example.test', '/linspace-verify/upload'),
                             (200, {'content-type': 'text/plain'}, "page='linspace-verify'\n"))

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
