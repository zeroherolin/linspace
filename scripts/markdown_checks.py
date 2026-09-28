"""Check local Markdown links and GitHub-style heading anchors."""
import re
from urllib.parse import unquote


def anchors(page):
    result = set()
    counts = {}
    fence = None
    for line in page.read_text().splitlines():
        stripped = line.lstrip()
        if stripped.startswith(('```', '~~~')):
            marker = stripped[:3]
            if fence is None:
                fence = marker
            elif marker == fence:
                fence = None
            continue
        if fence:
            continue
        match = re.match(r'^#{1,6}\s+(.+?)\s*#*$', line)
        if not match:
            continue
        text = re.sub(r'\[([^]]+)\]\([^)]*\)', r'\1', match[1]).replace('`', '')
        slug = re.sub(r'[^\w\s-]', '', text.lower()).replace(' ', '-')
        index = counts.get(slug, 0)
        counts[slug] = index + 1
        result.add(slug if index == 0 else f'{slug}-{index}')
    result.update(re.findall(r'<a\s+(?:id|name)=["\']([^"\']+)',page.read_text()))
    return result


def check(pages):
    for page in pages:
        for link in re.findall(r'\[[^\]]*\]\(([^)]+)\)', page.read_text()):
            if re.match(r'[a-z]+:', link):
                continue
            path, _, fragment = link.partition('#')
            target = page.parent / unquote(path) if path else page
            if not target.exists():
                raise ValueError(f'{page}: missing link {link}')
            if fragment and target.suffix == '.md' and unquote(fragment) not in anchors(target):
                raise ValueError(f'{page}: missing heading {link}')
