"""Destructive lifecycle operations are exercised only in temporary homes."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'src/lifecycle'))
import common
import clients
import mihomo
import build


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='linspace-lifecycle-')
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name).resolve() / 'home'
        self.home.mkdir()
        self.environment = patch.dict(os.environ, {'HOME': str(self.home), 'PATH': '/usr/bin:/bin',
            'CODEX_HOME': str(self.home / '.codex'), 'CLAUDE_CONFIG_DIR': str(self.home / '.claude'),
            'XDG_DATA_HOME': str(self.home / '.local/share'), 'XDG_CACHE_HOME': str(self.home / '.cache')}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        if not sys.platform.startswith('linux'):
            processes = patch.object(common, 'process_table', return_value={})
            processes.start()
            self.addCleanup(processes.stop)

    def file(self, relative, text='fixture', executable=False):
        path = self.home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        if executable:
            path.chmod(0o755)
        return path

    def fixture(self, name):
        executable = self.file(f'.local/share/linspace/{name}/release/bin/{name}', '#!/bin/sh\nexit 0\n', True)
        launcher = self.home / '.local/bin' / name
        launcher.parent.mkdir(parents=True, exist_ok=True)
        launcher.symlink_to(executable)
        return executable, launcher

    def test_codex_removes_both_sources_and_credentials_preserving_history(self):
        self.fixture('codex')
        official = self.file('.codex/packages/standalone/releases/old/bin/codex')
        (official.parents[3] / 'current').symlink_to(official.parents[1])
        preserved = [self.file('.codex/sessions/2026/session.jsonl'), self.file('.codex/archived_sessions/old.jsonl'),
                     self.file('.codex/history.jsonl'), self.file('.codex/session_index.jsonl'), self.file('.codex/state_5.sqlite')]
        removed = [self.file('.codex/auth.json'), self.file('.codex/config.toml'), self.file('.codex/models-1m.json'),
                   self.file('.codex/log/cli.log'), self.file('.codex/auth.json.backup.old'), self.file('.cache/linspace/codex/digest')]
        profiles = [self.file('.bashrc'), self.file('.zshrc')]
        client = clients.Client('codex', self.home, system=False).discover()
        with patch.object(client, 'logout'):
            client.uninstall()
        self.assertTrue(all(path.read_text() == 'fixture' for path in preserved + profiles))
        self.assertFalse(any(path.exists() for path in removed))
        self.assertFalse((self.home / '.local/bin/codex').is_symlink())
        self.assertFalse((self.home / '.codex/packages').exists())
        with patch.object(clients.Client, 'logout'):
            clients.Client('codex', self.home, system=False).discover().uninstall()

    def test_claude_removes_native_and_legacy_keeping_only_conversations(self):
        self.fixture('claude')
        self.file('.local/share/claude/versions/1.0.0')
        self.file('.claude/local/node_modules/old')
        self.file('.claude/settings.json')
        self.file('.claude/.credentials.json')
        self.file('.claude.json')
        self.file('.claude.json.backup.old')
        self.file('.claude/projects/project/session.jsonl')
        self.file('.claude/history.jsonl')
        client = clients.Client('claude', self.home, system=False).discover()
        with patch.object(client, 'logout'):
            client.uninstall()
        self.assertEqual({p.name for p in (self.home / '.claude').iterdir()}, {'projects', 'history.jsonl'})
        self.assertFalse((self.home / '.local/share/claude').exists())
        self.assertFalse(list(self.home.glob('.claude.json*')))

    def test_preview_preserves_every_file_and_does_not_logout(self):
        self.fixture('codex')
        self.file('.codex/auth.json')
        before = {str(p): p.read_bytes() for p in self.home.rglob('*') if p.is_file()}
        client = clients.Client('codex', self.home, system=False).discover()
        with patch.object(client, 'logout') as logout:
            client.uninstall(dry_run=True)
            logout.assert_called_once_with(True)
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.home.rglob('*') if p.is_file()})

    def test_broad_and_symlinked_state_paths_are_refused_before_deletion(self):
        for value in (str(self.home), '/', '/etc', str(self.home / '.config')):
            with self.subTest(value=value), patch.dict(os.environ, {'CODEX_HOME': value}), self.assertRaises(ValueError):
                clients.Client('codex', self.home, system=False).discover()
        target = self.home / 'personal'
        target.mkdir()
        (self.home / '.codex').symlink_to(target)
        with self.assertRaises(ValueError):
            common.clear_history_except(self.home / '.codex', lambda _: False)
        self.assertTrue(target.exists())

    def test_symlink_removal_never_follows_data_target(self):
        external = self.file('other/private.txt')
        link = self.home / 'cache-link'
        link.symlink_to(external.parent)
        common.remove(link)
        self.assertTrue(external.is_file())

    def test_operation_lock_blocks_concurrent_mutation_and_cleans_up(self):
        with common.client_lock('codex'):
            with self.assertRaises(RuntimeError):
                with common.client_lock('codex'):
                    self.fail('Two client operations acquired the same lock')
        self.assertFalse((self.home / '.local/state/linspace/locks/codex').exists())

    def test_logout_uses_each_custom_home_before_files_are_removed(self):
        _, launcher = self.fixture('codex')
        self.file('.codex/auth.json')
        custom = self.home / 'custom-codex'
        custom.mkdir()
        (custom / 'auth.json').write_text('secret')
        with patch.dict(os.environ, {'CODEX_HOME': str(custom)}):
            client = clients.Client('codex', self.home, system=False).discover()
            with patch.object(clients, 'run', return_value=subprocess.CompletedProcess([], 0, '', '')) as run:
                client.logout(False)
            self.assertEqual({call.kwargs['env']['CODEX_HOME'] for call in run.call_args_list}, {str(custom), str(self.home / '.codex')})

    def test_failed_logout_leaves_installation_and_history_untouched(self):
        executable, launcher = self.fixture('codex')
        secret = self.file('.codex/auth.json')
        client = clients.Client('codex', self.home, system=False).discover()
        with patch.object(clients, 'run', return_value=subprocess.CompletedProcess([], 1, '', '')), self.assertRaises(RuntimeError):
            client.uninstall()
        self.assertTrue(executable.exists() and launcher.exists() and secret.exists())

    def test_npm_requires_original_manager_and_does_not_remove_other_packages(self):
        package = self.file('.npm-global/lib/node_modules/@openai/codex/package.json', json.dumps({'name': '@openai/codex'})).parent
        other = self.file('.npm-global/lib/node_modules/other/package.json', '{}')
        client = clients.Client('codex', self.home, system=False).discover()
        self.assertIn(package, client.npm)
        with self.assertRaises(RuntimeError):
            client.uninstall()
        self.assertTrue(package.exists() and other.exists())

    def test_desktop_bundle_is_never_a_cli_uninstall_target(self):
        executable = self.file('Desktop.app/Contents/Resources/codex', '#!/bin/sh\necho codex-cli 0.154.0\n', True)
        (self.home / '.local/bin').mkdir(parents=True)
        (self.home / '.local/bin/codex').symlink_to(executable)
        client = clients.Client('codex', self.home, system=False).discover()
        self.assertFalse(client.launchers)
        with self.assertRaises(ValueError):
            clients.Client('codex', self.home, system=False).discover([str(executable)])

    def test_shared_version_manager_binary_is_never_removed(self):
        shim = self.file('tools/shared-shim', '#!/bin/sh\necho codex-cli 0.154.0\n', True)
        (self.home / '.local/bin').mkdir(parents=True)
        (self.home / '.local/bin/codex').symlink_to(shim)
        with self.assertRaises(ValueError):
            clients.Client('codex', self.home, system=False).discover()
        self.assertTrue(shim.exists())

    def test_yarn_style_package_launcher_is_removed_by_its_manager(self):
        root = '.config/yarn/global/node_modules/@openai/codex'
        package = self.file(root + '/package.json', json.dumps({'name': '@openai/codex'})).parent
        target = self.file(root + '/bin/codex.js', '#!/bin/sh\necho codex-cli 0.154.0\n', True)
        other = self.file('.config/yarn/global/node_modules/other/package.json', '{}')
        launcher = self.home / '.local/bin/codex'
        launcher.parent.mkdir(parents=True)
        launcher.symlink_to(target)
        client = clients.Client('codex', self.home, system=False)
        client.managers = [(['fixture-yarn', 'global', 'remove', '@openai/codex'], None)]
        client.discover()
        self.assertIn(package, client.manager_roots)
        def uninstall(args, **kwargs):
            self.assertEqual(args, client.managers[0][0])
            shutil.rmtree(package)
            return subprocess.CompletedProcess(args, 0, '', '')
        with patch.object(client, 'logout'), patch.object(clients, 'run', side_effect=uninstall):
            client.uninstall()
        self.assertFalse(launcher.is_symlink())
        self.assertTrue(other.exists())

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Real process-stop verification runs in disposable Linux containers')
    def test_stop_matches_identity_and_leaves_unrelated_process_alive(self):
        script = self.file('program.py', 'import time\ntime.sleep(60)\n')
        other = self.file('unrelated.py', 'import time\ntime.sleep(60)\n')
        selected = subprocess.Popen([sys.executable, str(script)], start_new_session=True)
        unrelated = subprocess.Popen([sys.executable, str(other)], start_new_session=True)
        try:
            common.stop_processes({str(script)})
            selected.wait(timeout=3)
            self.assertIsNone(unrelated.poll())
        finally:
            for process in (selected, unrelated):
                if process.poll() is None:
                    process.kill()
                process.wait()

    def test_source_and_wrapper_render_uninstall_routes(self):
        config = self.file('site.json', json.dumps({'domain': 'lifecycle.example.test', 'site_name': 'Lifecycle', 'icp_number': '', 'ssh_public_key_file': '', 'claude_settings_file': str(ROOT / 'config/claude/settings.json')}))
        release = build.build(config, self.home / 'dist', internal=True)
        for name in ('codex', 'claude', 'mihomo'):
            script = release / 'site' / name / 'uninstall'
            self.assertIn('/' + name + '/uninstall', (release / 'config/Caddyfile').read_text())
            result = subprocess.run(['bash', str(script), '--help'], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('--dry-run', result.stdout)
            text = script.read_text().rsplit('main "$@"', 1)[0]
            result = subprocess.run(['bash', '-s'], input=text, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
