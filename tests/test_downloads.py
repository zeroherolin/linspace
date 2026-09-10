"""Installer failures are simulated in temporary homes, never real user setups."""
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

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import build


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='linspace-download-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.bin=self.root/'tools';self.bin.mkdir()
        self.home=self.root/"client 'home";self.home.mkdir()
        self.env={**os.environ,'HOME':str(self.home),'CODEX_HOME':str(self.home/'.codex'),'CLAUDE_CONFIG_DIR':str(self.home/'.claude'),'XDG_CACHE_HOME':str(self.home/'cache'),'XDG_DATA_HOME':str(self.home/'data'),'XDG_CONFIG_HOME':str(self.home/'.config'),'XDG_STATE_HOME':str(self.home/'.state'),'ZDOTDIR':str(self.home),'PATH':str(self.bin)+':'+os.environ['PATH'],'FIXTURES':str(self.root),'https_proxy':'http://broken.example.test:1','NO_COLOR':'1'}
        for key in ('BASH_ENV','ENV','SUDO_USER','CODEX_INSTALL_DIR'):self.env.pop(key,None)
        self.executable('uname','#!/bin/sh\ncase "$1" in -s) echo Linux;; *) echo x86_64;; esac\n')
        self.executable('curl',f'#!{sys.executable}\n'+'''import os,sys,json
from pathlib import Path
root=Path(os.environ['FIXTURES']); args=sys.argv[1:];url=next(a for a in args if a.startswith('https://'))
with (root/'requests').open('a') as f:f.write(json.dumps(args)+'\\n')
output=Path(args[args.index('-o')+1])
if 'upstream.test' in url:output.write_text('<!DOCTYPE html>Unavailable')
elif (root/'corrupt').exists():output.write_text('wrong bytes')
else:output.write_bytes((root/url.rsplit('/',1)[1]).read_bytes())
''')
        self.script=self.package_script()
        (self.home/'.codex').mkdir();(self.home/'.codex/auth.json').write_text('PRIVATE FIXTURE')
        self.launcher=self.home/'.local/bin/codex';self.launcher.parent.mkdir(parents=True);self.launcher.write_text('previous launcher')
        self.profiles={self.home/name:('# original '+name+'\n') for name in ('.bashrc','.bash_profile','.profile','.zshrc','.zprofile')}
        for path,text in self.profiles.items():path.write_text(text)

    def executable(self,name,text):
        path=self.bin/name;path.write_text(text);path.chmod(0o755)

    def package_script(self,entrypoint='#!/bin/sh\necho codex-cli 0.154.0\n'):
        package=io.BytesIO()
        with tarfile.open(fileobj=package,mode='w:gz') as tar:
            for name in ('bin/codex','bin/codex-code-mode-host','codex-path/rg','codex-resources/bwrap','codex-resources/zsh/bin/zsh','codex-package.json'):
                data=(entrypoint if name=='bin/codex' else '#!/bin/sh\nexit 0\n').encode() if name!='codex-package.json' else b'{}'
                member=tarfile.TarInfo(name);member.mode=0o755;member.size=len(data);tar.addfile(member,io.BytesIO(data))
        data=package.getvalue();sha=hashlib.sha256(data).hexdigest();parts=[data[:len(data)//2],data[len(data)//2:]]
        for i,part in enumerate(parts):(self.root/f'part{i}').write_bytes(part)
        hashes=' '.join(hashlib.sha256(p).hexdigest() for p in parts);sizes=' '.join(str(len(p)) for p in parts)
        case=f'codex-linux-x64) ASSET_SHA={sha}; ASSET_SIZE={len(data)}; ASSET_URL=https://upstream.test/package; ASSET_VERSION=0.154.0; ASSET_PART_SHAS=({hashes}); ASSET_PART_SIZES=({sizes}); ASSET_PART_URLS=(https://fallback.test/part0 https://fallback.test/part1);;'
        return build.render('src/common/client-install.sh.in',{'DOMAIN':'site.example.test','CLIENT':'codex','CLIENT_NAME':'Codex','ASSET_CASES':case})

    def run_script(self,script=None):
        return subprocess.run(['bash','-s'],input=script or self.script,env=self.env,text=True,capture_output=True,timeout=15,start_new_session=True)

    def requests(self):
        path=self.root/'requests'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_html_broken_proxy_fallback_cache_and_idempotency(self):
        result=self.run_script();self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(self.launcher.is_symlink());self.assertEqual((self.home/'.codex/auth.json').read_text(),'PRIVATE FIXTURE')
        package=self.launcher.resolve().parent.parent
        self.assertTrue((package/'codex-path/rg').exists());self.assertTrue((package/'codex-resources/bwrap').exists())
        upstream=[a for a in self.requests() if 'https://upstream.test/package' in a]
        self.assertEqual(len(upstream),2);self.assertNotIn('--proxy',upstream[0]);self.assertIn('--proxy',upstream[1])
        self.assertEqual(len([a for a in self.requests() if any('fallback.test' in v for v in a)]),2)
        backups=list((self.home/'data/linspace/codex').glob('.previous.*'))
        (self.root/'requests').write_text('');result=self.run_script()
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(self.requests(),[])
        self.assertEqual(list((self.home/'data/linspace/codex').glob('.previous.*')),backups)

    def test_path_hint_is_executable_and_profiles_are_untouched(self):
        result=self.run_script();self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('PATH setup required',result.stderr);self.assertNotIn('\x1b',result.stderr)
        command=next(line.strip() for line in result.stderr.splitlines() if line.strip().startswith('export PATH='))
        checked=subprocess.run(['bash','-c',command+'; command -v codex'],env=self.env,text=True,capture_output=True)
        self.assertEqual(checked.stdout.strip(),str(self.launcher))
        for path,text in self.profiles.items():self.assertEqual(path.read_text(),text)
        self.assertFalse((self.home/'.config/linspace').exists())

    def test_hosted_only_snapshot_needs_no_primary_download(self):
        result=self.run_script(self.script.replace('ASSET_URL=https://upstream.test/package',"ASSET_URL=''"))
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse(any('https://upstream.test/package' in a for a in self.requests()))

    def test_bad_fallback_preserves_launcher_and_cleans_partial_files(self):
        (self.root/'corrupt').touch();result=self.run_script();self.assertNotEqual(result.returncode,0)
        self.assertEqual(self.launcher.read_text(),'previous launcher')
        self.assertFalse(list((self.home/'cache/linspace').glob('.*')))

    def test_newer_install_is_never_downgraded(self):
        self.launcher.write_text('#!/bin/sh\necho codex-cli 0.200.0\n');self.launcher.chmod(0o755)
        original=self.launcher.read_bytes();result=self.run_script()
        self.assertEqual(result.returncode,0,result.stderr);self.assertIn('Keeping newer',result.stderr)
        self.assertEqual(self.launcher.read_bytes(),original);self.assertEqual(self.requests(),[])

    def test_failed_activation_leaves_no_staging_or_release(self):
        self.executable('mv',f'#!{sys.executable}\n'+'''import os,sys
from pathlib import Path
if sys.argv[-1]==str(Path(os.environ['HOME'])/'.local/bin/codex'):sys.exit(1)
os.execv('/bin/mv',['mv',*sys.argv[1:]])
''')
        result=self.run_script();self.assertNotEqual(result.returncode,0)
        self.assertEqual(self.launcher.read_text(),'previous launcher')
        self.assertFalse(list((self.home/'data/linspace/codex').iterdir()))
        self.assertFalse(list(self.launcher.parent.glob('.linspace.*')))

    def test_truncated_stream_and_help_make_no_changes(self):
        result=self.run_script(self.script.rsplit('main "$@"',1)[0]);self.assertEqual(result.returncode,0)
        self.assertEqual(self.launcher.read_text(),'previous launcher');self.assertEqual(self.requests(),[])

    def test_binary_version_timeout_kills_children(self):
        pid=self.root/'child.pid'
        script=self.package_script('#!/bin/sh\nsleep 60 &\necho $! > '+shlex.quote(str(pid))+'\nwait\n').replace('bounded 15','bounded 1')
        result=self.run_script(script);self.assertNotEqual(result.returncode,0)
        child=int(pid.read_text())
        try:os.kill(child,0)
        except ProcessLookupError:pass
        else:
            proc=Path(f'/proc/{child}/stat')
            if proc.exists():self.assertEqual(proc.read_text().split(')')[-1].strip().split()[0],'Z')
            else:self.fail('The version-check child is still running')
        self.assertEqual(self.launcher.read_text(),'previous launcher')
