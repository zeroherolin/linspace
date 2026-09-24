"""Exercise the tmux installer and uninstaller without changing the test host."""
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build

PERSONAL_CONFIG = '# personal config\n'


class TmuxInstallerTests(unittest.TestCase):
    def installer(self):
        return build.render('src/tmux/install.sh.in', {'DOMAIN': 'tmux.example.test', 'ASSET_CASES': ''})

    def uninstaller(self):
        return build.render('src/tmux/uninstall.sh.in', {'DOMAIN': 'tmux.example.test', 'ASSET_CASES': ''})

    def run_installer(self, os_name='Linux', tmux=False, manager='apt-get', tmux_version='3.3'):
        """Run the installer against fake tools; return the outcome and the package-manager arguments."""
        with tempfile.TemporaryDirectory(prefix='linspace-tmux-install-') as temporary:
            root = Path(temporary)
            tools = root / 'tools'
            tools.mkdir()
            (tools / 'uname').write_text(f'#!/bin/sh\necho {os_name}\n')
            (tools / 'uname').chmod(0o755)
            (root / 'manager-args').write_text('')
            # The fake package manager records its arguments and "installs" a tmux 3.4 stub.
            fake_manager = ('#!/bin/sh\n'
                            f'printf "%s\\n" "$@" >> {root / "manager-args"}\n'
                            f'/bin/cat > {tools / "tmux"} <<\'TMUX\'\n'
                            '#!/bin/sh\n'
                            'echo "tmux 3.4"\n'
                            'TMUX\n'
                            f'/bin/chmod 755 {tools / "tmux"}\n')
            for name in filter(None, (manager, 'brew' if os_name == 'Darwin' else None)):
                (tools / name).write_text(fake_manager)
                (tools / name).chmod(0o755)
            (tools / 'sudo').write_text('#!/bin/sh\nexec "$@"\n')
            (tools / 'sudo').chmod(0o755)
            if tmux:
                (tools / 'tmux').write_text(f'#!/bin/sh\necho "tmux {tmux_version}"\n')
                (tools / 'tmux').chmod(0o755)
            environment = {**os.environ, 'PATH': str(tools), 'NO_COLOR': '1'}
            environment.pop('SUDO_USER', None)
            result = subprocess.run(['/bin/bash', '-s'], input=self.installer(), text=True,
                                    env=environment, capture_output=True, timeout=10)
            return result, (root / 'manager-args').read_text()

    def run_uninstaller(self, running=False, dry_run=False, installed=True, package_status='installed',
                        failure=False, named_server=False, invalid_home=False, symlink_parent=False,
                        symlink_config=False, platform='Linux'):
        """Run the uninstaller in a fake home; return what happened to the package, config and socket."""
        with tempfile.TemporaryDirectory(prefix='linspace-tmux-uninstall-') as temporary:
            root = Path(temporary).resolve()
            tools = root / 'tools'
            tools.mkdir()
            (tools / 'uname').write_text(f'#!/bin/sh\necho {platform}\n')
            (tools / 'uname').chmod(0o755)
            (tools / 'tmux').write_text(
                '#!/bin/sh\n'
                'if [ "${1:-}" = has-session ]; then\n'
                f'  exit {0 if running else 1}\n'
                'fi\n'
                'echo "tmux 3.3"\n'
            )
            (tools / 'tmux').chmod(0o755)
            if not installed:
                (tools / 'tmux').unlink()
            (tools / 'dpkg-query').write_text(f'#!/bin/sh\nprintf "%s\\n" "{package_status}"\n')
            (tools / 'dpkg-query').chmod(0o755)
            (root / 'manager-args').write_text('')
            (tools / 'apt-get').write_text(
                '#!/bin/sh\n'
                f'printf "%s\\n" "$@" > {root / "manager-args"}\n'
                + ('exit 1\n' if failure else '') +
                f'/bin/rm -f {tools / "tmux"}\n'
            )
            (tools / 'apt-get').chmod(0o755)
            if platform == 'Darwin':
                (tools / 'brew').write_text('#!/bin/sh\nif [ "$1" = list ]; then exit 0; fi\n'
                                          f'printf "%s\\n" "$@" > {root / "manager-args"}\n'
                                          f'/bin/rm -f {tools / "tmux"}\n')
                (tools / 'brew').chmod(0o755)
            (tools / 'sudo').write_text('#!/bin/sh\nexec "$@"\n')
            (tools / 'sudo').chmod(0o755)
            (tools / 'rm').symlink_to('/bin/rm')
            (tools / 'readlink').symlink_to(shutil.which('readlink'))
            (tools / 'ps').write_text('#!/bin/sh\n' + ('echo "tmux: server"\n' if named_server else 'exit 0\n'))
            (tools / 'ps').chmod(0o755)
            home = root / "client 'home"
            home.mkdir()
            config = home / '.tmux.conf'
            config.write_text(PERSONAL_CONFIG)
            paths = ['.tmux/plugins/tpm/plugin', '.tmux.conf.local', '.config/tmux/tmux.conf',
                     '.local/share/tmux/file', '.cache/tmux/cache', '.cache/linspace/tmux/cache',
                     'xdg-config/tmux/tmux.conf', 'xdg-data/tmux/file', 'xdg-cache/tmux/cache',
                     'xdg-cache/linspace/tmux/cache']
            for path in paths:
                target = home / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text('tmux data')
            outside = root / 'outside'
            outside.mkdir()
            (outside / 'keep').write_text('unrelated data')
            if symlink_config:
                config.unlink()
                config.symlink_to(outside / 'keep')
            if symlink_parent:
                shutil.rmtree(home / '.config')
                (home / '.config').symlink_to(outside)
            socket_dir = root / 'tmp' / f'tmux-{os.getuid()}'
            socket_dir.mkdir(parents=True)
            (socket_dir / 'default').write_text('socket')
            environment = {'HOME': '/' if invalid_home else str(home), 'TMPDIR': str(root / 'tmp'),
                           'TMUX_TMPDIR': str(root / 'tmp'), 'PATH': str(tools), 'NO_COLOR': '1',
                           'XDG_CONFIG_HOME': str(home / 'xdg-config'),
                           'XDG_DATA_HOME': str(home / 'xdg-data'), 'XDG_CACHE_HOME': str(home / 'xdg-cache')}
            arguments = ['--', '--dry-run'] if dry_run else []
            result = subprocess.run(['/bin/bash', '-s', *arguments], input=self.uninstaller(), text=True,
                                    env=environment, capture_output=True, timeout=10)
            self.assertEqual((outside / 'keep').read_text(), 'unrelated data')
            cleaned = result.returncode == 0 and not dry_run
            for path in paths:
                if symlink_parent and path.startswith('.config/'):
                    continue
                self.assertEqual((home / path).exists(), not cleaned, path + '\n' + result.stderr)
            return SimpleNamespace(result=result, manager_args=(root / 'manager-args').read_text(),
                                   config=config.read_text() if config.exists() else None,
                                   installed=(tools / 'tmux').exists(), socket=socket_dir.exists())

    def assert_untouched(self, outcome):
        self.assertEqual(outcome.config, PERSONAL_CONFIG)
        self.assertTrue(outcome.installed)
        self.assertTrue(outcome.socket)

    def test_existing_tmux_is_reused(self):
        result, args = self.run_installer(tmux=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(args, '')
        self.assertIn('Using existing tmux 3.3', result.stderr)

    def test_linux_refreshes_apt_lists_then_installs_without_hosted_binary(self):
        result, args = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(args.splitlines(), ['update', 'install', '-y', 'tmux'])
        self.assertIn('Installed tmux 3.4', result.stderr)

    def test_linux_dnf_and_apk_use_their_native_install_commands(self):
        for manager, expected in [('dnf', ['install', '-y', 'tmux']), ('apk', ['add', '--no-cache', 'tmux'])]:
            with self.subTest(manager=manager):
                result, args = self.run_installer(manager=manager)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(args.splitlines(), expected)

    def test_macos_uses_homebrew(self):
        result, args = self.run_installer(os_name='Darwin', manager=None)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(args.splitlines(), ['install', 'tmux'])
        self.assertIn('Installed tmux 3.4', result.stderr)

    def test_old_tmux_is_rejected_before_any_package_manager_action(self):
        result, args = self.run_installer(tmux=True, tmux_version='2.5')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(args, '')
        self.assertIn('tmux 3.2 or newer is required', result.stderr)

    def test_uninstaller_dry_run_keeps_package_and_config(self):
        outcome = self.run_uninstaller(dry_run=True)
        self.assertEqual(outcome.result.returncode, 0, outcome.result.stderr)
        self.assertEqual(outcome.manager_args, '')
        self.assert_untouched(outcome)

    def test_uninstaller_removes_package_and_config(self):
        outcome = self.run_uninstaller()
        self.assertEqual(outcome.result.returncode, 0, outcome.result.stderr)
        self.assertEqual(outcome.manager_args.splitlines(), ['purge', '-y', 'tmux'])
        self.assertIsNone(outcome.config)
        self.assertFalse(outcome.installed or outcome.socket)

    def test_uninstaller_refuses_running_server(self):
        outcome = self.run_uninstaller(running=True)
        self.assertNotEqual(outcome.result.returncode, 0)
        self.assertEqual(outcome.manager_args, '')
        self.assertIn('tmux server is running', outcome.result.stderr)
        self.assert_untouched(outcome)

    def test_uninstaller_cleans_residual_data_without_a_binary(self):
        for status, expected in [('not-installed', []), ('config-files', ['purge', '-y', 'tmux'])]:
            with self.subTest(status=status):
                outcome = self.run_uninstaller(installed=False, package_status=status)
                self.assertEqual(outcome.result.returncode, 0, outcome.result.stderr)
                self.assertEqual(outcome.manager_args.splitlines(), expected)
                self.assertIsNone(outcome.config)
                self.assertFalse(outcome.installed or outcome.socket)

    def test_failed_package_removal_preserves_configuration(self):
        outcome = self.run_uninstaller(failure=True)
        self.assertNotEqual(outcome.result.returncode, 0)
        self.assert_untouched(outcome)

    def test_invalid_paths_are_rejected_before_package_removal(self):
        for argument in ('invalid_home', 'symlink_parent'):
            with self.subTest(argument=argument):
                outcome = self.run_uninstaller(**{argument: True})
                self.assertNotEqual(outcome.result.returncode, 0)
                self.assertEqual(outcome.manager_args, '')
                self.assert_untouched(outcome)

    def test_config_symlink_is_unlinked_without_deleting_its_target(self):
        outcome = self.run_uninstaller(symlink_config=True)
        self.assertEqual(outcome.result.returncode, 0, outcome.result.stderr)
        self.assertIsNone(outcome.config)
        self.assertFalse(outcome.installed)

    def test_named_tmux_server_blocks_shared_package_removal(self):
        outcome = self.run_uninstaller(named_server=True)
        self.assertNotEqual(outcome.result.returncode, 0)
        self.assertEqual(outcome.manager_args, '')
        self.assertEqual(outcome.config, PERSONAL_CONFIG)
        self.assertTrue(outcome.installed)

    def test_homebrew_removal_cleans_account_data(self):
        outcome = self.run_uninstaller(platform='Darwin')
        self.assertEqual(outcome.result.returncode, 0, outcome.result.stderr)
        self.assertEqual(outcome.manager_args.splitlines(), ['uninstall', '--force', '--formula', 'tmux'])
        self.assertIsNone(outcome.config)
        self.assertFalse(outcome.installed or outcome.socket)


if __name__ == '__main__':
    unittest.main()
