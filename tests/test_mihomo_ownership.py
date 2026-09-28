"""Proc inspection must work without granting container ptrace capabilities."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'vendor/pyyaml.zip'))
sys.path.insert(0,str(ROOT/'scripts'))
MODULES=[]
for name in ('process','sub'):
    spec=importlib.util.spec_from_file_location('mihomo_'+name,ROOT/f'src/mihomo/{name}.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);MODULES.append(module)


class OwnershipTests(unittest.TestCase):
    def test_fs_credentials_are_restored_even_when_proc_read_fails(self):
        for module in MODULES:
            for error in (False,True):
                calls=[]
                def readlink(path):
                    self.assertEqual(calls,[('gid',123),('uid',456)])
                    if error:raise PermissionError('restricted proc')
                    return 'socket:[77]'
                with self.subTest(module=module.__name__,error=error),patch.object(module.os,'geteuid',return_value=0),patch.object(module.os,'getegid',return_value=0),patch.object(module.os,'seteuid',side_effect=lambda n:calls.append(('uid',n))),patch.object(module.os,'setegid',side_effect=lambda n:calls.append(('gid',n))),patch.object(module.pwd,'getpwnam',return_value=SimpleNamespace(pw_uid=456,pw_gid=123)),patch.object(Path,'iterdir',return_value=iter([Path('/proc/7/fd/0')])),patch.object(module.os,'readlink',side_effect=readlink):
                    if error:
                        with self.assertRaises(PermissionError):module.process_sockets(7)
                    else:self.assertEqual(module.process_sockets(7),{'socket:[77]'})
                    self.assertEqual(calls,[('gid',123),('uid',456),('uid',0),('gid',0)])
