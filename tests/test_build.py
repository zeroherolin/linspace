import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build
import deploy


class BuildTests(unittest.TestCase):
    def test_custom_domain_rendering_release_integrity_and_tamper_detection(self):
        with tempfile.TemporaryDirectory(prefix='linspace-build-test-') as tmp:
            root = Path(tmp)
            key = root / 'id_ed25519'
            subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)], check=True)
            config = root / 'site.json'
            config.write_text(json.dumps({'domain': 'custom.example.test', 'site_name': 'Site <test>', 'icp_number': '', 'ssh_public_key_file': str(key) + '.pub', 'claude_settings_file': str(ROOT / 'config/claude/settings.json')}))
            release = build.build(config, root / 'dist', internal=True)
            meta, identifier = deploy.checked_release(release)
            self.assertTrue(meta['ssh_enabled'])
            self.assertTrue(meta['internal_test'])
            self.assertEqual((release / 'site/ssh/key.pub').read_bytes(), Path(str(key) + '.pub').read_bytes())
            for path in release.rglob('*'):
                if path.is_file() and path.suffix != '.dat':
                    self.assertNotIn('linspace.xyz', path.read_text())
                    self.assertNotIn('@@DOMAIN@@', path.read_text())
            self.assertIn('https://custom.example.test', (release / 'site/mihomo/install').read_text())
            self.assertIn('https://custom.example.test/stash', (release / 'site/stash/upload7').read_text())
            self.assertIn('Site &lt;test&gt;', (release / 'site/index.html').read_text())
            self.assertIn('custom.example.test {', (release / 'config/Caddyfile').read_text())
            self.assertNotIn('ssh_public_key_file', (release / 'release.json').read_text())
            sha = hashlib.sha256((root / 'dist/linspace-site.tar.gz').read_bytes()).hexdigest()
            release = build.build(config, root / 'dist', internal=True)
            self.assertEqual(hashlib.sha256((root / 'dist/linspace-site.tar.gz').read_bytes()).hexdigest(), sha)
            for _ in range(2):
                result = subprocess.run(['bash', str(release / 'linspace'), '--internal-test', '--dry-run'], text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('No host changes made', result.stdout)
                deploy.checked_release(release)
            result = subprocess.run(['bash', str(release / 'linspace'), '--dry-run'], text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('internal-test', result.stderr)
            extra = release / 'site/extra'
            extra.write_text('unlisted')
            with self.assertRaises(ValueError):
                deploy.checked_release(release)
            extra.unlink()
            (release / 'site/claude/config').write_text('{"tampered":true}')
            with self.assertRaises(ValueError):
                deploy.checked_release(release)

    def test_no_key_means_no_public_key_or_route(self):
        with tempfile.TemporaryDirectory(prefix='linspace-build-test-') as tmp:
            root = Path(tmp)
            config = root / 'site.json'
            config.write_text(json.dumps({'domain': 'second.example.test', 'site_name': 'Second site', 'icp_number': '', 'ssh_public_key_file': '', 'claude_settings_file': str(ROOT / 'config/claude/settings.json')}))
            release = build.build(config, root / 'dist', internal=True)
            self.assertFalse((release / 'site/ssh/key.pub').exists())
            self.assertNotIn('/ssh/key.pub', (release / 'config/Caddyfile').read_text())
            self.assertFalse(json.loads((release / 'release.json').read_text())['ssh_enabled'])
