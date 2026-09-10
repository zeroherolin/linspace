import hashlib
import json
import re
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
            subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-C', 'test-key', '-f', str(key)], check=True)
            config = root / 'site.json'
            config.write_text(json.dumps({'domain': 'custom.example.test', 'site_name': 'Site <test>', 'icp_number': '', 'ssh_public_key_file': str(key) + '.pub', 'ssh_public_key_name': 'team.pub', 'claude_settings_file': str(ROOT / 'config/claude/settings.json')}))
            release = build.build(config, root / 'dist', internal=True)
            meta, identifier = deploy.checked_release(release)
            self.assertTrue(meta['ssh_enabled'])
            self.assertTrue(meta['internal_test'])
            self.assertEqual(meta['ssh_public_key_name'], 'team.pub')
            self.assertEqual(meta['stash_auth'], 'ssh-signature-v1')
            self.assertEqual(meta['stash_key_count'], 1)
            normalized = ' '.join(Path(str(key) + '.pub').read_text().split()[:2])
            self.assertEqual((release / 'site/stash/keys').read_text(), normalized + '\n')
            self.assertEqual((release / 'config/stash.allowed_signers').read_text(), f'stash namespaces="linspace-stash@custom.example.test" {normalized}\n')
            self.assertNotIn('basic_auth', (release / 'config/stash.caddy.template').read_text())
            self.assertNotIn('__HASH__', (release / 'config/stash.caddy.template').read_text())
            self.assertIn('unix//run/stashd/ssh.sock', (release / 'config/stash.caddy.template').read_text())
            self.assertIn('ListenStream=/run/stashd/ssh.sock', (release / 'service/stashd.socket').read_text())
            self.assertEqual((release / 'site/ssh/team.pub').read_bytes(), Path(str(key) + '.pub').read_bytes())
            self.assertFalse((release / 'site/ssh/key.pub').exists())
            for path in release.rglob('*'):
                if path.is_file() and path.suffix not in ('.dat', '.gz'):
                    self.assertNotIn('@@DOMAIN@@', path.read_text())
            self.assertIn('https://custom.example.test', (release / 'site/mihomo/install').read_text())
            self.assertIn('https://custom.example.test/stash', (release / 'site/stash/upload7').read_text())
            self.assertIn('Site &lt;test&gt;', (release / 'site/index.html').read_text())
            self.assertIn('custom.example.test {', (release / 'config/Caddyfile').read_text())
            self.assertEqual(set(re.findall(r'/ssh/[a-zA-Z0-9._-]+', (release / 'config/Caddyfile').read_text())), {'/ssh/team.pub'})
            self.assertIn('/codex/install', (release / 'config/Caddyfile').read_text())
            self.assertTrue((release / 'site/codex/install').read_text().startswith('#!/usr/bin/env bash'))
            self.assertNotIn('redir https://chatgpt.com', (release / 'config/Caddyfile').read_text())
            self.assertIn('/codex/config', (release / 'config/Caddyfile').read_text())
            self.assertEqual((release / 'site/codex/config').read_bytes(), (ROOT / 'config/codex/config.toml').read_bytes())
            self.assertEqual(build.siteconfig.tomllib.loads((release / 'site/codex/config').read_text())['model_catalog_json'], 'models-1m.json')
            self.assertIn('/codex/models_1m', (release / 'config/Caddyfile').read_text())
            self.assertIn('/codex/auth', (release / 'config/Caddyfile').read_text())
            auth = (release / 'site/codex/auth').read_text()
            self.assertIn('https://custom.example.test/codex/auth', auth)
            subprocess.run(['bash', '-n'], input=auth, text=True, check=True)
            models = release / 'site/codex/models_1m'
            self.assertEqual(models.read_bytes(), (ROOT / 'config/codex/models-1m.json').read_bytes())
            self.assertEqual({m['slug']: m['context_window'] for m in json.loads(models.read_text())['models']}, {'gpt-6-astra': 1000000, 'gpt-5.6-sol': 1000000})
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
            (release / 'site/codex/models_1m').write_text('{"models":[]}')
            with self.assertRaises(ValueError):
                deploy.checked_release(release)

    def test_no_key_means_no_public_key_or_route(self):
        with tempfile.TemporaryDirectory(prefix='linspace-build-test-') as tmp:
            root = Path(tmp)
            config = root / 'site.json'
            config.write_text(json.dumps({'domain': 'second.example.test', 'site_name': 'Second site', 'icp_number': '', 'ssh_public_key_file': '', 'ssh_public_key_name': 'unused.pub', 'claude_settings_file': str(ROOT / 'config/claude/settings.json')}))
            release = build.build(config, root / 'dist', internal=True)
            self.assertFalse((release / 'site/ssh').exists())
            self.assertNotIn('/ssh/', (release / 'config/Caddyfile').read_text())
            self.assertFalse(json.loads((release / 'release.json').read_text())['ssh_enabled'])
            self.assertEqual(json.loads((release / 'release.json').read_text())['stash_key_count'], 0)
            self.assertEqual((release / 'config/stash.allowed_signers').read_bytes(), b'')

    def test_custom_client_configs_are_published_without_private_input_paths(self):
        with tempfile.TemporaryDirectory(prefix='linspace-build-test-') as tmp:
            root = Path(tmp)
            claude = root / 'private-location-claude.json'
            claude.write_text('{"language":"English"}')
            codex = root / 'private-location-codex.toml'
            codex.write_text('# Keep this comment\nmodel_reasoning_effort = "high"\n')
            config = root / 'site.json'
            config.write_text(json.dumps({'domain': 'clients.example.test', 'site_name': 'Clients', 'icp_number': '', 'claude_settings_file': str(claude), 'codex_config_file': str(codex)}))
            release = build.build(config, root / 'dist', internal=True)
            self.assertEqual(json.loads((release / 'site/claude/config').read_text()), {'language': 'English'})
            self.assertEqual((release / 'site/codex/config').read_bytes(), codex.read_bytes())
            for path in release.rglob('*'):
                if path.is_file() and path.suffix not in ('.dat', '.gz'):
                    self.assertNotIn('private-location-', path.read_text())
