import json
import importlib.util
import os
import errno
import pty
import select
import subprocess
import sys
import tempfile
import termios
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build
spec = importlib.util.spec_from_file_location('provider_auth', ROOT / 'src/codex/provider_auth.py')
provider_auth = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provider_auth)


class CodexAuthTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='linspace-auth-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.config_dir = self.root / 'client settings'
        self.auth_file = self.config_dir / 'auth.json'
        self.script = build.render('src/codex/auth.sh.in', {'DOMAIN': 'auth.example.test'})
        # Use Codex's supported directory setting; never touch the test runner's credentials.
        self.env = dict(os.environ, CODEX_HOME=str(self.config_dir))
        self.env['PATH'] = str(Path(sys.executable).parent) + os.pathsep + self.env['PATH']
        # Shell startup hooks must not run through injected failing test commands.
        self.env.pop('BASH_ENV', None)
        self.env.pop('ENV', None)

    def run_script(self, *args, script=None, **env):
        return subprocess.run(['bash', '-s', '--', *args], input=self.script if script is None else script,
                              env={**self.env, **env}, text=True, capture_output=True,
                              start_new_session=True, timeout=10, cwd=self.root)

    def run_interactive(self, token, url='', *args, eof=False):
        """Use a real terminal for /dev/tty while Bash reads the script from stdin."""
        script = self.root / 'interactive.sh'
        script.write_text(self.script)
        master, slave = pty.openpty()
        # A fresh process owns the controlling terminal. No personal shell or
        # credentials are used, and stdin remains redirected like curl | bash.
        setup = ('import fcntl, os, sys, termios; '
                 'fcntl.ioctl(1, termios.TIOCSCTTY, 0); '
                 'os.execvp("bash", ["bash", "-s", "--", *sys.argv[1:]])')
        process = None
        output = bytearray()
        deadline = time.monotonic() + 10

        def read_output():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self.fail('Interactive authentication did not finish')
            if not select.select([master], [], [], remaining)[0]:
                self.fail('Interactive authentication timed out')
            try:
                data = os.read(master, 65536)
            except OSError as error:
                if error.errno != errno.EIO:
                    raise
                data = b''
            output.extend(data)
            return bool(data)

        def wait_prompt(text):
            while text.encode() not in output:
                if not read_output():
                    self.fail('Interactive authentication exited before: ' + text)

        def wait_echo(enabled):
            # Bash may print the prompt just before changing terminal echo.
            while bool(termios.tcgetattr(master)[3] & termios.ECHO) != enabled:
                if time.monotonic() >= deadline:
                    self.fail('Terminal echo did not reach the expected state')
                time.sleep(.005)

        try:
            with script.open('rb') as source:
                process = subprocess.Popen([sys.executable, '-c', setup, *args], stdin=source,
                                           stdout=slave, stderr=slave, start_new_session=True,
                                           cwd=self.root, env={**self.env, 'HOME': str(self.root),
                                               'XDG_CACHE_HOME': str(self.root / 'cache'), 'NO_COLOR': '1'})
            os.close(slave)
            slave = None
            if '-u' not in args and '--base-url' not in args:
                wait_prompt('Codex base_url (Enter to keep current): ')
                self.assertNotIn(b'Codex API token: ', output)
                wait_echo(True)
                os.write(master, b'\x04' if eof else url.encode() + b'\n')
                if eof:
                    while read_output():
                        pass
                    process.wait(timeout=2)
                    return SimpleNamespace(returncode=process.returncode, stdout=output.decode(errors='replace'))
            wait_prompt('Codex API token: ')
            wait_echo(False)
            os.write(master, token.encode() + b'\n')
            while read_output():
                pass
            process.wait(timeout=2)
            return SimpleNamespace(returncode=process.returncode, stdout=output.decode(errors='replace'))
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=2)
            os.close(master)
            if slave is not None:
                os.close(slave)

    def test_interactive_url_is_visible_and_matches_explicit_u_update(self):
        self.config_dir.mkdir()
        config = self.config_dir / 'config.toml'
        original = (b'model_provider = "chosen"\r\n'
                    b'[model_providers.other]\r\nbase_url = "https://other.example/v1"\r\n'
                    b'[model_providers.chosen]\r\nbase_url = "https://old.example/v1" # keep\r\n')
        config.write_bytes(original)
        token, url = 'private-interactive-token', 'https://relay.example/v1'
        explicit = self.run_script('-t', token, '-u', url)
        self.assertEqual(explicit.returncode, 0, explicit.stderr)
        expected_config, expected_auth = config.read_bytes(), self.auth_file.read_bytes()
        config.write_bytes(original)
        self.auth_file.write_text('old credentials')
        result = self.run_interactive(token, url)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertLess(result.stdout.index('Codex base_url'), result.stdout.index('Codex API token'))
        self.assertIn(url, result.stdout)
        self.assertNotIn(token, result.stdout)
        self.assertEqual(config.read_bytes(), expected_config)
        self.assertEqual(self.auth_file.read_bytes(), expected_auth)
        self.assertEqual(config.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.auth_file.stat().st_mode & 0o777, 0o600)
        self.assertEqual({p.name for p in self.config_dir.iterdir()}, {'config.toml', 'auth.json'})

    def test_interactive_empty_url_never_reads_or_changes_config(self):
        self.config_dir.mkdir()
        config = self.config_dir / 'config.toml'
        for original in (None, b'not TOML; preserve bytes\xff'):
            with self.subTest(config=original):
                if original is not None:
                    config.write_bytes(original)
                result = self.run_interactive('hidden-token', '')
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertNotIn('hidden-token', result.stdout)
                self.assertEqual(config.read_bytes() if config.exists() else None, original)
                self.assertEqual(json.loads(self.auth_file.read_text())['OPENAI_API_KEY'], 'hidden-token')

    def test_interactive_invalid_url_or_eof_preserves_existing_files(self):
        self.config_dir.mkdir()
        config = self.config_dir / 'config.toml'
        original = (ROOT / 'config/codex/config.toml').read_bytes()
        config.write_bytes(original)
        self.auth_file.write_text('old credentials')
        for url, eof in [('not-a-url', False), ('https://relay.example:wrong/v1', False), ('', True)]:
            with self.subTest(url=url, eof=eof):
                result = self.run_interactive('new-hidden-token', url, eof=eof)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertNotIn('new-hidden-token', result.stdout)
                self.assertEqual(config.read_bytes(), original)
                self.assertEqual(self.auth_file.read_text(), 'old credentials')
                self.assertEqual({p.name for p in self.config_dir.iterdir()}, {'config.toml', 'auth.json'})

    def test_interactive_explicit_u_skips_the_url_prompt(self):
        self.config_dir.mkdir()
        config = self.config_dir / 'config.toml'
        config.write_bytes((ROOT / 'config/codex/config.toml').read_bytes())
        result = self.run_interactive('hidden-token', '', '-u', 'https://selected.example/v1')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn('Codex base_url', result.stdout)
        self.assertNotIn('hidden-token', result.stdout)
        self.assertIn('https://selected.example/v1', config.read_text())

    def test_piped_script_escapes_token_and_sets_private_permissions(self):
        token = 'test-"\\$(touch${IFS}unexpected)`id`;abc'
        result = self.run_script('-t', token)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.auth_file.read_text()), {'auth_mode': 'apikey', 'OPENAI_API_KEY': token})
        self.assertEqual(self.config_dir.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.auth_file.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(token, result.stdout + result.stderr)
        self.assertFalse((self.root / 'unexpected').exists())
        self.assertEqual(list(self.config_dir.iterdir()), [self.auth_file])

    def test_replacement_keeps_no_backups_and_repeat_is_idempotent(self):
        self.config_dir.mkdir(mode=0o755)
        previous = '{"tokens":{"access_token":"old-test-value"}}\n'
        self.auth_file.write_text(previous)
        self.auth_file.chmod(0o644)
        config = self.config_dir / 'config.toml'
        config.write_text('model = "custom-model"\n')
        for _ in range(2):
            result = self.run_script('--token', 'new-test-value')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn('new-test-value', result.stdout + result.stderr)
        backups = list(self.config_dir.glob('auth.json.backup.*'))
        self.assertEqual(backups, [])
        self.assertEqual(config.read_text(), 'model = "custom-model"\n')
        self.assertEqual(list(self.config_dir.glob('.auth.*')), [])

    def test_invalid_arguments_and_tokens_leave_existing_credentials_untouched(self):
        self.config_dir.mkdir()
        self.auth_file.write_text('existing credentials')
        cases = [(), ('-t',), ('-t', ''), ('-t', 'has space'), ('-t', 'line\nbreak'),
                 ('-t', 'tab\tvalue'), ('-t', 'control\x01value'), ('-t', 'nonascii-é'),
                 ('-t', 'first', '-t', 'second'), ('--unexpected-secret',), ('bare-secret',)]
        for args in cases:
            with self.subTest(args=args):
                result = self.run_script(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.auth_file.read_text(), 'existing credentials')
                self.assertEqual(list(self.config_dir.iterdir()), [self.auth_file])
                for value in args:
                    if len(value) > 3:
                        self.assertNotIn(value, result.stdout + result.stderr)

    def test_help_and_incomplete_download_do_not_write_credentials(self):
        result = self.run_script('--help')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('https://auth.example.test/codex/auth', result.stdout)
        result = self.run_script('-t', 'test-value', script=self.script.split('# Parse the complete function')[0])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.config_dir.exists())

    def test_relative_config_directory_is_rejected(self):
        result = self.run_script('-t', 'test-value', CODEX_HOME='relative-settings')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('absolute path', result.stderr)
        self.assertFalse((self.root / 'relative-settings').exists())

    def test_default_location_uses_the_client_home(self):
        client_home = self.root / 'client home'
        client_home.mkdir()
        result = self.run_script('-t', 'test-value', CODEX_HOME='', HOME=str(client_home))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads((client_home / '.codex/auth.json').read_text())['OPENAI_API_KEY'], 'test-value')
        self.assertFalse(self.config_dir.exists())

    def test_symlink_and_nonregular_auth_destinations_are_rejected(self):
        self.config_dir.mkdir()
        target = self.root / 'unrelated'
        target.write_text('preserve me')
        for destination in (target, self.root / 'absent'):
            with self.subTest(destination=destination.name):
                self.auth_file.symlink_to(destination)
                result = self.run_script('-t', 'test-value')
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(self.auth_file.is_symlink())
                self.auth_file.unlink()
        self.auth_file.mkdir()
        result = self.run_script('-t', 'test-value')
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.auth_file.is_dir())
        self.assertEqual(target.read_text(), 'preserve me')
        self.assertFalse((self.root / 'absent').exists())

    def test_failed_staging_or_replace_preserves_old_auth_and_cleans_temporary_files(self):
        self.config_dir.mkdir()
        self.auth_file.write_text('old-test-value')
        commands = self.root / 'commands'
        commands.mkdir()
        for name in ('mktemp', 'mv'):
            with self.subTest(command=name):
                failing = commands / name
                failing.write_text('#!/bin/sh\nexit 1\n')
                failing.chmod(0o755)
                result = self.run_script('-t', 'new-test-value', PATH=str(commands) + os.pathsep + os.environ['PATH'])
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.auth_file.read_text(), 'old-test-value')
                self.assertEqual(list(self.config_dir.glob('.auth.*')), [])
                for backup in self.config_dir.glob('auth.json.backup.*'):
                    self.assertEqual(backup.read_text(), 'old-test-value')
                    self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
                failing.unlink()

    def test_base_url_changes_only_selected_provider_and_preserves_formatting(self):
        self.config_dir.mkdir()
        config = self.config_dir / 'config.toml'
        original = ("model_provider = 'chosen'\r\n"
                    "[model_providers.other]\r\nbase_url = 'https://old.example/v1'\r\n"
                    "[model_providers.'chosen']\r\nbase_url = 'https://old.example/v1' # keep this\r\n"
                    "wire_api = 'responses'\r\n")
        config.write_bytes(original.encode())
        self.auth_file.write_text('old credentials')
        url = 'https://relay.example/v1'
        for _ in range(2):
            result = self.run_script('-t', 'new-token', '-u', url)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn('new-token', result.stdout + result.stderr)
        expected = original.replace("base_url = 'https://old.example/v1' # keep this", 'base_url = "https://relay.example/v1" # keep this')
        self.assertEqual(config.read_bytes(), expected.encode())
        self.assertEqual(json.loads(self.auth_file.read_text())['OPENAI_API_KEY'], 'new-token')
        self.assertEqual(config.stat().st_mode & 0o777, 0o600)
        backups = list(self.config_dir.glob('config.toml.backup.*'))
        self.assertEqual(backups, [])
        self.assertEqual(len(list(self.config_dir.glob('auth.json.backup.*'))), 0)
        self.assertFalse(list(self.config_dir.glob('.codex-*')))
        # An unchanged token must not short-circuit a different URL update.
        result = self.run_script('-t', 'new-token', '-u', 'https://second.example/v1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b'base_url = "https://second.example/v1" # keep this', config.read_bytes())
        self.assertEqual(len(list(self.config_dir.glob('auth.json.backup.*'))), 0)

    def test_omitting_url_keeps_even_invalid_config_byte_for_byte(self):
        self.config_dir.mkdir()
        config = self.config_dir / 'config.toml'
        config.write_bytes(b'not TOML; leave untouched\xff')
        result = self.run_script('-t', 'new-token')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(config.read_bytes(), b'not TOML; leave untouched\xff')

    def test_url_validation_and_missing_or_invalid_config_preserve_credentials(self):
        self.config_dir.mkdir()
        self.auth_file.write_text('old credentials')
        config = self.config_dir / 'config.toml'
        preset = (ROOT / 'config/codex/config.toml').read_bytes()
        for url in ('', 'not-a-url', 'ftp://relay.example/v1', 'https://', 'https://user:pass@relay.example/v1', 'https://relay.example/v1#fragment', 'https://relay.example:wrong/v1'):
            with self.subTest(url=url):
                config.write_bytes(preset)
                result = self.run_script('-t', 'new-token', '-u', url)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(config.read_bytes(), preset)
                self.assertEqual(self.auth_file.read_text(), 'old credentials')
        for data in (None, b'invalid TOML [', b'model_provider="missing"\n'):
            with self.subTest(config=data):
                if data is None:
                    config.unlink()
                else:
                    config.write_bytes(data)
                result = self.run_script('-t', 'new-token', '--base-url', 'https://relay.example/v1')
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.auth_file.read_text(), 'old credentials')
                self.assertEqual(config.read_bytes() if config.exists() else None, data)
        self.assertFalse(list(self.config_dir.glob('*.backup.*')))

    def test_url_update_rejects_symlink_config_and_duplicate_option(self):
        self.config_dir.mkdir()
        self.auth_file.write_text('old credentials')
        outside = self.root / 'outside.toml'
        outside.write_bytes((ROOT / 'config/codex/config.toml').read_bytes())
        (self.config_dir / 'config.toml').symlink_to(outside)
        result = self.run_script('-t', 'new-token', '-u', 'https://relay.example/v1')
        self.assertNotEqual(result.returncode, 0)
        result = self.run_script('-t', 'new-token', '-u', 'https://one.example/v1', '-u', 'https://two.example/v1')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.auth_file.read_text(), 'old credentials')
        self.assertEqual(outside.read_bytes(), (ROOT / 'config/codex/config.toml').read_bytes())

    def test_second_file_write_failure_restores_the_original_config(self):
        self.config_dir.mkdir()
        config = self.config_dir / 'config.toml'
        preset = (ROOT / 'config/codex/config.toml').read_bytes()
        config.write_bytes(preset)
        self.auth_file.write_text('old credentials')
        replace = os.replace
        def fail_auth(source, destination):
            if destination == self.auth_file:
                raise OSError('injected auth write failure')
            replace(source, destination)
        with patch.object(provider_auth.os, 'replace', side_effect=fail_auth):
            with self.assertRaises(OSError):
                provider_auth.save_pair(self.config_dir, 'https://relay.example/v1', 'new-token')
        self.assertEqual(config.read_bytes(), preset)
        self.assertEqual(self.auth_file.read_text(), 'old credentials')
        self.assertFalse(list(self.config_dir.glob('.codex-*')))
