#!/usr/bin/env python3
"""Run offline checks without a personal site configuration or administrator privileges."""
import ast
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
import build
import deploy

ROOT = Path(__file__).resolve().parents[1]


def main():
    for directory in ('src', 'scripts', 'tests'):
        for path in (ROOT / directory).rglob('*.py'):
            ast.parse(path.read_text(), filename=str(path))
    for path in [ROOT / 'linspace', *ROOT.rglob('*.sh')]:
        if 'dist' not in path.parts and 'local' not in path.parts:
            subprocess.run(['bash', '-n', path], check=True)
    for page in [*ROOT.glob('*.md'), *(ROOT / 'docs').rglob('*.md'), *(ROOT / 'config').rglob('*.md'), *(ROOT / 'assets').rglob('*.md'), *(ROOT / 'packaging').rglob('*.md')]:
        for link in re.findall(r'\[[^\]]*\]\(([^)]+)\)', page.read_text()):
            link = link.split('#', 1)[0]
            if link and not re.match(r'[a-z]+:', link):
                if not (page.parent / link).exists():
                    raise ValueError(f'{page}: missing link {link}')
    with tempfile.TemporaryDirectory(prefix='linspace-check-') as tmp:
        root = Path(tmp)
        config = root / 'site.json'
        config.write_text(json.dumps({'domain': 'check.example.test', 'site_name': 'Build check', 'icp_number': '', 'ssh_public_key_file': '', 'claude_settings_file': str(ROOT / 'config/claude/settings.json')}))
        release = build.build(config, root / 'dist', internal=True)
        deploy.checked_release(release)
        for path in [*list((release / 'site/mihomo').glob('*')), *list((release / 'site/stash').glob('upload*')), release / 'site/stash/clear', release / 'site/codex/auth']:
            if path.is_file():
                subprocess.run(['bash', '-n', path], check=True)
                if path.parent.name == 'stash':
                    embedded = path.read_text().split("<<'LINSPACE_STASH_PY'\n", 1)[1].rsplit('\nLINSPACE_STASH_PY', 1)[0]
                    ast.parse(embedded, filename=str(path))
        for path in release.rglob('*.py'):
            ast.parse(path.read_text(), filename=str(path))
    subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'], check=True, cwd=ROOT)
    print('All source, generated-script, local-link, release-integrity, configuration, deployment, and stash checks passed.')


if __name__ == '__main__':
    main()
