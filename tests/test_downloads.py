"""Exercise network failures with a fake transport, never real installer requests."""
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='linspace-download-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bin = self.root / 'tools'
        self.bin.mkdir()
        self.home = self.root / 'client home'
        self.home.mkdir()
        self.env = {**os.environ, 'HOME': str(self.home), 'XDG_CACHE_HOME': str(self.home / 'cache'),
                    'XDG_DATA_HOME': str(self.home / 'data'), 'PATH': str(self.bin) + ':' + os.environ['PATH'],
                    'FIXTURES': str(self.root), 'https_proxy': 'http://broken.example.test:1'}
        for key in ('BASH_ENV', 'ENV', 'SUDO_USER', 'CODEX_INSTALL_DIR'):
            self.env.pop(key, None)
        (self.root / 'official').write_text('<!DOCTYPE html><html>Unavailable</html>')
        self.executable('uname', '#!/bin/sh\ncase "$1" in -s) echo Linux;; *) echo x86_64;; esac\n')
        self.executable('curl', f'#!{sys.executable}\n' + '''import os,sys,json
from pathlib import Path
root=Path(os.environ['FIXTURES']); args=sys.argv[1:]
url=next(a for a in args if a.startswith('https://'))
with (root/'requests').open('a') as f:f.write(json.dumps(args)+'\\n')
output=Path(args[args.index('-o')+1])
if url.endswith('/install.sh'):output.write_bytes((root/'official').read_bytes())
elif 'upstream.test' in url:sys.exit(28)
elif (root/'corrupt').exists():output.write_text('<html>Bad gateway</html>')
else:output.write_bytes((root/url.rsplit('/',1)[1]).read_bytes())
''')
        package = io.BytesIO()
        with tarfile.open(fileobj=package, mode='w:gz') as tar:
            for name in ('bin/codex', 'bin/codex-code-mode-host', 'codex-path/rg', 'codex-resources/bwrap', 'codex-resources/zsh/bin/zsh', 'codex-package.json'):
                data = b'#!/bin/sh\necho codex-cli 0.154.0\n' if name != 'codex-package.json' else b'{}'
                member = tarfile.TarInfo(name); member.mode = 0o755; member.size = len(data)
                tar.addfile(member, io.BytesIO(data))
        self.data = package.getvalue()
        self.sha = hashlib.sha256(self.data).hexdigest()
        parts = [self.data[:len(self.data)//2], self.data[len(self.data)//2:]]
        for i,data in enumerate(parts): (self.root / f'part{i}').write_bytes(data)
        hashes = ' '.join(hashlib.sha256(data).hexdigest() for data in parts)
        sizes = ' '.join(str(len(data)) for data in parts)
        case = f'codex-linux-x64) ASSET_SHA={self.sha}; ASSET_SIZE={len(self.data)}; ASSET_URL=https://upstream.test/package; ASSET_VERSION=0.154.0; ASSET_PART_SHAS=({hashes}); ASSET_PART_SIZES=({sizes}); ASSET_PART_URLS=(https://fallback.test/part0 https://fallback.test/part1);;'
        self.script = build.render('src/common/client-install.sh.in', {'DOMAIN': 'site.example.test', 'CLIENT': 'codex', 'CLIENT_NAME': 'Codex', 'OFFICIAL_INSTALL': 'https://official.test/install.sh', 'ASSET_CASES': case})
        config = self.home / '.codex';config.mkdir();(config/'auth.json').write_text('PRIVATE FIXTURE')
        self.launcher = self.home / '.local/bin/codex'
        self.launcher.parent.mkdir(parents=True)
        self.launcher.write_text('previous launcher')

    def executable(self, name, text):
        path = self.bin / name; path.write_text(text);path.chmod(0o755)

    def run_script(self, script=None):
        return subprocess.run(['bash','-s'], input=script or self.script, env=self.env,
                              text=True, capture_output=True, timeout=15, start_new_session=True)

    def requests(self):
        return [json.loads(line) for line in (self.root/'requests').read_text().splitlines()]

    def test_html_broken_proxy_split_fallback_and_cache_reuse(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertTrue(self.launcher.is_symlink())
        self.assertEqual((self.home/'.codex/auth.json').read_text(), 'PRIVATE FIXTURE')
        package = self.launcher.resolve().parent.parent
        self.assertTrue((package/'codex-path/rg').exists())
        self.assertTrue((package/'codex-resources/zsh/bin/zsh').exists())
        requests = self.requests()
        upstream = [a for a in requests if 'https://upstream.test/package' in a]
        self.assertEqual(len(upstream), 2)
        self.assertNotIn('--proxy', upstream[0]); self.assertIn('--proxy', upstream[1])
        fallback = [a for a in requests if any('fallback.test' in v for v in a)]
        self.assertEqual(len(fallback), 2)
        self.assertTrue(all('--proxy' in a for a in fallback))
        (self.root/'requests').write_text('')
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.requests()), 1)  # Official script; verified archive was reused.

    def test_hosted_only_snapshot_needs_no_primary_download(self):
        result = self.run_script(self.script.replace('ASSET_URL=https://upstream.test/package', "ASSET_URL=''"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(any('https://upstream.test/package' in args for args in self.requests()))
        self.assertTrue(self.launcher.is_symlink())

    def test_bad_fallback_never_replaces_existing_installation(self):
        (self.root/'corrupt').touch()
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.launcher.read_text(), 'previous launcher')
        self.assertFalse(self.launcher.is_symlink())
        self.assertFalse(list((self.home/'cache/linspace').glob('.assemble.*')))
        self.assertFalse(list((self.home/'cache/linspace').glob('.download.*')))

    def test_nonzero_official_installer_and_truncated_stream(self):
        (self.root/'official').write_text('#!/bin/sh\nexit 23\n')
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        before = self.launcher.readlink()
        result = self.run_script(self.script.rsplit('main "$@"',1)[0])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.launcher.readlink(), before)

    def test_timeout_kills_the_official_download_process_group(self):
        pid = self.root/'child.pid'
        (self.root/'official').write_text('#!/bin/sh\nsleep 60 &\necho $! > '+shlex.quote(str(pid))+'\nwait\n')
        result = self.run_script(self.script.replace('bounded 120 env', 'bounded 1 env'))
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        child = int(pid.read_text())
        try:
            os.kill(child, 0)
        except ProcessLookupError:
            pass
        else:
            # Container PID 1 may retain an exited orphan as a zombie.
            status = Path(f'/proc/{child}/stat').read_text()
            self.assertEqual(status[status.rfind(')') + 2:].split()[0], 'Z')
