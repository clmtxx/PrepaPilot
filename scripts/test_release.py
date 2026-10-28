"""Regression tests for privacy, release identity and bounded file operations."""
from __future__ import annotations

import hashlib
import io
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile


SPEC = importlib.util.spec_from_file_location("build_release", Path(__file__).with_name("build_release.py"))
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


def make_executable(target: Path, machine: int = 0x8664) -> None:
    header = bytearray(140)
    header[:2] = b"MZ"
    struct.pack_into("<I", header, 0x3C, 128)
    header[128:132] = b"PE\0\0"
    struct.pack_into("<H", header, 132, machine)
    target.write_bytes(header)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.app = self.root / "app"
        self.app.mkdir()
        make_executable(self.app / "PrepaPilot.exe")
        (self.app / "_internal" / "licenses").mkdir(parents=True)
        (self.app / "_internal" / "python312.dll").write_bytes(b"runtime")
        (self.app / "_internal" / "licenses" / "Python-LICENSE.txt").write_text("license", encoding="utf-8")
        self.guide = self.root / "INSTALLER.md"
        self.guide.write_text("Installer PrépaPilot", encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def test_root_personal_data_and_diagnostics_never_enter_payload(self):
        (self.app / "data").mkdir()
        (self.app / "data" / "mpsi.sqlite3").write_text("PRIVATE", encoding="utf-8")
        for name in ("installation.json", "self-test.log", "self-test-ok.txt", "unknown.pdf"):
            (self.app / name).write_text("PRIVATE", encoding="utf-8")
        payload = release.stage_payload(self.app, self.root / "payload", self.guide)
        self.assertEqual({file.name for file in payload.iterdir()}, {"PrepaPilot.exe", "_internal", "GUIDE.md"})
        self.assertTrue((self.app / "data" / "mpsi.sqlite3").is_file())
        self.assertTrue((payload / "_internal" / "licenses" / "Python-LICENSE.txt").is_file())
        archive = self.root / "portable.zip"
        release.write_portable_zip(payload, archive)
        with zipfile.ZipFile(archive) as zipped:
            self.assertIn("PrepaPilot/PrepaPilot.exe", zipped.namelist())
            self.assertFalse(any("data/" in name or "self-test" in name or "installation.json" in name for name in zipped.namelist()))

    def test_internal_private_data_aborts_before_copying(self):
        private = self.app / "_internal" / "nested" / "data"
        private.mkdir(parents=True)
        (private / "mpsi.sqlite3").write_text("PRIVATE", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "données privées"):
            release.stage_payload(self.app, self.root / "payload", self.guide)
        self.assertFalse((self.root / "payload").exists())

    def test_internal_diagnostic_aborts(self):
        (self.app / "_internal" / "self-test.log").write_text("diagnostic", encoding="utf-8")
        with self.assertRaises(ValueError):
            release.checked_runtime_files(self.app / "_internal")

    def test_redirect_in_runtime_is_rejected(self):
        file = self.app / "_internal" / "python312.dll"
        original = release.is_redirect
        with patch.object(release, "is_redirect", side_effect=lambda candidate: candidate == file or original(candidate)):
            with self.assertRaisesRegex(ValueError, "redirection"):
                release.stage_payload(self.app, self.root / "payload", self.guide)

    def test_only_windows_x64_executable_is_accepted(self):
        make_executable(self.app / "PrepaPilot.exe", machine=0x14C)
        with self.assertRaisesRegex(ValueError, "x64"):
            release.stage_payload(self.app, self.root / "payload", self.guide)

    def test_version_is_read_without_executing_source(self):
        module = self.root / "source" / "mpsi_desktop"
        module.mkdir(parents=True)
        (module / "__init__.py").write_text('__version__ = "2.16.0"\nraise RuntimeError("must not execute")\n', encoding="utf-8")
        self.assertEqual(release.read_version(module.parent), "2.16.0")
        release.check_expected_version("2.16.0", "2.16.0")
        with self.assertRaisesRegex(ValueError, "incohérente"):
            release.check_expected_version("2.16.0", "2.16.1")
        (module / "__init__.py").write_text('__version__ = "2.16.0-beta"', encoding="utf-8")
        with self.assertRaises(ValueError):
            release.read_version(module.parent)

    def test_portable_archive_refuses_installer_marker(self):
        payload = release.stage_payload(self.app, self.root / "payload", self.guide)
        (payload / "installation.json").write_text(json.dumps(release.INSTALLATION_MARKER), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "marqueur"):
            release.write_portable_zip(payload, self.root / "portable.zip")

    def test_installer_compilation_receives_explicit_payload_and_marker(self):
        payload = release.stage_payload(self.app, self.root / "payload", self.guide)
        artifacts = self.root / "artifacts"
        artifacts.mkdir()
        expected = artifacts / "PrepaPilot-2.16.0-Setup.exe"
        def pretend_compile(command, **kwargs):
            self.assertIn(f"/DAppDir={payload}", command)
            self.assertIn("/DAppVersion=2.16.0", command)
            self.assertEqual(json.loads((payload / "installation.json").read_text()), {"data_mode": "localappdata"})
            expected.write_bytes(b"installer")
        with patch.object(release.subprocess, "run", side_effect=pretend_compile):
            actual = release.compile_installer(Path("ISCC.exe"), payload, artifacts, "2.16.0", repo=self.root)
        self.assertEqual(actual, expected)

    def test_checksums_describe_only_requested_artifacts(self):
        artifact = self.root / "setup.exe"
        artifact.write_bytes(b"public binary")
        sums = self.root / "SHA256SUMS.txt"
        release.write_checksums([artifact], sums)
        self.assertEqual(sums.read_text(), f"{hashlib.sha256(b'public binary').hexdigest()}  setup.exe\n")

    def test_cleanup_is_bounded_to_one_generated_work_directory(self):
        build_root = self.root / ".build" / "release"
        work = build_root / "release-example"
        work.mkdir(parents=True)
        (work / "scratch.txt").write_text("scratch", encoding="utf-8")
        unrelated = build_root / "keep-example"
        unrelated.mkdir()
        nested = work / "release-nested"
        nested.mkdir()
        with self.assertRaises(ValueError):
            release.safe_remove_work(self.app, build_root)
        with self.assertRaises(ValueError):
            release.safe_remove_work(build_root, build_root)
        with self.assertRaises(ValueError):
            release.safe_remove_work(unrelated, build_root)
        with self.assertRaises(ValueError):
            release.safe_remove_work(nested, build_root)
        self.assertTrue((self.app / "PrepaPilot.exe").is_file())
        release.safe_remove_work(work, build_root)
        self.assertFalse(work.exists())
        self.assertTrue(unrelated.is_dir())

    @unittest.skipUnless(release.sys.platform == "win32", "Windows 8.3 paths required")
    def test_cleanup_accepts_windows_short_paths_for_root_or_work(self):
        import ctypes

        build_root = self.root / "Long temporary build directory" / "release work root"
        work = build_root / "release-example-long-directory"
        work.mkdir(parents=True)
        sibling = build_root / "keep-this-directory"
        sibling.mkdir()
        sentinel = sibling / "keep.txt"
        sentinel.write_text("keep", encoding="utf-8")

        get_short_path = ctypes.WinDLL("kernel32", use_last_error=True).GetShortPathNameW
        get_short_path.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32)
        get_short_path.restype = ctypes.c_uint32

        def short_path(path):
            size = get_short_path(str(path), None, 0)
            if not size:
                raise ctypes.WinError(ctypes.get_last_error())
            buffer = ctypes.create_unicode_buffer(size)
            written = get_short_path(str(path), buffer, size)
            if not written or written >= size:
                raise ctypes.WinError(ctypes.get_last_error())
            return Path(buffer.value)

        short_root, short_work = short_path(build_root), short_path(work)
        if short_root == build_root.resolve():
            self.skipTest("8.3 aliases are not enabled on this volume")
        self.assertEqual(short_root.resolve(), build_root.resolve())
        self.assertEqual(short_work.resolve(), work.resolve())
        for target, root in ((short_root / work.name, build_root),
                             (work, short_root), (short_work, short_root)):
            with self.subTest(target=target, root=root):
                work.mkdir(exist_ok=True)
                (work / "scratch.txt").write_text("scratch", encoding="utf-8")
                release.safe_remove_work(target, root)
                self.assertFalse(work.exists())
                self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

    @unittest.skipUnless(release.sys.platform == "win32", "Windows junctions required")
    def test_cleanup_rejects_junctions_in_target_root_and_ancestors(self):
        import _winapi

        build_root = self.root / "real-parent" / "release-root"
        work = build_root / "release-original"
        work.mkdir(parents=True)
        sentinel = work / "keep.txt"
        sentinel.write_text("keep", encoding="utf-8")
        target_link = build_root / "release-link"
        root_link = self.root / "root-link"
        parent_link = self.root / "parent-link"
        links = []
        try:
            for target, link in ((work, target_link), (build_root, root_link),
                                 (build_root.parent, parent_link)):
                _winapi.CreateJunction(str(target), str(link))
                links.append(link)
                self.assertTrue(release.is_redirect(link))
            for target, root in ((target_link, build_root),
                                 (root_link / work.name, root_link),
                                 (parent_link / build_root.name / work.name,
                                  parent_link / build_root.name)):
                with self.subTest(target=target, root=root):
                    with self.assertRaisesRegex(ValueError, "redirection"):
                        release.safe_remove_work(target, root)
                    self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")
        finally:
            for link in reversed(links):
                link.rmdir()

    def test_update_repository_is_a_public_github_identity(self):
        for repository in ('alice/PrepaPilot', 'a/b', 'a-b/project.name_1-2', 'a' * 39 + '/' + 'b' * 100):
            with self.subTest(repository=repository):
                self.assertEqual(release.validate_repository(repository), repository)
        for repository in ('https://github.com/alice/PrepaPilot', '../project', 'alice/..', 'alice/.',
                           '-alice/project', 'alice-/project', 'alice/project/extra', 'alice/project?token=secret',
                           'alice/project.git', 'alice/project\n', 'alice/project name', 'a' * 40 + '/project', 'alice/' + 'b' * 101,
                           'alice/project;echo', 'alice/project`whoami`', '', None):
            with self.subTest(repository=repository), self.assertRaises(ValueError):
                release.validate_repository(repository)

    def make_assets(self):
        assets = self.root / 'source-assets'
        assets.mkdir()
        (assets / 'app.ico').write_bytes(b'icon')
        return assets

    def test_build_identity_is_injected_into_staging_without_modifying_sources(self):
        assets = self.make_assets()
        channel = assets / release.UPDATE_CHANNEL
        original = '{"repository":"original/PrepaPilot"}\n'
        channel.write_text(original, encoding='utf-8')
        staging = release.stage_assets(assets, self.root / 'staged-assets', 'publisher/PrepaPilot')
        self.assertEqual(json.loads((staging / release.UPDATE_CHANNEL).read_text()), {'repository': 'publisher/PrepaPilot'})
        self.assertEqual(channel.read_text(), original)
        self.assertEqual((staging / 'app.ico').read_bytes(), b'icon')

    def test_optional_channel_is_reused_and_absence_does_not_invent_a_repository(self):
        assets = self.make_assets()
        staging = release.stage_assets(assets, self.root / 'unconfigured-assets')
        self.assertFalse((staging / release.UPDATE_CHANNEL).exists())
        (assets / release.UPDATE_CHANNEL).write_text('{"repository":"publisher/PrepaPilot"}', encoding='utf-8')
        staging = release.stage_assets(assets, self.root / 'configured-assets')
        self.assertEqual(release.read_update_repository(staging / release.UPDATE_CHANNEL), 'publisher/PrepaPilot')

    def test_channel_with_secrets_or_invalid_content_is_rejected_before_copying(self):
        assets = self.make_assets()
        channel = assets / release.UPDATE_CHANNEL
        invalid = ('{"repository":"publisher/PrepaPilot","token":"PRIVATE"}', '[]', 'not json',
                   '{"repository":"https://github.com/publisher/PrepaPilot"}', '{}', 'x' * 4097)
        for index, content in enumerate(invalid):
            channel.write_text(content, encoding='utf-8')
            destination = self.root / f'invalid-{index}'
            with self.subTest(content=content[:100]), self.assertRaises(ValueError):
                release.stage_assets(assets, destination)
            self.assertFalse(destination.exists())

    def test_existing_bundle_channel_is_validated_before_distribution(self):
        assets = self.app / '_internal' / 'assets'
        assets.mkdir()
        (assets / release.UPDATE_CHANNEL).write_text('{"repository":"publisher/PrepaPilot","token":"PRIVATE"}', encoding='utf-8')
        with self.assertRaises(ValueError):
            release.stage_payload(self.app, self.root / 'payload', self.guide)
        self.assertFalse((self.root / 'payload').exists())

    def test_changing_repository_requires_recompilation_of_an_existing_bundle(self):
        with patch.object(release.sys, 'stderr', new_callable=io.StringIO) as errors:
            result = release.main(['--app-dir', str(self.app), '--repository', 'publisher/PrepaPilot', '--portable-only'])
        self.assertEqual(result, 1)
        self.assertIn('nouvelle compilation', errors.getvalue())
        self.assertFalse((self.app / '_internal' / 'assets').exists())

    def test_frozen_build_embeds_staged_channel_and_update_translation(self):
        source = self.root / 'source'
        (source / 'assets').mkdir(parents=True)
        (source / 'assets' / 'app.ico').write_bytes(b'icon')
        work = self.root / 'work'
        work.mkdir()
        with patch.object(release.subprocess, 'run') as run:
            release.build_frozen(source, work, '2.19.0', 'publisher/PrepaPilot')
        command = run.call_args.args[0]
        self.assertIn(f'{work / "assets"};assets', command)
        self.assertNotIn(f'{source / "assets"};assets', command)
        self.assertIn('mpsi_desktop.translations_updates', command)
        self.assertEqual(release.read_update_repository(work / 'assets' / release.UPDATE_CHANNEL), 'publisher/PrepaPilot')
        self.assertFalse((source / 'assets' / release.UPDATE_CHANNEL).exists())

    def google_client(self):
        path = self.root / 'desktop-client.json'
        path.write_text(json.dumps({'installed': {'client_id': '123456789-publisher.apps.googleusercontent.com',
                                               'client_secret': 'fixture-only', 'project_id': 'publisher'}}), encoding='utf-8')
        return path

    def test_shared_google_client_is_injected_without_source_or_bundle_mutation(self):
        client = self.google_client()
        original = client.read_bytes()
        assets = self.make_assets()
        staging = release.stage_assets(assets, self.root / 'google-assets', google_oauth_client=client,
                                       require_google_drive=True)
        expected = {'installed': {'client_id': '123456789-publisher.apps.googleusercontent.com', 'client_secret': 'fixture-only'}}
        self.assertEqual(json.loads((staging / release.GOOGLE_OAUTH_ASSET).read_text()), expected)
        self.assertFalse((assets / release.GOOGLE_OAUTH_ASSET).exists())
        payload = release.stage_payload(self.app, self.root / 'google-payload', self.guide,
                                        google_oauth_client=client, require_google_drive=True)
        self.assertEqual(json.loads((payload / '_internal/assets' / release.GOOGLE_OAUTH_ASSET).read_text()), expected)
        self.assertFalse((self.app / '_internal/assets').exists())
        self.assertEqual(client.read_bytes(), original)
        archive = self.root / 'google-portable.zip'
        release.write_portable_zip(payload, archive)
        with zipfile.ZipFile(archive) as zipped:
            config = json.loads(zipped.read('PrepaPilot/_internal/assets/' + release.GOOGLE_OAUTH_ASSET))
            self.assertEqual(config, expected)
            self.assertFalse(any('/cloud/' in name or 'credentials.bin' in name for name in zipped.namelist()))

    def test_embedded_google_client_is_normalized_and_tokens_are_rejected(self):
        assets = self.app / '_internal/assets'
        assets.mkdir()
        client = self.google_client()
        target = assets / release.GOOGLE_OAUTH_ASSET
        target.write_bytes(client.read_bytes())
        original = target.read_bytes()
        payload = release.stage_payload(self.app, self.root / 'clean-client', self.guide, require_google_drive=True)
        normalized = json.loads((payload / '_internal/assets' / release.GOOGLE_OAUTH_ASSET).read_text())
        self.assertEqual(set(normalized['installed']), {'client_id', 'client_secret'})
        self.assertEqual(target.read_bytes(), original)
        for invalid in ({'installed': {**normalized['installed'], 'access_token': 'PRIVATE'}},
                        {'installed': normalized['installed'], 'refresh_token': 'PRIVATE'},
                        {'web': normalized['installed']}, {'type': 'service_account'}):
            target.write_text(json.dumps(invalid), encoding='utf-8')
            with self.subTest(config=invalid), self.assertRaises(ValueError):
                release.stage_payload(self.app, self.root / 'invalid-client', self.guide)
            self.assertFalse((self.root / 'invalid-client').exists())

    def test_google_requirement_blocks_before_build_or_output_creation(self):
        assets = self.make_assets()
        with self.assertRaisesRegex(ValueError, '--google-oauth-client'):
            release.stage_assets(assets, self.root / 'required-google', require_google_drive=True)
        self.assertFalse((self.root / 'required-google').exists())
        with patch.object(release, 'REPO', self.root), patch.object(release, 'SOURCE', self.root / 'source'), \
                patch.object(release, 'read_version', return_value='2.22.0'), \
                patch.object(release, 'find_iscc') as compiler, patch.object(release, 'build_frozen') as freeze, \
                patch.object(release.sys, 'stderr', new_callable=io.StringIO) as errors:
            result = release.main(['--require-google-drive'])
        self.assertEqual(result, 1)
        self.assertIn('--google-oauth-client', errors.getvalue())
        compiler.assert_not_called()
        freeze.assert_not_called()
        self.assertFalse((self.root / 'dist').exists())

    def test_required_google_client_supports_existing_bundle_via_staging(self):
        client = self.google_client()
        (self.root / 'INSTALLER.md').write_text('French guide', encoding='utf-8')
        (self.root / 'INSTALL.en.md').write_text('English guide', encoding='utf-8')
        with patch.object(release, 'REPO', self.root), patch.object(release, 'read_version', return_value='2.22.0'):
            result = release.main(['--app-dir', str(self.app), '--portable-only', '--skip-self-test',
                                   '--google-oauth-client', str(client), '--require-google-drive'])
        self.assertEqual(result, 0)
        self.assertFalse((self.app / '_internal/assets').exists())
        with zipfile.ZipFile(self.root / 'dist/PrepaPilot-2.22.0-Windows-portable.zip') as zipped:
            self.assertIn('PrepaPilot/_internal/assets/' + release.GOOGLE_OAUTH_ASSET, zipped.namelist())


if __name__ == "__main__":
    unittest.main()
