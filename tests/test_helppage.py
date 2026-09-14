import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import helppage


class HelpPageTests(unittest.TestCase):
    config = {'domain': 'help.example.test', 'site_name': 'Site <name>', 'icp_number': 'ICP & 号'}

    def test_markdown_subset_renders_escaped_html(self):
        source = ('# Title\n\nIntro with `code`, **bold**, *em* and a [link](/help).\n\n'
                  '## Steps\n\n- one\n- two <b>\n\n1. first\n2. second\n\n```sh\necho "<hi>" && export PATH="$HOME/.local/bin:$PATH"\n```\n\n```text\nplain\n```\n')
        body = helppage.render_markdown(source)
        self.assertIn('<h1>Title</h1>', body)
        self.assertIn('<code>code</code>, <strong>bold</strong>, <em>em</em> and a <a href="/help" rel="noopener">link</a>.', body)
        self.assertIn('<ul>\n<li>one</li>\n<li>two &lt;b&gt;</li>\n</ul>', body)
        self.assertIn('<ol>\n<li>first</li>\n<li>second</li>\n</ol>', body)
        self.assertIn('<pre data-language="bash"><code>echo &quot;&lt;hi&gt;&quot; &amp;&amp; export PATH=&quot;$HOME/.local/bin:$PATH&quot;</code></pre>', body)
        self.assertIn('<pre data-language="text"><code>plain</code></pre>', body)

    def test_raw_html_and_unsafe_links_stay_text(self):
        body = helppage.render_markdown('<script>alert(1)</script>\n\n[x](javascript:alert(1)) [y](http://insecure.example)\n')
        self.assertNotIn('<script', body)
        self.assertIn('&lt;script&gt;', body)
        self.assertNotIn('<a ', body)

    def test_unclosed_fence_is_rejected(self):
        with self.assertRaises(ValueError):
            helppage.render_markdown('```sh\necho unterminated\n')

    def test_page_replaces_domain_and_escapes_site_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'help.md'
            source.write_text('# Help\n\n```sh\ncurl https://your-domain.cn/claude/install | bash\n```\n')
            page = helppage.help_page(self.config, source)
        self.assertIn('https://help.example.test/claude/install', page)
        self.assertNotIn('your-domain.cn', page)
        self.assertIn('<title>Help · Site &lt;name&gt;</title>', page)
        self.assertIn('ICP &amp; 号', page)
        self.assertIn('<html lang="en">', page)
        self.assertNotIn('@@', page)

    def test_repository_help_source_covers_both_clients_without_mihomo(self):
        page = helppage.help_page(self.config)
        for route in ('/claude/install', '/claude/config', '/claude/uninstall', '/codex/install', '/codex/config', '/codex/models_1m', '/codex/auth', '/codex/uninstall'):
            self.assertIn(f'https://help.example.test{route}', page)
        self.assertNotIn('mihomo', page.lower())
        self.assertNotIn('<script', page.lower())


if __name__ == '__main__':
    unittest.main()
