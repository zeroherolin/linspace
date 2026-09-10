import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import cli
import downloads
import siteconfig
from linspace_console import linspace_log


class AuditTests(unittest.TestCase):
    def test_configuration_profiles_keep_independent_public_keys(self):
        with tempfile.TemporaryDirectory(prefix='linspace-profile-') as directory:
            root=Path(directory);shutil.copytree(ROOT/'config',root/'config')
            profiles=[]
            for number in (1,2):
                private=root/f'key{number}'
                subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(private)],check=True)
                profile=root/f'site{number}.json';profile.write_text(json.dumps({'domain':f'site{number}.example.test','site_name':'Test','icp_number':'','ssh_public_key_file':str(private)+'.pub'}))
                args=SimpleNamespace(config=profile,non_interactive=True,internal_test=True,stash_public_key_files=None)
                with patch.object(cli,'ROOT',root),contextlib.redirect_stderr(io.StringIO()):cli.configure(args)
                profiles.append(json.loads(profile.read_text()))
            self.assertNotEqual(profiles[0]['ssh_public_key_file'],profiles[1]['ssh_public_key_file'])
            for number,profile in enumerate(profiles,1):self.assertEqual((root/profile['ssh_public_key_file']).read_bytes(),(root/f'key{number}.pub').read_bytes())
            self.assertFalse(list(root.glob('.site-*')))

    def test_public_configs_reject_literal_secrets_but_allow_env_references(self):
        for value in ({'env':{'ANTHROPIC_AUTH_TOKEN':'private-fixture'}},{'model_providers':{'relay':{'http_headers':{'Authorization':'Bearer private-fixture'}}}},{'model_providers':{'relay':{'experimental_bearer_token':'private-fixture'}}}):
            with self.subTest(value=value),self.assertRaises(ValueError) as error:siteconfig.check_public_settings(value)
            self.assertNotIn('private-fixture',str(error.exception))
        siteconfig.check_public_settings({'model_providers':{'relay':{'env_key':'OPENAI_API_KEY','env_http_headers':{'Authorization':'RELAY_AUTH'}}}})

    def test_download_versions_and_linux_completeness_are_validated(self):
        original=json.loads((ROOT/'config/downloads.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'config').mkdir()
            for edit in ('version','size','missing','raw'):
                data=json.loads(json.dumps(original));entry=data['assets']['codex-linux-x64']
                if edit=='version':entry['version']='../../unsafe'
                elif edit=='size':entry['size']=True
                elif edit=='missing':del data['assets']['python-linux-arm64']
                else:data['assets']['mihomo-arm64']['raw_sha256']='bad'
                (root/'config/downloads.json').write_text(json.dumps(data))
                with self.subTest(edit=edit),patch.object(downloads,'ROOT',root),self.assertRaises(ValueError):downloads.values()

    def test_status_is_plain_on_pipes_and_does_not_pollute_stdout(self):
        output=io.StringIO();status=io.StringIO()
        with contextlib.redirect_stdout(output),contextlib.redirect_stderr(status):linspace_log('OK','done\x1b\nnext')
        self.assertEqual(output.getvalue(),'');self.assertEqual(status.getvalue(),'[linspace] OK    done\n[linspace] OK    next\n')
