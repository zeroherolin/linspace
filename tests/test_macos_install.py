"""Exercise the macOS client installer with Darwin architecture fixtures."""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ('bash', 'tar', 'gzip', 'mktemp', 'diff', 'sha256sum', 'shasum', 'cat', 'chmod', 'mkdir', 'rm', 'rmdir', 'cp', 'mv', 'ln',
         'readlink', 'dirname', 'basename', 'sleep', 'wc', 'tail', 'cut')
sys.path.insert(0, str(ROOT / 'scripts'))
import build


class MacOSInstallerTests(unittest.TestCase):
    def make_package(self, client, version):
        if client == 'claude':
            # The official native executable; served as is when zstd is unavailable.
            data = f'#!/bin/sh\necho "{version} (Claude Code)"\n'.encode()
            return data, hashlib.sha256(data).hexdigest()
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode='w:gz') as tar:
            files = {
                'bin/codex': f'#!/bin/sh\necho "codex-cli {version}"\n',
                'bin/codex-code-mode-host': '#!/bin/sh\nexit 0\n',
                'codex-path/rg': '#!/bin/sh\nexit 0\n',
            }
            for name, text in files.items():
                data = text.encode(); member = tarfile.TarInfo(name); member.mode = 0o755; member.size = len(data)
                tar.addfile(member, io.BytesIO(data))
        data = archive.getvalue()
        return data, hashlib.sha256(data).hexdigest()

    def run_install(self, client, machine):
        version = '2.1.267' if client == 'claude' else '0.154.0'
        package, digest = self.make_package(client, version)
        with tempfile.TemporaryDirectory(prefix='linspace-macos-install-') as temporary:
            root = Path(temporary); home = root / 'home'; home.mkdir(); tools = root / 'tools'; tools.mkdir()
            # Only these commands are visible, so the test never finds a real client or zstd.
            for name in TOOLS:
                command = shutil.which(name)
                if command:
                    (tools / name).symlink_to(command)
            fixture = root / 'package.tar.gz'; fixture.write_bytes(package)
            (tools / 'uname').write_text(f'#!/bin/sh\ncase "$1" in -s) echo Darwin;; *) echo {machine};; esac\n')
            (tools / 'uname').chmod(0o755)
            (tools / 'curl').write_text(
                f'#!{sys.executable}\n'
                'import os, shutil, sys\n'
                'from pathlib import Path\n'
                'args=sys.argv[1:]\n'
                'target=Path(args[args.index("-o")+1])\n'
                'shutil.copyfile(os.environ["LINSPACE_FIXTURE"], target)\n'
            )
            (tools / 'curl').chmod(0o755)
            raw = ''
            if client == 'claude':
                # No zstd in this PATH: the uncompressed official executable is fetched and checked.
                raw = f'ASSET_COMPRESSION=zstd; ASSET_RAW_SHA={digest}; ASSET_RAW_SIZE={len(package)}; ASSET_RAW_URL=https://upstream.test/claude; '
                digest = '0' * 64
            values = {
                'DOMAIN': 'macos.example.test',
                'CLIENT': client,
                'CLIENT_NAME': 'Claude Code' if client == 'claude' else 'Codex',
                'ASSET_CASES': f'{client}-darwin-{"arm64" if machine == "arm64" else "x64"}) ASSET_SHA={digest}; ASSET_SIZE={len(package)}; ASSET_URL=https://upstream.test/package; ASSET_VERSION={version}; ASSET_TARGET=; ASSET_RAW_SHA=; {raw}ASSET_PART_SHAS=({digest}); ASSET_PART_SIZES=({len(package)}); ASSET_PART_URLS=(https://fallback.test/package);;'
            }
            script = build.render('src/lifecycle/install.sh.in', values)
            environment = {**os.environ, 'HOME': str(home), 'XDG_DATA_HOME': str(root / 'data'),
                           'XDG_CACHE_HOME': str(root / 'cache'), 'XDG_STATE_HOME': str(root / 'state'),
                           'PATH': str(tools), 'LINSPACE_FIXTURE': str(fixture),
                           'NO_COLOR': '1'}
            for key in ('BASH_ENV', 'ENV', 'SUDO_USER', 'CODEX_INSTALL_DIR'):
                environment.pop(key, None)
            result = subprocess.run(['bash', '-s'], input=script, text=True, env=environment,
                                    cwd=home, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            launcher = home / '.local/bin' / client
            self.assertTrue(launcher.is_symlink(), result.stderr)
            self.assertIn(version, subprocess.check_output([str(launcher), '--version'], text=True))
            self.assertTrue(launcher.resolve().is_file())
            second = subprocess.run(['bash', '-s'], input=script, text=True, env=environment,
                                    cwd=home, capture_output=True, timeout=30)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(launcher.resolve(), launcher.resolve())

    def test_apple_silicon_claude_and_codex_install(self):
        for client in ('claude', 'codex'):
            with self.subTest(client=client):
                self.run_install(client, 'arm64')

    def test_intel_architecture_selects_darwin_x64_asset(self):
        self.run_install('claude', 'x86_64')


if __name__ == '__main__':
    unittest.main()
