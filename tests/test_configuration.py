import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import siteconfig


class ConfigurationTests(unittest.TestCase):
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

    def config(self, root, **kwargs):
        raw = {'domain': 'my-domain.cn', 'site_name': 'My site', 'icp_number': '京ICP备2026123456号-1', 'ssh_public_key_file': '', 'claude_settings_file': 'settings.json'}
        raw.update(kwargs)
        (root / 'settings.json').write_text('{}')
        path = root / 'site.json'
        path.write_text(json.dumps(raw))
        return path

    def test_filing_and_unknown_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for values in [{'icp_number': ''}, {'icp_number': 'YOUR_ICP_FILING_NUMBER'}, {'icp_number': 'not a filing number'}, {'site_name': ''}, {'unknown_field': True}]:
                with self.subTest(values=values), self.assertRaises(ValueError):
                    siteconfig.load(self.config(root, **values), root=root)
            config, key, settings = siteconfig.load(self.config(root), root=root)
            self.assertIsNone(key)
            self.assertEqual(json.loads(settings), {})
            self.assertEqual(siteconfig.load(self.config(root, site_name='Fireplace'), root=root)[0]['site_name'], 'Fireplace')

    def test_internal_build_allows_missing_filing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, _, _ = siteconfig.load(self.config(root, icp_number=''), True, root)
            self.assertIn('Internal test', siteconfig.page(config))

    def test_homepage_escapes_user_text(self):
        text = siteconfig.page({'site_name': '<script>alert("x")</script>', 'icp_number': 'ICP " & 号'})
        self.assertNotIn('<script>', text)
        self.assertIn('&lt;script&gt;', text)
        self.assertIn('&amp;', text)

    def test_private_key_is_never_accepted_as_public_key(self):
        for data in [b'-----BEGIN OPENSSH PRIVATE KEY-----\nabc', b'command="whoami" ssh-ed25519 AAAA', b'ssh-ed25519 nonsense']:
            with self.assertRaises(ValueError):
                siteconfig.public_key(data)
