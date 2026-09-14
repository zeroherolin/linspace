import json
import hashlib
import sys
import subprocess
import tempfile
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import deploy


class DeploymentTests(unittest.TestCase):
    @contextmanager
    def deployment_host(self):
        """Run apply against temporary host files with every system effect mocked."""
        with tempfile.TemporaryDirectory(prefix='linspace-deploy-test-') as tmp, ExitStack() as stack:
            root = Path(tmp).resolve()

            def host_path(value):
                path = Path(value)
                return root / path.relative_to('/') if path.is_absolute() and not path.is_relative_to(root) else path

            for name in ('MAIN', 'SITE', 'FRAGMENT', 'LEGACY_TOKEN', 'SIGNERS', 'CURRENT', 'STATE', 'LOCK'):
                stack.enter_context(patch.object(deploy, name, host_path(getattr(deploy, name))))
            stack.enter_context(patch.object(deploy, 'Path', side_effect=host_path))
            stack.enter_context(patch.object(deploy.os, 'geteuid', return_value=0))
            stack.enter_context(patch.object(deploy.os, 'umask'))
            stack.enter_context(patch.object(deploy.os, 'chown'))
            stack.enter_context(patch.object(deploy.shutil, 'which', return_value='/mock/tool'))
            stack.enter_context(patch.object(deploy.grp, 'getgrnam', return_value=SimpleNamespace(gr_gid=1)))
            stack.enter_context(patch.object(deploy.grp, 'getgrgid', return_value=SimpleNamespace(gr_name='stash')))
            account = SimpleNamespace(pw_uid=1, pw_gid=1, pw_dir='/var/lib/stashd', pw_shell='/usr/sbin/nologin')
            stack.enter_context(patch.object(deploy.pwd, 'getpwnam', return_value=account))
            run = stack.enter_context(patch.object(deploy, 'run', return_value=SimpleNamespace(stdout='v2.11.4')))
            stack.enter_context(patch.object(deploy.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='405')))
            stack.enter_context(patch.object(deploy, 'stop_writer'))
            stack.enter_context(patch.object(deploy, 'snapshot'))
            restore = stack.enter_context(patch.object(deploy, 'restore'))
            verification = stack.enter_context(patch.object(deploy.verify, 'verify'))
            host_path('/etc').mkdir()
            host_path('/etc/debian_version').touch()
            host_path('/run/systemd/system').mkdir(parents=True)
            deploy.MAIN.parent.mkdir(parents=True)
            deploy.MAIN.write_text('other.cn {\n respond "keep"\n}\n')
            release = root / 'release'
            for name in ('service/stashd.py', 'service/stashd.service', 'service/stashd.socket',
                         'config/Caddyfile', 'config/stash.caddy.template', 'config/stash.allowed_signers'):
                path = release / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('')
            (release / 'site').mkdir()
            meta = {'domain': 'mine.cn', 'stash_auth': 'ssh-signature-v1', 'internal_test': False, 'stash_key_count': 0}
            stack.enter_context(patch.object(deploy, 'checked_release', return_value=(meta, 'release-id')))
            args = SimpleNamespace(dry_run=False, internal_test=False, adopt_existing=False, skip_verify=False, local=True)
            yield SimpleNamespace(release=release, args=args, run=run, verify=verification, restore=restore)

    def test_busy_deployment_does_not_read_host_state_or_install_packages(self):
        with self.deployment_host() as host, deploy.deployment_lock():
            # A stale/invalid state must not even be inspected by the competing deploy.
            deploy.STATE.write_text('invalid state')
            with self.assertRaisesRegex(RuntimeError, 'Another deployment or rollback'):
                deploy.apply(host.release, host.args)
            host.run.assert_not_called()
            host.verify.assert_not_called()
            host.restore.assert_not_called()

    def test_deployment_reads_current_config_only_after_acquiring_lock(self):
        with self.deployment_host() as host:
            acquire = deploy.deployment_lock
            replacement = 'restored.cn {\n respond "restored before deployment acquired lock"\n}\n'

            @contextmanager
            def after_rollback():
                deploy.MAIN.write_text(replacement)
                with acquire():
                    yield

            with patch.object(deploy, 'deployment_lock', after_rollback):
                deploy.apply(host.release, host.args)
            self.assertEqual(deploy.MAIN.read_text(), replacement + '\n' + deploy.IMPORT + '\n')
            host.restore.assert_not_called()

    def test_deployment_holds_lock_through_installation_and_https_verification(self):
        with self.deployment_host() as host:
            def assert_locked(*args, **kwargs):
                with self.assertRaisesRegex(RuntimeError, 'Another deployment or rollback'), deploy.deployment_lock():
                    self.fail('Deployment released its lock too early')
                return SimpleNamespace(stdout='v2.11.4')

            host.run.side_effect = assert_locked
            host.verify.side_effect = assert_locked
            deploy.apply(host.release, host.args)
            host.verify.assert_called_once()
            with deploy.deployment_lock():
                pass  # Normal completion releases the lock.

    def test_failed_preflight_releases_lock_without_changing_config(self):
        with self.deployment_host() as host:
            before = deploy.MAIN.read_bytes()
            host.run.side_effect = RuntimeError('installation unavailable')
            with self.assertRaisesRegex(RuntimeError, 'installation unavailable'):
                deploy.apply(host.release, host.args)
            self.assertEqual(deploy.MAIN.read_bytes(), before)
            host.restore.assert_not_called()
            with deploy.deployment_lock():
                pass

    def test_rollback_uses_the_same_lock_as_deployment(self):
        with self.deployment_host() as host:
            backup = deploy.Path('/var/backups/linspace/snapshot')
            backup.mkdir(parents=True)
            with deploy.deployment_lock():
                with self.assertRaisesRegex(RuntimeError, 'Another deployment or rollback'):
                    deploy.main(['--rollback', str(backup)])
            host.restore.assert_not_called()

            def restore(directory):
                self.assertEqual(directory, backup)
                with self.assertRaisesRegex(RuntimeError, 'Another deployment or rollback'), deploy.deployment_lock():
                    self.fail('Rollback did not acquire the deployment lock')

            host.restore.side_effect = restore
            deploy.main(['--rollback', str(backup)])
            host.restore.assert_called_once_with(backup)

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
