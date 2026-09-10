import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import siteconfig


class ConfigurationTests(unittest.TestCase):
    def test_stash_keys_default_to_published_key_and_allow_independent_authorization(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            key = root / 'key'
            subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-C', 'private-comment', '-f', str(key)], check=True)
            expected = [' '.join(Path(str(key) + '.pub').read_text().split()[:2])]
            for fields, wanted in [({'ssh_public_key_file': 'key.pub'}, expected),
                                   ({'ssh_public_key_file': 'key.pub', 'stash_public_key_files': []}, []),
                                   ({'stash_public_key_files': ['key.pub', str(root / 'key.pub')]}, expected)]:
                with self.subTest(fields=fields):
                    config, published, _, _ = siteconfig.load(self.config(root, **fields), root=root)
                    self.assertEqual(siteconfig.stash_keys(config, published, root), wanted)
            for value in ['key.pub', [None], [''], ['key'], ['missing.pub'], ['key.pub'] * 65]:
                with self.subTest(value=value), self.assertRaises((ValueError, OSError)):
                    siteconfig.load(self.config(root, stash_public_key_files=value), root=root)

    def test_domains_are_normalized(self):
        self.assertEqual(siteconfig.domain_name('Tools.My-Domain.cn'), 'tools.my-domain.cn')
        self.assertEqual(siteconfig.domain_name('例子.cn'), 'xn--fsqu00a.cn')

    def test_domains_reject_shell_caddy_and_url_syntax(self):
        for value in ['https://my-domain.cn', 'host.cn:443', 'host.cn/path', '*.host.cn', 'host.cn\nadmin off', 'a.cn{', '$(id).cn', '127.0.0.1', 'localhost', 'a..cn', 'a.cn.', '-a.cn', 'example.com']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                siteconfig.domain_name(value)

    def test_reserved_domains_need_internal_flag(self):
        self.assertEqual(siteconfig.domain_name('docs.example.test', True), 'docs.example.test')
        with self.assertRaises(ValueError):
            siteconfig.domain_name('docs.example.test')

    def test_public_key_names_allow_safe_pub_filenames(self):
        for value in ['key.pub', 'team.pub', 'workstation-01.pub', 'id_ed25519.pub', 'Work.Key.pub']:
            with self.subTest(name=value):
                self.assertEqual(siteconfig.public_key_name(value), value)

    def test_public_key_names_reject_paths_and_route_injection(self):
        for value in ['', None, 123, 'team', '.hidden.pub', '../team.pub', '/tmp/team.pub', 'folder/team.pub', 'folder\\team.pub', 'team key.pub', 'team*.pub', 'team.pub?x=1', '%2e%2e.pub', 'team.pub\nheader X-Test yes', 'a' * 125 + '.pub']:
            with self.subTest(name=value), self.assertRaises(ValueError):
                siteconfig.public_key_name(value)

    def config(self, root, **kwargs):
        raw = {'domain': 'my-domain.cn', 'site_name': 'My site', 'icp_number': '京ICP备2026123456号-1', 'ssh_public_key_file': '', 'claude_settings_file': 'settings.json'}
        raw.update(kwargs)
        (root / 'settings.json').write_text('{}')
        default = root / 'config/codex/config.toml'
        default.parent.mkdir(parents=True, exist_ok=True)
        default.write_bytes((ROOT / 'config/codex/config.toml').read_bytes())
        path = root / 'site.json'
        path.write_text(json.dumps(raw))
        return path

    def test_filing_and_unknown_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for values in [{'icp_number': ''}, {'icp_number': 'YOUR_ICP_FILING_NUMBER'}, {'icp_number': 'not a filing number'}, {'site_name': ''}, {'unknown_field': True}]:
                with self.subTest(values=values), self.assertRaises(ValueError):
                    siteconfig.load(self.config(root, **values), root=root)
            config, key, settings, codex = siteconfig.load(self.config(root), root=root)
            self.assertIsNone(key)
            self.assertEqual(config['ssh_public_key_name'], 'key.pub')
            self.assertEqual(json.loads(settings), {})
            self.assertEqual(siteconfig.tomllib.loads(codex.decode())['approval_policy'], 'on-request')
            self.assertEqual(config['codex_config_file'], 'config/codex/config.toml')
            self.assertEqual(siteconfig.load(self.config(root, site_name='Fireplace'), root=root)[0]['site_name'], 'Fireplace')

    def test_internal_build_allows_missing_filing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, _, _, _ = siteconfig.load(self.config(root, icp_number=''), True, root)
            self.assertIn('Internal test', siteconfig.page(config))

    def test_custom_codex_toml_preserves_bytes_and_accepts_relative_and_absolute_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = '# Shared preferences\nmodel_reasoning_effort = "high"\n[features]\nmemories = false\n'.encode()
            custom = root / 'shared.toml'
            custom.write_bytes(data)
            for value in ['shared.toml', str(custom)]:
                with self.subTest(path=value):
                    config = self.config(root, codex_config_file=value)
                    self.assertEqual(siteconfig.load(config, root=root)[3], data)

    def test_codex_rejects_invalid_toml_and_missing_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for value in ['', 123, 'missing.toml']:
                with self.subTest(path=value), self.assertRaises((ValueError, OSError)):
                    siteconfig.load(self.config(root, codex_config_file=value), root=root)
            for data in [b'model = [', b'model = "a"\nmodel = "b"', b'\xff']:
                (root / 'invalid.toml').write_bytes(data)
                with self.subTest(data=data), self.assertRaisesRegex(ValueError, 'valid UTF-8 TOML'):
                    siteconfig.load(self.config(root, codex_config_file='invalid.toml'), root=root)

    def test_saved_user_home_inputs_keep_their_source_after_account_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            account_home = root / 'account with spaces'
            account_home.mkdir()
            (account_home / 'claude.json').write_text('{"language":"English"}')
            (account_home / 'codex.toml').write_text('model_catalog_json = "models-1m.json"\n')
            profile = self.config(root, claude_settings_file='~/claude.json', codex_config_file='~/codex.toml')

            def expand_for_home(path):
                text = str(path)
                return account_home / text[2:] if text.startswith('~/') else path

            with patch.object(Path, 'expanduser', expand_for_home):
                config, _, claude, codex = siteconfig.load(profile, root=root)
            self.assertEqual(config['claude_settings_file'], str(account_home / 'claude.json'))
            self.assertEqual(config['codex_config_file'], str(account_home / 'codex.toml'))
            profile.write_text(json.dumps(config))

            def no_user_expansion(path):
                self.assertFalse(str(path).startswith('~'), 'Saved input still depends on the invoking account')
                return path

            with patch.object(Path, 'expanduser', no_user_expansion):
                _, _, reloaded_claude, reloaded_codex = siteconfig.load(profile, root=root)
            self.assertEqual(reloaded_claude, claude)
            self.assertEqual(reloaded_codex, codex)

    def test_homepage_escapes_user_text(self):
        text = siteconfig.page({'site_name': '<script>alert("x")</script>', 'icp_number': 'ICP " & 号'})
        self.assertNotIn('<script>', text)
        self.assertIn('&lt;script&gt;', text)
        self.assertIn('&amp;', text)

    def test_private_key_is_never_accepted_as_public_key(self):
        for data in [b'-----BEGIN OPENSSH PRIVATE KEY-----\nabc', b'command="whoami" ssh-ed25519 AAAA', b'ssh-ed25519 nonsense']:
            with self.assertRaises(ValueError):
                siteconfig.public_key(data)
