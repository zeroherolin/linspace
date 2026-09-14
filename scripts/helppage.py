"""Render docs/help.md into the public /help page without passing raw HTML through."""
import html
import re
from pathlib import Path
import siteconfig

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'docs/help.md'
TEMPLATE = 'config/help.html.in'
PLACEHOLDER_DOMAIN = 'your-domain.cn'
SHELL_LANGUAGES = {'bash', 'sh', 'shell', 'zsh'}

INLINE_CODE = re.compile(r'`([^`\n]+)`')
INLINE_LINK = re.compile(r'\[([^\]]+)\]\((https://[^\s)]+|/[^\s)]*)\)')
INLINE_STRONG = re.compile(r'\*\*([^*\n]+)\*\*')
INLINE_EMPHASIS = re.compile(r'(?<!\*)\*([^*\n]+)\*(?!\*)')
FENCE = re.compile(r'^(```|~~~)\s*([A-Za-z0-9_+.-]*)\s*$')
HEADING = re.compile(r'^(#{1,3})\s+(.+?)\s*#*$')
BULLET = re.compile(r'^\s*[-*]\s+(.+)$')
NUMBERED = re.compile(r'^\s*\d+[.)]\s+(.+)$')


def markdown_inline(text):
    """Render inline code, links, bold and italics; everything else stays escaped text."""
    escaped = html.escape(text.replace('\x00', ''))
    code = []

    def keep_code(match):
        code.append('<code>' + match.group(1) + '</code>')
        return f'\x00{len(code) - 1}\x00'

    escaped = INLINE_CODE.sub(keep_code, escaped)
    escaped = INLINE_LINK.sub(r'<a href="\2" rel="noopener">\1</a>', escaped)
    escaped = INLINE_STRONG.sub(r'<strong>\1</strong>', escaped)
    escaped = INLINE_EMPHASIS.sub(r'<em>\1</em>', escaped)
    return re.sub('\x00(\\d+)\x00', lambda match: code[int(match.group(1))], escaped)


def render_markdown(markdown):
    """Render headings, paragraphs, lists and fenced code; tables and raw HTML are not supported."""
    blocks = []
    paragraph = []
    code_lines = []
    fence = None
    list_kind = None

    def close_paragraph():
        if paragraph:
            blocks.append('<p>' + '<br>\n'.join(markdown_inline(line) for line in paragraph) + '</p>')
            paragraph.clear()

    def close_list():
        nonlocal list_kind
        if list_kind:
            blocks.append(f'</{list_kind}>')
            list_kind = None

    for raw in markdown.splitlines():
        line = raw.rstrip()
        if fence:
            if line.startswith(fence[0]):
                blocks.append(f'<pre data-language="{fence[1]}"><code>' + html.escape('\n'.join(code_lines)) + '</code></pre>')
                fence = None
                code_lines = []
            else:
                code_lines.append(raw)
            continue
        opened = FENCE.match(line)
        if opened:
            close_paragraph()
            close_list()
            language = opened.group(2).lower()
            fence = (opened.group(1), 'bash' if language in SHELL_LANGUAGES else language or 'text')
            continue
        heading = HEADING.match(line)
        if heading:
            close_paragraph()
            close_list()
            level = len(heading.group(1))
            blocks.append(f'<h{level}>{markdown_inline(heading.group(2))}</h{level}>')
            continue
        bullet = BULLET.match(line)
        item = bullet or NUMBERED.match(line)
        if item:
            close_paragraph()
            kind = 'ul' if bullet else 'ol'
            if list_kind != kind:
                close_list()
                blocks.append(f'<{kind}>')
                list_kind = kind
            blocks.append('<li>' + markdown_inline(item.group(1)) + '</li>')
            continue
        if not line:
            close_paragraph()
            close_list()
            continue
        paragraph.append(line)
    if fence:
        raise ValueError(f'{SOURCE.relative_to(ROOT)} has an unclosed code fence')
    close_paragraph()
    close_list()
    return '\n'.join(blocks)


def help_page(config, source=SOURCE):
    markdown = Path(source).read_text(encoding='utf-8').replace(PLACEHOLDER_DOMAIN, config['domain'])
    return siteconfig.page(config, TEMPLATE, body=render_markdown(markdown))
