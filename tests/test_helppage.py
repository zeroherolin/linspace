import html
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import helppage


def strip_tags(fragment):
    return html.unescape(re.sub(r'<[^>]+>', '', fragment))


class HelpPageTests(unittest.TestCase):
    config = {'domain': 'help.example.test', 'site_name': 'Site <name>', 'icp_number': 'ICP & 号'}

    def test_markdown_subset_renders_escaped_html(self):
        source = ('# Title\n\nIntro with `code`, **bold**, *em* and a [link](/help).\n\n'
                  '## Steps\n\n- one\n- two <b>\n\n1. first\n2. second\n\n```text\nplain <x>\n```\n')
        body = helppage.render_markdown(source)
        self.assertIn('<h1>Title</h1>', body)
        self.assertIn('<code>code</code>, <strong>bold</strong>, <em>em</em> and a <a href="/help" rel="noopener">link</a>.', body)
        self.assertIn('<ul>\n<li>one</li>\n<li>two &lt;b&gt;</li>\n</ul>', body)
        self.assertIn('<ol>\n<li>first</li>\n<li>second</li>\n</ol>', body)
        self.assertIn('<pre data-language="text"><code>plain &lt;x&gt;</code></pre>', body)

    def test_shell_blocks_are_highlighted_without_changing_text(self):
        code = ('# note <b>\n'
                'curl -fsSL https://x.test/a | bash && mkdir -p ~/.x  # trailing\n'
                'export PATH="$HOME/.local/bin:$PATH" && \\\n'
                "    export TOKEN='a<b'\n")
        body = helppage.render_markdown('```sh\n' + code + '```\n')
        pre = re.search(r'<pre data-language="bash"><code>(.*)</code></pre>', body, re.S).group(1)
        self.assertEqual(strip_tags(pre), code.rstrip('\n'))
        self.assertNotIn('<b>', pre)
        self.assertIn('<span class="c"># note &lt;b&gt;</span>', pre)
        self.assertIn('<span class="c"># trailing</span>', pre)
        self.assertIn('<span class="k">curl</span>', pre)
        self.assertIn('<span class="o">|</span> <span class="k">bash</span>', pre)
        self.assertIn('<span class="v">PATH</span>=<span class="s">&quot;<span class="v">$HOME</span>/.local/bin:<span class="v">$PATH</span>&quot;</span>', pre)
        self.assertIn('<span class="o">\\</span>\n    <span class="k">export</span>', pre)
        self.assertIn('<span class="s">&#x27;a&lt;b&#x27;</span>', pre)

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
            source.write_text('# Page <t>\n\n```sh\ncurl https://your-domain.cn/claude/install | bash\n```\n')
            page = helppage.help_page(self.config, source)
        self.assertIn('https://help.example.test/claude/install', page)
        self.assertNotIn('your-domain.cn', page)
        self.assertIn('<title>Page &lt;t&gt; · Site &lt;name&gt;</title>', page)
        self.assertIn('ICP &amp; 号', page)
        self.assertIn('<html lang="en">', page)
        self.assertNotIn('@@', page)

    def test_repository_help_source_covers_both_clients_without_mihomo(self):
        page = helppage.help_page(self.config)
        self.assertIn('<title>Linspace Help · Site &lt;name&gt;</title>', page)
        self.assertIn('<h1>Linspace Help</h1>', page)
        for route in ('/claude/install', '/claude/config', '/claude/uninstall', '/codex/install', '/codex/config', '/codex/models_1m', '/codex/auth', '/codex/uninstall'):
            self.assertIn(f'https://help.example.test{route}', page)
        self.assertNotIn('mihomo', page.lower())
        self.assertNotIn('<script', page.lower())


if __name__ == '__main__':
    unittest.main()
