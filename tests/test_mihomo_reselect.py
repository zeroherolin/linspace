"""Restart reselects a working proxy with the same ordered search as import."""
import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'vendor/pyyaml.zip'))
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('mihomo_sub_reselect', ROOT / 'src/mihomo/sub.py')
sub = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sub)


class ReselectTests(unittest.TestCase):
    def run_reselect(self, names, now, healthy):
        calls = {'control': [], 'selected': [], 'probed': []}

        def api(path, method='GET', body=None, *, sock=None, timeout=5):
            self.assertIsNone(sock, 'restart must talk to the live process, not a trial socket')
            if path == '/proxies':
                return {'proxies': {sub.GROUP: {'type': 'Selector', 'all': list(names), 'now': now}}}
            if method == 'PUT':
                calls['selected'].append(body['name'])
                return None
            self.fail(f'unexpected API call {method} {path}')

        def probe_node(name, sock=None):
            calls['probed'].append(name)
            return name in healthy

        with patch.object(sub, 'CONFIG', Path('/dev/null')), patch.object(sub, 'ROOT', Path('/dev')), \
             patch.object(sub, 'control', side_effect=lambda action, check=True: calls['control'].append(action)), \
             patch.object(sub, 'active', return_value=True), \
             patch.object(sub, 'wait_ready'), patch.object(sub, 'verify_proxy_request') as live, \
             patch.object(sub, 'api', side_effect=api), patch.object(sub, 'probe_node', side_effect=probe_node), \
             patch.object(sub, 'linspace_log'):
            # ROOT / 'proxies.yaml' must exist: /dev/null stands in for both managed files.
            with patch.object(Path, 'is_file', lambda self: str(self) in ('/dev/null', '/dev/proxies.yaml')):
                sub.reselect()
        return calls, live

    def test_restart_keeps_a_working_selection_without_probing_others(self):
        # 'c' is selected and healthy while 'a' also works: the selection must not move back to 'a'.
        calls, live = self.run_reselect(['a', 'b', 'c'], now='c', healthy={'a', 'c'})
        self.assertEqual(calls['control'], ['restart'])
        self.assertEqual(calls['probed'], ['c'])
        self.assertEqual(calls['selected'], [])
        live.assert_called_once()

    def test_restart_switches_to_the_first_working_node_when_the_selection_fails(self):
        calls, _ = self.run_reselect(['a', 'b', 'c', 'd'], now='b', healthy={'c', 'd'})
        # The failed node is checked once, then the subscription is walked in order without it.
        self.assertEqual(calls['probed'], ['b', 'a', 'c'])
        self.assertEqual(calls['selected'], ['c'])

    def test_restart_without_a_valid_selection_searches_the_whole_subscription(self):
        calls, _ = self.run_reselect(['a', 'b'], now='gone', healthy={'b'})
        self.assertEqual(calls['probed'], ['a', 'b'])
        self.assertEqual(calls['selected'], ['b'])

    def test_restart_fails_without_changing_the_selection_when_nothing_works(self):
        with self.assertRaisesRegex(RuntimeError, 'No proxy passed'):
            self.run_reselect(['a', 'b'], now='a', healthy=set())

    def test_restart_requires_an_imported_subscription(self):
        with patch.object(sub, 'CONFIG', Path('/nonexistent/config.yaml')), self.assertRaisesRegex(RuntimeError, 'No subscription is imported'):
            sub.reselect()

    def test_reselect_flag_takes_no_source_and_import_still_reads_argv(self):
        self.assertIsNone(sub.read_source(['--reselect']))
        self.assertEqual(sub.read_source(['https://example.test/sub']), 'https://example.test/sub')
        with patch('argparse.ArgumentParser.error', side_effect=SystemExit(2)) as error:
            with self.assertRaises(SystemExit):
                sub.read_source(['--reselect', 'https://example.test/sub'])
        self.assertIn('takes no subscription', error.call_args.args[0])

    def test_import_and_restart_share_one_ordered_search(self):
        selected = []
        with patch.object(sub, 'probe_node', side_effect=lambda name, sock=None: name == 'second'), \
             patch.object(sub, 'api', side_effect=lambda path, method='GET', body=None, sock=None, timeout=5: selected.append((body['name'], sock))), \
             patch.object(sub, 'linspace_log'):
            self.assertEqual(sub.first_available(['first', 'second', 'third'], sock='trial'), 'second')
            self.assertIsNone(sub.first_available(['first', 'third']))
        self.assertEqual(selected, [('second', 'trial')])



class ProbeTests(unittest.TestCase):
    """Nodes are probed through the provider, which newer Mihomo releases no longer list under /proxies."""

    def probe(self, alive=True):
        calls = []
        provider = '/providers/proxies/my-sub/Los%20Angeles%2001'

        def api(path, method='GET', body=None, *, sock=None, timeout=5):
            calls.append(path)
            if path.startswith('/proxies/'):  # what v1.19.33 answers for a provider's node
                raise sub.subprocess.CalledProcessError(22, 'curl')
            if path.startswith(provider + '/healthcheck?'):
                return {'delay': 640}
            if path == provider:
                return {'extra': {sub.CHECK_URL: {'alive': alive, 'history': [{'delay': 640 if alive else 0}]}}}
            self.fail(f'unexpected API call {path}')

        with patch.object(sub, 'api', side_effect=api):
            result = sub.probe_node('Los Angeles 01', sock='trial')
        return result, calls

    def test_a_working_node_passes_through_the_provider_routes(self):
        result, calls = self.probe()
        self.assertTrue(result)
        self.assertFalse(any(c.startswith('/proxies/') for c in calls))
        self.assertIn('url=https%3A%2F%2Fwww.google.com', calls[0])

    def test_the_managed_group_is_probed_where_it_is_configured(self):
        # The live check probes PROXY itself; groups are never in the provider.
        self.assertEqual(sub.outbound_paths(sub.GROUP), ('/proxies/PROXY', '/proxies/PROXY/delay'))
        self.assertEqual(sub.outbound_paths(sub.AUTO), ('/proxies/AUTO', '/proxies/AUTO/delay'))
        node = '/providers/proxies/my-sub/Los%20Angeles%2001'
        self.assertEqual(sub.outbound_paths('Los Angeles 01'), (node, node + '/healthcheck'))
        calls = []

        def api(path, method='GET', body=None, *, sock=None, timeout=5):
            calls.append(path)
            if path.startswith('/providers/'):
                raise sub.subprocess.CalledProcessError(22, 'curl')
            if path.startswith('/proxies/PROXY/delay?'):
                return {'delay': 670}
            if path == '/proxies/PROXY':
                return {'extra': {sub.CHECK_URL: {'alive': True, 'history': [{'delay': 670}]}}}
            self.fail(f'unexpected API call {path}')

        with patch.object(sub, 'api', side_effect=api):
            self.assertTrue(sub.probe_node(sub.GROUP))
        self.assertEqual(len(calls), 2)

    def test_a_delay_without_a_passing_record_fails(self):
        # Mihomo returns a delay even for an unexpected status; only the URL's record tells.
        result, _ = self.probe(alive=False)
        self.assertFalse(result)


class SiteVersionTests(unittest.TestCase):
    """A site that offers a newer Mihomo must not break import or restart on an older install."""

    def setUp(self):
        sub.installed_version.cache_clear()
        self.addCleanup(sub.installed_version.cache_clear)

    def test_installed_version_comes_from_the_binary(self):
        output = 'Mihomo Meta v1.19.27 linux amd64 with go1.26.4 Sat Jun  6 07:43:19 UTC 2026\nUse tags: with_gvisor\n'
        with patch.object(sub.subprocess, 'run', return_value=SimpleNamespace(stdout=output)):
            self.assertEqual(sub.installed_version(), 'v1.19.27')
        sub.installed_version.cache_clear()
        with patch.object(sub.subprocess, 'run', side_effect=OSError), self.assertRaisesRegex(RuntimeError, 'Cannot read the installed'):
            sub.installed_version()

    def wait(self, running):
        with patch.object(sub, 'SITE_VERSION', 'v1.19.33'), patch.object(sub, 'installed_version', return_value='v1.19.27'), \
             patch.object(sub, 'active', return_value=True), patch.object(sub, 'control', return_value=SimpleNamespace(stdout='42\n')), \
             patch.object(sub, 'owned_ports', return_value=True), patch.object(sub, 'api', return_value={'version': running}), \
             patch.object(sub.time, 'sleep'):
            sub.wait_ready()

    def test_the_installed_version_is_ready_while_the_site_offers_a_newer_one(self):
        self.wait('v1.19.27')

    def test_a_process_older_than_the_installed_binary_is_named(self):
        with self.assertRaisesRegex(RuntimeError, 'running mihomo is v1.19.26, but v1.19.27 is installed'):
            self.wait('v1.19.26')

    def test_a_newer_site_version_is_only_pointed_out(self):
        with patch.object(sub, 'SITE_VERSION', 'v1.19.33'), patch.object(sub, 'installed_version', return_value='v1.19.27'), \
             patch.object(sub, 'linspace_log') as log:
            sub.notice_site_version()
        self.assertEqual([c.args[0] for c in log.call_args_list], ['WARN', 'INFO'])
        self.assertIn('v1.19.27 is installed; this site provides v1.19.33', log.call_args_list[0].args[1])
        self.assertIn('/mihomo/install', log.call_args_list[1].args[1])
        with patch.object(sub, 'SITE_VERSION', 'v1.19.27'), patch.object(sub, 'installed_version', return_value='v1.19.27'), \
             patch.object(sub, 'linspace_log') as log:
            sub.notice_site_version()
        log.assert_not_called()

    def test_geoip_is_checked_against_the_installed_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'GeoIP.dat').write_bytes(b'snapshot')
            record = root / 'geoip.sha256'
            record.write_text(hashlib.sha256(b'snapshot').hexdigest() + '  /var/lib/mihomo/GeoIP.dat\n')
            with patch.object(sub, 'ROOT', root), patch.object(sub, 'GEO_RECORD', record):
                sub.check_geoip()
                (root / 'GeoIP.dat').write_bytes(b'other')
                with self.assertRaisesRegex(RuntimeError, 'snapshot installed with mihomo'):
                    sub.check_geoip()
                record.unlink()
                with self.assertRaisesRegex(RuntimeError, 'snapshot installed with mihomo'):
                    sub.check_geoip()



process_spec = importlib.util.spec_from_file_location('mihomo_process', ROOT / 'src/mihomo/process.py')
process = importlib.util.module_from_spec(process_spec)
process_spec.loader.exec_module(process)


class ProcessHelperTests(unittest.TestCase):
    """The installed helper waits for the binary installed beside it, whatever the site offers."""

    def test_ready_compares_with_the_installed_binary(self):
        output = 'Mihomo Meta v1.19.27 linux amd64 with go1.26.4\n'
        with patch.object(process, 'SITE_VERSION', 'v1.19.33'), \
             patch.object(process.subprocess, 'run', return_value=SimpleNamespace(stdout=output)):
            self.assertEqual(process.installed_version(), 'v1.19.27')
        with patch.object(process.subprocess, 'run', side_effect=OSError), patch.object(process, 'SITE_VERSION', 'v1.19.33'):
            self.assertEqual(process.installed_version(), 'v1.19.33')

    def test_wait_ready_accepts_a_process_running_the_installed_version(self):
        seen = []
        with patch.object(process, 'installed_version', return_value='v1.19.27'), \
             patch.object(process, 'running_pid', return_value=42), \
             patch.object(process, 'ready', side_effect=lambda pid, version=None: seen.append(version) or True):
            self.assertEqual(process.wait_ready(), 42)
        self.assertEqual(seen, ['v1.19.27'])


class ControlTests(unittest.TestCase):
    """A failed helper call is reported with its reason, never as a bare exception name."""

    def test_the_helper_reason_is_reported(self):
        stderr = '[linspace] ERROR mihomo is not ready. Check the log and port conflicts.\n'
        with patch.object(sub.subprocess, 'run', return_value=SimpleNamespace(returncode=1, stdout='', stderr=stderr)):
            with self.assertRaisesRegex(RuntimeError, 'Could not start mihomo: mihomo is not ready. Check the log'):
                sub.control('start')
        with patch.object(sub.subprocess, 'run', return_value=SimpleNamespace(returncode=3, stdout='', stderr='')):
            self.assertEqual(sub.control('is-active', check=False).returncode, 3)
            with self.assertRaisesRegex(RuntimeError, 'Could not stop mihomo: exit 3'):
                sub.control('stop')


class PortTests(unittest.TestCase):
    """Another program on 127.0.0.1:7890 is named before anything changes."""

    def test_a_listener_on_the_proxy_port_is_named(self):
        holder = 'clash (pid 4242)'
        with patch.object(sub, 'port_holder', return_value=holder):
            with self.assertRaisesRegex(RuntimeError, r'127\.0\.0\.1:7890 is already in use by clash \(pid 4242\)'):
                sub.ensure_port_free()
        with patch.object(sub, 'port_holder', return_value=None):
            sub.ensure_port_free()

    def test_restart_checks_the_port_only_when_nothing_runs(self):
        with patch.object(sub, 'CONFIG', Path('/dev/null')), patch.object(sub, 'ROOT', Path('/dev')), \
             patch.object(Path, 'is_file', lambda self: str(self) in ('/dev/null', '/dev/proxies.yaml')), \
             patch.object(sub, 'active', return_value=False), patch.object(sub, 'linspace_log'), \
             patch.object(sub, 'port_holder', return_value='other (pid 7)'), patch.object(sub, 'control') as control:
            with self.assertRaisesRegex(RuntimeError, 'already in use by other'):
                sub.reselect()
        control.assert_not_called()

if __name__ == '__main__':
    unittest.main()
