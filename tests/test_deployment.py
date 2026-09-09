import json
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import deploy


class DeploymentTests(unittest.TestCase):
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
