"""Exercise installer rollback on temporary fixtures, never on the real application."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import mettre_a_jour_application as updater

spec = importlib.util.spec_from_file_location("prepapilot_build", updater.WORKSPACE / "Sources" / "PrepaPilot" / "build_windows.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class FakeLock:
    def __init__(self, available=True):
        self.available = available
        self.released = False

    def setStaleLockTime(self, value):
        pass

    def tryLock(self, value):
        return self.available

    def unlock(self):
        self.released = True


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "Projet PrépaPilot"
        self.local = updater.local_root(self.root)
        self.application = self.root / "Application" / "PrepaPilot"
        self.staging = self.local / "Livraison" / "PrepaPilot"
        self.sources = self.root / "Sources" / "PrepaPilot"
        (self.sources / 'assets').mkdir(parents=True)
        (self.sources / 'assets' / 'app.ico').write_bytes(b'icon')
        for folder, version in ((self.application, "old"), (self.staging, "new")):
            (folder / "_internal").mkdir(parents=True)
            (folder / "PrepaPilot.exe").write_bytes(version.encode())
            (folder / "_internal" / "runtime.dll").write_bytes((version + " dll").encode())
            (folder / "GUIDE.md").write_text(version + " guide")
        (self.application / "data" / "documents").mkdir(parents=True)
        (self.application / "data" / "mpsi.sqlite3").write_bytes(b"personal database")
        (self.application / "data" / "documents" / "note.txt").write_bytes(b"personal original")
        marker = self.staging / "self-test-ok.txt"
        marker.write_text("validated fixture")
        stamp = (self.staging / "PrepaPilot.exe").stat().st_mtime_ns + 100000
        os.utime(marker, ns=(stamp, stamp))
        self.lock = FakeLock()

    def tearDown(self):
        self.temp.cleanup()

    def install(self):
        return updater.install_update(self.staging, workspace=self.root, lock_factory=lambda _: self.lock)

    def assert_data(self):
        self.assertEqual((self.application / "data" / "mpsi.sqlite3").read_bytes(), b"personal database")
        self.assertEqual((self.application / "data" / "documents" / "note.txt").read_bytes(), b"personal original")

    def test_update_archives_previous_files_and_keeps_data_in_place(self):
        archive = self.install()
        self.assertEqual((self.application / "PrepaPilot.exe").read_bytes(), b"new")
        self.assertEqual((archive / "PrepaPilot.exe").read_bytes(), b"old")
        self.assertEqual((archive / "_internal" / "runtime.dll").read_bytes(), b"old dll")
        self.assertFalse((archive / "data").exists())
        self.assertFalse((self.application / "self-test-ok.txt").exists())
        self.assertTrue(self.lock.released)
        self.assertEqual(archive.parent, self.local / "Archives")
        self.assertEqual(list((self.local / "Transactions").iterdir()), [])
        self.assertFalse((self.root / "Archives").exists())
        self.assertFalse((self.root / "Outils").exists())
        self.assert_data()

    def test_open_application_rejected_without_closing_or_moving_anything(self):
        self.lock.available = False
        with self.assertRaisesRegex(ValueError, "est ouvert"):
            self.install()
        self.assertEqual((self.application / "PrepaPilot.exe").read_bytes(), b"old")
        self.assertFalse((self.local / "Archives").exists())
        self.assert_data()

    def test_interrupted_replacement_rolls_back_all_binaries(self):
        real_replace = os.replace
        def fail_runtime(source, target):
            if Path(source).parent.name == "new" and Path(source).name == "_internal":
                raise OSError("simulated locked DLL")
            return real_replace(source, target)
        with patch.object(updater.os, "replace", side_effect=fail_runtime), self.assertRaises(OSError):
            self.install()
        self.assertEqual((self.application / "PrepaPilot.exe").read_bytes(), b"old")
        self.assertEqual((self.application / "_internal" / "runtime.dll").read_bytes(), b"old dll")
        self.assertEqual(list((self.local / "Archives").iterdir()), [])
        self.assertEqual(list((self.local / "Transactions").iterdir()), [])
        self.assertTrue(self.lock.released)
        self.assert_data()

    def test_bad_copy_detected_before_installed_version_is_touched(self):
        real_copy = updater._copy
        def bad_copy(source, target):
            real_copy(source, target)
            if target.name == "PrepaPilot.exe":
                target.write_bytes(b"incomplete")
        with patch.object(updater, "_copy", side_effect=bad_copy), self.assertRaises(ValueError):
            self.install()
        self.assertEqual((self.application / "PrepaPilot.exe").read_bytes(), b"old")
        self.assertFalse((self.local / "Archives").exists())
        self.assertEqual(list((self.local / "Transactions").iterdir()), [])
        self.assert_data()

    def test_unverified_build_and_personal_staging_rejected(self):
        (self.staging / "self-test-ok.txt").unlink()
        with self.assertRaisesRegex(ValueError, "self-test"):
            self.install()
        (self.staging / "data").mkdir()
        with self.assertRaisesRegex(ValueError, "sans données"):
            self.install()
        self.assertEqual((self.application / "PrepaPilot.exe").read_bytes(), b"old")
        self.assert_data()

    def test_two_updates_preserve_v2_and_every_previous_release(self):
        oldest = self.local / "Archives" / "PrepaPilot-v2"
        oldest.mkdir(parents=True)
        (oldest / "PrepaPilot.exe").write_bytes(b"historic v2")
        first = self.install()
        self.assertEqual(first.name, "PrepaPilot-v2.1")
        (self.staging / "PrepaPilot.exe").write_bytes(b"newer")
        (self.staging / "_internal" / "runtime.dll").write_bytes(b"newer dll")
        stamp = (self.staging / "PrepaPilot.exe").stat().st_mtime_ns + 100000
        os.utime(self.staging / "self-test-ok.txt", ns=(stamp, stamp))
        second = self.install()
        self.assertNotEqual(first, second)
        self.assertTrue(second.name.startswith("PrepaPilot-v2.1-"))
        self.assertTrue(second.resolve().is_relative_to((self.local / "Archives").resolve()))
        self.assertEqual((oldest / "PrepaPilot.exe").read_bytes(), b"historic v2")
        self.assertEqual((first / "PrepaPilot.exe").read_bytes(), b"old")
        self.assertEqual((second / "PrepaPilot.exe").read_bytes(), b"new")
        self.assertEqual((self.application / "PrepaPilot.exe").read_bytes(), b"newer")
        self.assertEqual((self.application / "_internal" / "runtime.dll").read_bytes(), b"newer dll")
        self.assert_data()

    def test_archive_label_cannot_escape_workspace(self):
        for label in ("../outside", "PrepaPilot-v2/../../outside", str(self.root / "outside")):
            with self.subTest(label=label), self.assertRaises(ValueError):
                updater.install_update(self.staging, workspace=self.root, archive_label=label, lock_factory=lambda _: self.lock)
        self.assertFalse((self.local / "Archives").exists())
        self.assertEqual((self.application / "PrepaPilot.exe").read_bytes(), b"old")
        self.assert_data()

    def test_build_output_guards_sources_and_live_data(self):
        allowed = build.validate_output(self.local / "Livraison", source=self.sources, workspace=self.root)
        self.assertEqual(allowed, self.local / "Livraison")
        custom = build.validate_output("Distribution personnalisée", source=self.sources, workspace=self.root)
        self.assertEqual(custom, self.root / "Distribution personnalisée")
        for forbidden in (self.root, self.root.parent, self.local, self.local / "Construction", self.local / "Livraison" / "nested", self.sources, self.sources / "nested", self.sources.parent, self.root / "Application", self.application, self.application / "nested", self.application / "data"):
            with self.subTest(path=forbidden), self.assertRaises(ValueError):
                build.validate_output(forbidden, source=self.sources, workspace=self.root)

    def test_build_output_rejects_existing_personal_data(self):
        output = self.root / "Ancienne distribution"
        (output / "PrepaPilot" / "data").mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "contient des données"):
            build.validate_output(output, source=self.sources, workspace=self.root)

    def test_only_designated_local_staging_can_be_installed(self):
        for path in (self.root / "Outils" / "Livraison" / "PrepaPilot", self.local / "Autre" / "PrepaPilot", self.local / "Livraison", self.application):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "dossier local voisin"):
                updater.install_update(path, workspace=self.root, lock_factory=lambda _: self.lock)
        self.assertEqual((self.application / "PrepaPilot.exe").read_bytes(), b"old")
        self.assertFalse((self.local / "Archives").exists())
        self.assert_data()

    def test_transaction_is_prepared_outside_project(self):
        real_mkdtemp = updater.tempfile.mkdtemp
        with patch.object(updater.tempfile, "mkdtemp", wraps=real_mkdtemp) as prepare:
            self.install()
        self.assertEqual(prepare.call_args.kwargs["dir"], self.local / "Transactions")
        self.assertEqual(list((self.local / "Transactions").iterdir()), [])

    def test_unexpected_transaction_is_retained_and_lock_released(self):
        unexpected = Path(self.temp.name) / ".update-outside"
        unexpected.mkdir()
        (unexpected / "keep.txt").write_text("keep")
        with patch.object(updater.tempfile, "mkdtemp", return_value=str(unexpected)), self.assertRaisesRegex(RuntimeError, "inattendu"):
            self.install()
        self.assertEqual((unexpected / "keep.txt").read_text(), "keep")
        self.assertEqual((self.application / "PrepaPilot.exe").read_bytes(), b"old")
        self.assertTrue(self.lock.released)
        self.assert_data()

    def test_local_archives_and_transactions_cannot_redirect(self):
        outside = Path(self.temp.name) / "autre emplacement"
        outside.mkdir()
        for name in ("Archives", "Transactions"):
            link = self.local / name
            try:
                link.symlink_to(outside, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"Directory symlinks unavailable: {exc}")
            try:
                with self.subTest(directory=name), self.assertRaisesRegex(ValueError, "sans redirection"):
                    self.install()
                self.assertEqual(list(outside.iterdir()), [])
                self.assertEqual((self.application / "PrepaPilot.exe").read_bytes(), b"old")
                self.assert_data()
            finally:
                link.unlink()

    def test_build_target_cannot_redirect_to_another_folder(self):
        output = self.root / "Distribution personnalisée"
        output.mkdir()
        outside = Path(self.temp.name) / "autre emplacement"
        outside.mkdir()
        link = output / "PrepaPilot"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"Directory symlinks unavailable: {exc}")
        try:
            with self.assertRaisesRegex(ValueError, "rediriger"):
                build.validate_output(output, source=self.sources, workspace=self.root)
            self.assertEqual(list(outside.iterdir()), [])
        finally:
            link.unlink()

    def test_build_defaults_use_local_delivery_and_construction_without_building(self):
        output = self.local / "Livraison"
        with patch.object(build, "WORKSPACE", self.root), patch.object(build, "ROOT", self.sources), patch.object(build.sys, "argv", ["build_windows.py"]), patch.object(build, "validate_output", return_value=output) as validate, patch.object(build.subprocess, "run") as run, patch("builtins.print"):
            build.main()
        validate.assert_called_once_with(str(output))
        arguments = run.call_args.args[0]
        self.assertEqual(arguments[arguments.index("--distpath") + 1], str(output))
        for option in ("--workpath", "--specpath"):
            self.assertEqual(arguments[arguments.index(option) + 1], str(self.local / "Construction"))
        self.assertFalse((self.root / "Outils").exists())

    def test_update_cli_defaults_to_local_staging_without_installing(self):
        with patch.object(updater, "WORKSPACE", self.root), patch.object(build.sys, "argv", ["mettre_a_jour_application.py"]), patch.object(updater, "install_update", return_value=self.local / "Archives" / "PrepaPilot-v2.1") as install, patch("builtins.print"):
            updater.main()
        install.assert_called_once_with(str(self.staging), archive_label="PrepaPilot-v2.1")

    def test_portable_build_channel_is_staged_and_source_identity_is_unchanged(self):
        channel = self.sources / 'assets' / 'update-channel.json'
        original = '{"repository":"original/PrepaPilot"}\n'
        channel.write_text(original, encoding='utf-8')
        staged = []
        def inspect_build(arguments, **kwargs):
            resource = next(value for value in arguments if value.endswith(';assets'))
            path = Path(resource[:-7])
            staged.append(path)
            self.assertNotEqual(path, self.sources / 'assets')
            self.assertEqual(json.loads((path / 'update-channel.json').read_text()), {'repository': 'publisher/PrepaPilot'})
            self.assertEqual(channel.read_text(), original)
            self.assertIn('mpsi_desktop.translations_updates', arguments)
        validate_output = build.validate_output
        with patch.object(build, 'WORKSPACE', self.root), patch.object(build, 'ROOT', self.sources), patch.object(build, 'validate_output', side_effect=lambda value: validate_output(value, source=self.sources, workspace=self.root)), patch.object(build.sys, 'argv', ['build_windows.py', '--repository', 'publisher/PrepaPilot']), patch.object(build.subprocess, 'run', side_effect=inspect_build), patch('builtins.print'):
            build.main()
        self.assertEqual(channel.read_text(), original)
        self.assertEqual(len(staged), 1)
        self.assertFalse(staged[0].exists())

    def test_portable_build_refuses_secrets_in_channel_and_invalid_repository(self):
        channel = self.sources / 'assets' / 'update-channel.json'
        channel.write_text('{"repository":"publisher/PrepaPilot","token":"PRIVATE"}', encoding='utf-8')
        with self.assertRaises(ValueError):
            build.stage_assets(self.sources / 'assets', self.root / 'staged-assets')
        self.assertFalse((self.root / 'staged-assets').exists())
        for repository in ('https://github.com/publisher/PrepaPilot', 'publisher-/PrepaPilot', 'publisher/project.git', 'publisher/..'):
            with self.subTest(repository=repository), self.assertRaises(ValueError):
                build.validate_repository(repository)
