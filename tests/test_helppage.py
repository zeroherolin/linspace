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
    return html.unescape(re.sub(r'<[^>]+>', '', fragment.replace('</span><span class="line">', '\n')))


def headings(page):
    return re.findall(r'<h2>(.*?)</h2>', page)


def section(page, title):
    return page.split(f'<h2>{title}</h2>', 1)[1].split('<h2>', 1)[0]


class HelpPageTests(unittest.TestCase):
    config = {'domain': 'help.example.test', 'site_name': 'Site <name>', 'icp_number': 'ICP & 号'}

    def test_markdown_subset_renders_escaped_html(self):
        source = ('# Title\n\nIntro with `code`, **bold**, *em* and a [link](/help).\n\n'
                  '## Steps\n\n- one\n- two <b>\n\n1. first\n2. second\n\n```text\nplain <x>\nmore\n```\n')
        body = helppage.render_markdown(source)
        self.assertIn('<h1>Title</h1>', body)
        self.assertIn('<code>code</code>, <strong>bold</strong>, <em>em</em> and a <a href="/help" rel="noopener">link</a>.', body)
        self.assertIn('<ul>\n<li>one</li>\n<li>two &lt;b&gt;</li>\n</ul>', body)
        self.assertIn('<ol>\n<li>first</li>\n<li>second</li>\n</ol>', body)
        self.assertIn('<pre data-language="text"><code><span class="line">plain &lt;x&gt;</span><span class="line">more</span></code></pre>', body)

    def test_shell_blocks_are_highlighted_without_changing_text(self):
        code = ('# note <b>\n'
                'curl -fsSL https://x.test/a | bash && mkdir -p ~/.x  # trailing\n'
                'export PATH="$HOME/.local/bin:$PATH" && \\\n'
                "    export TOKEN='a<b'\n")
        body = helppage.render_markdown('```sh\n' + code + '```\n')
        pre = re.search(r'<pre data-language="bash"><code>(.*)</code></pre>', body, re.S).group(1)
        self.assertEqual(strip_tags(pre), code.rstrip('\n'))
        self.assertEqual(pre.count('<span class="line">'), 4)
        self.assertNotIn('<b>', pre)
        self.assertIn('<span class="c"># note &lt;b&gt;</span>', pre)
        self.assertIn('<span class="c"># trailing</span>', pre)
        self.assertIn('curl -fsSL https://x.test/a | bash &amp;&amp; <span class="k">mkdir</span> -p ~/.x', pre)
        self.assertIn('<span class="k">export</span> PATH=<span class="s">&quot;$HOME/.local/bin:$PATH&quot;</span> &amp;&amp; \\', pre)
        self.assertIn('    <span class="k">export</span> TOKEN=<span class="s">&#x27;a&lt;b&#x27;</span>', pre)

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

    def test_section_includes_and_key_placeholder_are_resolved_or_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'page.md'
            source.write_text('# Page\n\n@@include:docs/help.md#tmux@@\n\n## Own\n\nkept\n')
            page = helppage.help_page(self.config, source)
            self.assertEqual(headings(page), ['tmux', 'Own'])
            self.assertIn('https://help.example.test/tmux/install', page)
            self.assertNotIn('@@', page)
            source.write_text('# Page\n\n@@include:docs/help.md#Missing@@\n')
            with self.assertRaisesRegex(ValueError, 'missing section'):
                helppage.help_page(self.config, source)
            source.write_text('# Page\n\n@@include:docs/help2.md#Stash@@\n')
            with self.assertRaisesRegex(ValueError, 'must not include'):
                helppage.help_page(self.config, source)
            source.write_text('# Page\n\n## Keys\n\ncurl https://your-domain.cn/ssh/your-key.pub\n')
            with self.assertRaisesRegex(ValueError, 'your-key.pub'):
                helppage.help_page(self.config, source)
            self.assertIn('https://help.example.test/ssh/ops.pub', helppage.help_page(self.config, source, ssh_key_name='ops.pub'))
            source.write_text('# Page\n\n## SSH key\n\n```sh\n## not a heading\n```\n\nhttps://your-domain.cn/ssh/your-key.pub\n\n## Next\n\nkept\n')
            page = helppage.help_page(self.config, source)
            self.assertEqual(headings(page), ['Next'])
            self.assertNotIn('/ssh/', page)
            self.assertIn('kept', page)

    def test_footer_carries_the_filing_number_unless_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'page.md'
            source.write_text('# Page\n')
            with_filing = helppage.help_page(self.config, source)
            without_filing = helppage.help_page(self.config, source, icp_footer=False)
        self.assertIn('<a href="/">Site &lt;name&gt;</a>\n<a href="https://beian.miit.gov.cn/" target="_blank" rel="noopener">ICP &amp; 号</a>', with_filing)
        self.assertIn('<a href="/">Site &lt;name&gt;</a>', without_filing)
        self.assertNotIn('beian.miit.gov.cn', without_filing)

    def test_repository_help_source_covers_clients_in_feature_order_without_mihomo(self):
        page = helppage.help_page(self.config)
        self.assertIn('<title>Linspace Help · Site &lt;name&gt;</title>', page)
        self.assertIn('<h1>Linspace Help</h1>', page)
        self.assertEqual(headings(page), ['tmux', 'Claude Code', 'Codex', 'Uninstall'])
        for route in ('/tmux/install', '/tmux/config', '/tmux/uninstall', '/claude/install', '/claude/config', '/claude/uninstall',
                      '/codex/install', '/codex/config', '/codex/models_1m', '/codex/auth', '/codex/uninstall'):
            self.assertIn(f'https://help.example.test{route}', page)
        tmux_section = section(page, 'tmux')
        self.assertEqual(tmux_section.count('<pre '), 1)
        self.assertEqual(tmux_section.count('class="c"'), 2)
        self.assertIn('tmux source-file ~/.tmux.conf', tmux_section)
        self.assertNotIn('mihomo', page.lower())
        self.assertNotIn('/ssh/', page)
        self.assertIn('beian.miit.gov.cn', page)
        self.assertNotIn('<script', page.lower())

    def test_complete_help_page_shares_client_sections_and_adds_the_rest_in_feature_order(self):
        page = helppage.help_page(self.config, helppage.COMPLETE_SOURCE, ssh_key_name='team.pub', icp_footer=False)
        self.assertIn('<title>Linspace Complete Help · Site &lt;name&gt;</title>', page)
        self.assertIn('<h1>Linspace Complete Help</h1>', page)
        self.assertEqual(headings(page), ['SSH key', 'Mihomo', 'tmux', 'Claude Code', 'Codex', 'Stash', 'Uninstall'])
        for route in ('/ssh/team.pub', '/mihomo/install', '/mihomo/sub', '/mihomo/restart', '/mihomo/uninstall',
                      '/tmux/install', '/tmux/config', '/tmux/uninstall', '/claude/install', '/claude/config', '/claude/uninstall',
                      '/codex/install', '/codex/config', '/codex/models_1m', '/codex/auth', '/codex/uninstall',
                      '/stash/upload7', '/stash/download7', '/stash/clear'):
            self.assertIn(f'https://help.example.test{route}', page)
        short = helppage.help_page(self.config)
        for title in ('tmux', 'Claude Code', 'Codex'):
            self.assertEqual(section(page, title), section(short, title))
        self.assertEqual(page.count('/codex/install'), 1)
        self.assertNotIn('your-key.pub', page)
        self.assertNotIn('your-domain.cn', page)
        self.assertNotIn('@@', page)
        self.assertNotIn('beian.miit.gov.cn', page)
        self.assertIn('<a href="/">Site &lt;name&gt;</a>', page)

    def test_complete_help_page_omits_ssh_without_a_published_key(self):
        page = helppage.help_page(self.config, helppage.COMPLETE_SOURCE)
        self.assertEqual(headings(page), ['Mihomo', 'tmux', 'Claude Code', 'Codex', 'Stash', 'Uninstall'])
        self.assertNotIn('/ssh/', page)
        self.assertNotIn('your-key.pub', page)


if __name__ == '__main__':
    unittest.main()
