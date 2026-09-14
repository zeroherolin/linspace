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

SHELL_WORD = re.compile(r'[^\s\'"|&;]+')
# Shell builtins and the file commands that read as keywords in a setup snippet.
SHELL_KEYWORDS = frozenset('''
    alias break case cd command continue declare do done echo elif else esac eval exec exit export fi for
    function if in local printf pwd read readonly return set shift source then trap unalias unset until while
    cat chmod chown cp ln mkdir mv rm rmdir touch
'''.split())


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


def plain_text(text):
    """Strip the inline Markdown syntax for use in a <title>."""
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)
    return re.sub(r'[`*]', '', text).strip()


def _span(text, kind=None):
    escaped = html.escape(text)
    return f'<span class="{kind}">{escaped}</span>' if kind and text else escaped


def _highlight_shell_line(line, expect_command):
    """Mark comments, quoted strings and keyword commands on one line."""
    out = []
    i, n = 0, len(line)
    continued = False
    while i < n:
        ch = line[i]
        if ch in ' \t':
            j = i
            while j < n and line[j] in ' \t':
                j += 1
            out.append(line[i:j])
            i = j
        elif ch == '#' and (i == 0 or line[i - 1] in ' \t'):
            out.append(_span(line[i:], 'c'))
            break
        elif ch in '\'"':
            j = i + 1
            while j < n and line[j] != ch:
                j += 2 if ch == '"' and line[j] == '\\' else 1
            j = min(j + 1, n)
            out.append(_span(line[i:j], 's'))
            i = j
            expect_command = False
        elif ch == '\\' and i == n - 1:
            out.append('\\')
            continued = True
            i += 1
        elif ch in '|&;':
            j = i
            while j < n and line[j] in '|&;':
                j += 1
            out.append(html.escape(line[i:j]))
            i = j
            expect_command = True
        else:
            word = SHELL_WORD.match(line, i)
            word = word.group(0) if word else ch
            out.append(_span(word, 'k' if expect_command and word in SHELL_KEYWORDS else None))
            i += len(word)
            expect_command = False
    return ''.join(out), expect_command if continued else True


def highlight_shell(code):
    """Return escaped HTML lines for a shell snippet with a small, quiet set of token classes."""
    lines, expect_command = [], True
    for line in code.split('\n'):
        rendered, expect_command = _highlight_shell_line(line, expect_command)
        lines.append(rendered)
    return lines


def code_block(language, code):
    """Wrap each line so the page can number lines without adding text to copies."""
    lines = highlight_shell(code) if language == 'bash' else [html.escape(line) for line in code.split('\n')]
    # Block-level spans supply the line breaks; a literal newline would add a blank row under white-space: pre.
    body = ''.join(f'<span class="line">{line}</span>' for line in lines)
    return f'<pre data-language="{language}"><code>{body}</code></pre>'


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
                blocks.append(code_block(fence[1], '\n'.join(code_lines)))
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
    title = next((plain_text(match.group(2)) for match in map(HEADING.match, markdown.splitlines())
                  if match and len(match.group(1)) == 1), 'Help')
    return siteconfig.page(config, TEMPLATE, body=render_markdown(markdown), title=html.escape(title, quote=True))
