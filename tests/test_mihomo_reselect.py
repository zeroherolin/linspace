"""Restart reselects a working proxy with the same ordered search as import."""
import importlib.util
from pathlib import Path
import sys
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


if __name__ == '__main__':
    unittest.main()
