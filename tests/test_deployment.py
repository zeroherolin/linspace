import json
import hashlib
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import deploy


class DeploymentTests(unittest.TestCase):
    def test_fresh_deployment_does_not_stop_missing_units(self):
        with patch.object(deploy, 'run', return_value=SimpleNamespace(stdout='not-found\n')) as run:
            deploy.stop_writer()
        self.assertEqual(len(run.call_args_list), 2)
        self.assertTrue(all(call.args[0][1] == 'show' for call in run.call_args_list))

    def test_existing_writer_stop_failures_are_not_ignored(self):
        def command(args, **kwargs):
            if args[1] == 'show':
                return SimpleNamespace(stdout='loaded\n')
            raise subprocess.CalledProcessError(1, args)
        with patch.object(deploy, 'run', side_effect=command) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                deploy.stop_writer()
        self.assertEqual(run.call_args_list[-1].args[0], ['systemctl', 'stop', 'stashd.service', 'stashd.socket'])

    def test_legacy_rollback_restores_proxy_authentication_before_starting_writer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backup = root / 'backup'
            backup.mkdir()
            current = root / 'current'
            (root / 'releases/old').mkdir(parents=True)
            current.symlink_to('releases/new')
            fragment, token, signers = root / 'fragment', root / 'legacy-token', root / 'allowed_signers'
            signers.write_text('new signers')
            entries = []
            for index, (path, value) in enumerate([(fragment, b'old proxy authentication'), (token, b'old secret')]):
                (backup / str(index)).write_bytes(value)
                entries.append({'path': str(path), 'exists': True, 'mode': 0o600, 'gid': 0, 'sha256': hashlib.sha256(value).hexdigest()})
            (backup / 'snapshot.json').write_text(json.dumps({'entries': entries, 'current': 'releases/old', 'stash_enabled': True, 'stash_active': True, 'caddy_active': True}))
            with patch.object(deploy, 'CURRENT', current), patch.object(deploy, 'SIGNERS', signers), \
                 patch.object(deploy, 'MANAGED', [fragment, token, signers]), patch.object(deploy.os, 'chown'), \
                 patch.object(deploy, 'run') as run, patch.object(deploy.subprocess, 'run'):
                deploy.restore(backup)
            self.assertEqual(token.read_bytes(), b'old secret')
            self.assertFalse(signers.exists())
            commands = [call.args[0] for call in run.call_args_list]
            self.assertLess(commands.index(['systemctl', 'reload', 'caddy']), commands.index(['systemctl', 'start', 'stashd.socket']))

    def test_fresh_config(self):
        self.assertEqual(deploy.merged_main(':80 {\n file_server\n}', 'mine.cn', fresh=True), deploy.IMPORT + '\n')

    def test_other_sites_are_preserved_and_import_is_idempotent(self):
        before = 'other.cn {\n respond "other site"\n}\n'
        after = deploy.merged_main(before, 'mine.cn')
        self.assertTrue(after.startswith(before))
        self.assertEqual(after.count(deploy.IMPORT), 1)
        self.assertEqual(deploy.merged_main(after, 'mine.cn'), after)

    def test_existing_top_level_import_globs_are_reused(self):
        for line in ('import /etc/caddy/sites-enabled/*.caddy', 'import sites-enabled/*', 'import "/etc/caddy/sites-enabled/*.caddy" # existing sites'):
            text = 'other.cn {\n respond "other site"\n}\n' + line + '\n'
            self.assertEqual(deploy.merged_main(text, 'mine.cn'), text)

    def test_duplicate_domain_requires_explicit_adoption(self):
        before = 'mine.cn {\n root * /srv/linspace\n handle {\n file_server\n }\n}\n'
        with self.assertRaises(ValueError):
            deploy.merged_main(before, 'mine.cn')
        self.assertEqual(deploy.merged_main(before, 'mine.cn', adopt=True), deploy.IMPORT + '\n')
        with self.assertRaises(ValueError):
            deploy.merged_main(before + 'other.cn {\n respond "keep"\n}\n', 'mine.cn', adopt=True)

    def test_rollback_restores_file_bytes_modes_and_pointer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backup = root / 'backup'
            backup.mkdir()
            (root / 'releases/old').mkdir(parents=True)
            current = root / 'current'
            current.symlink_to('releases/new')
            previous = root / 'config'
            previous.write_text('new value')
            introduced = root / 'introduced'
            introduced.write_text('new file')
            (backup / '0').write_bytes(b'old value\n')
            (backup / 'snapshot.json').write_text(json.dumps({'entries': [{'path': str(previous), 'exists': True, 'mode': 0o600, 'gid': 0, 'sha256': hashlib.sha256(b'old value\n').hexdigest()}, {'path': str(introduced), 'exists': False}], 'current': 'releases/old', 'stash_enabled': False, 'stash_active': False, 'caddy_active': False}))
            with patch.object(deploy, 'CURRENT', current), patch.object(deploy, 'MANAGED', [previous, introduced]), patch.object(deploy.os, 'chown'), patch.object(deploy, 'run'), patch.object(deploy.subprocess, 'run'):
                deploy.restore(backup)
            self.assertEqual(previous.read_bytes(), b'old value\n')
            self.assertEqual(previous.stat().st_mode & 0o777, 0o600)
            self.assertFalse(introduced.exists())
            self.assertEqual(current.readlink(), Path('releases/old'))
