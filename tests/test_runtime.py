import hashlib
import io
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


class PythonRuntimeTests(unittest.TestCase):
    def run_case(self, program, previous=True):
        temp=tempfile.TemporaryDirectory(prefix='linspace-runtime-');self.addCleanup(temp.cleanup)
        root=Path(temp.name);tools=root/'tools';tools.mkdir();cache=root/'cache';cache.mkdir()
        archive=io.BytesIO()
        with tarfile.open(fileobj=archive,mode='w:gz') as tar:
            data=program.encode();info=tarfile.TarInfo('python/bin/python3');info.size=len(data);info.mode=0o755;tar.addfile(info,io.BytesIO(data))
        data=archive.getvalue();sha=hashlib.sha256(data).hexdigest();(cache/sha).write_bytes(data)
        runtime=cache/('python-'+sha)
        if previous:
            (runtime/'python/bin').mkdir(parents=True);(runtime/'python/bin/python3').write_text('#!/bin/sh\nexit 1\n');(runtime/'python/bin/python3').chmod(0o755);(runtime/'keep').write_text('old runtime')
        values={'DOMAIN':'runtime.example.test','ASSET_CASES':f'python-linux-x64) ASSET_SHA={sha}; ASSET_SIZE={len(data)}; ASSET_URL=""; ASSET_PART_SHAS=({sha}); ASSET_PART_SIZES=({len(data)}); ASSET_PART_URLS=(https://fallback.test/python);;'}
        script='set -euo pipefail\n'+build.render('src/common/ui.sh',values)+build.render('src/common/download.sh.in',values)+ '\nLINSPACE_DOWNLOAD_CACHE='+shlex.quote(str(cache))+'\nlinspace_python_runtime linux-x64 9\n'
        env={**os.environ,'HOME':str(root),'NO_COLOR':'1'}
        for key in ('BASH_ENV','ENV'):env.pop(key,None)
        result=subprocess.run(['bash','-s'],input=script,env=env,text=True,capture_output=True,timeout=15)
        self.assertFalse(list(cache.glob('.python*')),result.stderr)
        return result,runtime

    def test_broken_runtime_is_repaired(self):
        result,runtime=self.run_case('#!/bin/sh\nexit 0\n')
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout.strip(),str(runtime/'python/bin/python3'))
        self.assertFalse((runtime/'keep').exists())

    def test_failed_candidate_preserves_previous_cache(self):
        result,runtime=self.run_case('#!/bin/sh\nexit 1\n')
        self.assertNotEqual(result.returncode,0);self.assertEqual((runtime/'keep').read_text(),'old runtime')

    def test_failed_relocation_restores_previous_runtime(self):
        result,runtime=self.run_case('#!/bin/sh\ncase "$0" in */.python.*) exit 0;; *) exit 1;; esac\n')
        self.assertNotEqual(result.returncode,0);self.assertEqual((runtime/'keep').read_text(),'old runtime')

    def test_failed_new_runtime_is_removed(self):
        result,runtime=self.run_case('#!/bin/sh\ncase "$0" in */.python.*) exit 0;; *) exit 1;; esac\n',previous=False)
        self.assertNotEqual(result.returncode,0);self.assertFalse(runtime.exists())
