#!/usr/bin/env python3
"""Run offline checks without a personal site configuration or administrator privileges."""
from linspace_console import linspace_log
import ast
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
import build
import deploy
import markdown_checks

ROOT = Path(__file__).resolve().parents[1]


def main():
    for directory in ('src', 'scripts', 'tests'):
        for path in (ROOT / directory).rglob('*.py'):
            ast.parse(path.read_text(), filename=str(path))
    for path in [ROOT / 'linspace', *ROOT.rglob('*.sh')]:
        if 'dist' not in path.parts and 'local' not in path.parts and '@@include:' not in path.read_text():
            subprocess.run(['bash', '-n', path], check=True)
    markdown_checks.check([*ROOT.glob('*.md'), *(ROOT / 'docs').glob('*.md')])
    with tempfile.TemporaryDirectory(prefix='linspace-check-') as tmp:
        root = Path(tmp)
        config = root / 'site.json'
        config.write_text(json.dumps({'domain': 'check.example.test', 'site_name': 'Build check', 'icp_number': '', 'ssh_public_key_file': '', 'claude_settings_file': str(ROOT / 'config/claude/settings.json')}))
        release = build.build(config, root / 'dist', internal=True)
        deploy.checked_release(release)
        for path in deploy.shell_scripts(release):
            subprocess.run(['bash', '-n', path], check=True)
            # Scripts that carry a Python program in a heredoc must also parse as Python.
            text = path.read_text()
            for delimiter in ('LINSPACE_STASH_PY', 'LINSPACE_UNINSTALL_PY'):
                if f"<<'{delimiter}'\n" in text:
                    embedded = text.split(f"<<'{delimiter}'\n", 1)[1].rsplit(f'\n{delimiter}', 1)[0]
                    ast.parse(embedded, filename=str(path))
        for path in release.rglob('*.py'):
            ast.parse(path.read_text(), filename=str(path))
    linspace_log('STEP', 'Run behavior and regression tests')
    result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'], text=True, capture_output=True, cwd=ROOT)
    if result.returncode:
        linspace_log('ERROR', 'Regression tests failed')
        details=result.stderr
        start=details.find('=' * 20)
        sys.stderr.write(details[start:] if start>=0 else result.stdout+details)
        raise SystemExit(result.returncode)
    count = re.search(r'Ran (\d+) tests?', result.stderr)
    linspace_log('OK', f'{count[1] if count else "All"} tests passed')
    linspace_log('OK', 'Source, scripts, documentation, release integrity and behavior checks passed.')


if __name__ == '__main__':
    try:main()
    except (ValueError,OSError,subprocess.SubprocessError) as exc:
        linspace_log('ERROR', exc);raise SystemExit(1)
