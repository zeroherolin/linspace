import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def test_configure_upgrades_old_profile_and_rejects_invalid_codex_without_replacing_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = root / 'site.json'
            profile.write_text(json.dumps({'domain': 'cli.example.test', 'site_name': 'CLI', 'icp_number': '', 'ssh_public_key_file': '', 'claude_settings_file': 'config/claude/settings.json'}))

            def command(name, *args):
                return subprocess.run([sys.executable, str(ROOT / 'scripts/cli.py'), name, '--config', str(profile), '--internal-test', *args], capture_output=True, text=True)

            result = command('configure', '--non-interactive')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(profile.read_text())['codex_config_file'], 'config/codex/config.toml')
            self.assertEqual(json.loads(profile.read_text())['ssh_public_key_name'], 'key.pub')
            custom = root / 'shared.toml'
            custom.write_text('model_reasoning_effort = "high"\n')
            result = command('configure', '--non-interactive', '--codex-config-file', str(custom))
            self.assertEqual(result.returncode, 0, result.stderr)
            saved = profile.read_bytes()
            urls = command('urls')
            self.assertEqual(urls.returncode, 0, urls.stderr)
            paths = [line.removeprefix('https://cli.example.test/') for line in urls.stdout.splitlines()]
            self.assertLess(paths.index('claude/config'), paths.index('codex/install'))
            self.assertLess(paths.index('codex/install'), paths.index('codex/config'))
            self.assertLess(paths.index('codex/config'), paths.index('codex/models_1m'))
            self.assertLess(paths.index('codex/models_1m'), paths.index('stash/upload0'))
            custom.write_text('not valid TOML')
            result = command('configure', '--non-interactive', '--codex-config-file', str(custom))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('valid UTF-8 TOML', result.stderr)
            self.assertEqual(profile.read_bytes(), saved)
            self.assertFalse((root / '.site-pending.json').exists())

    def test_configured_ssh_filename_is_saved_and_used_in_urls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = root / 'site.json'
            profile.write_text(json.dumps({'domain': 'keys.example.test', 'site_name': 'Keys', 'icp_number': '', 'ssh_public_key_file': ''}))

            def command(name, *args):
                return subprocess.run([sys.executable, str(ROOT / 'scripts/cli.py'), name, '--config', str(profile), '--internal-test', *args], capture_output=True, text=True)

            result = command('configure', '--non-interactive', '--ssh-public-key-name', 'team.pub')
            self.assertEqual(result.returncode, 0, result.stderr)
            saved = json.loads(profile.read_text())
            self.assertEqual(saved['ssh_public_key_name'], 'team.pub')
            key = root / 'test_key'
            subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-C', 'test-key', '-f', str(key)], check=True)
            # Use an isolated source path without overwriting the real checkout's
            # ignored key through the configure command's copy operation.
            saved['ssh_public_key_file'] = str(key) + '.pub'
            profile.write_text(json.dumps(saved))
            result = command('urls')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('https://keys.example.test/ssh/team.pub', result.stdout)
            self.assertNotIn('/ssh/key.pub', result.stdout)
            before = profile.read_bytes()
            result = command('configure', '--non-interactive', '--ssh-public-key-name', '../other.pub')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('ssh_public_key_name', result.stderr)
            self.assertEqual(profile.read_bytes(), before)
