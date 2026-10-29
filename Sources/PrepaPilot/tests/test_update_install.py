"""Final installer hand-off checks. Popen is always mocked: nothing is run."""
import ctypes
from dataclasses import replace
import hashlib
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import Mock, patch

from mpsi_desktop import update_install as install


class UpdateInstallTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='pp-install-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.cache = self.root / 'downloads'
        self.cache.mkdir()
        self.path = self.cache / 'PrepaPilot-2.19.0-Setup.exe'
        content = bytearray(1024)
        content[:2] = b'MZ'
        struct.pack_into('<I', content, 60, 128)
        content[128:132] = b'PE\0\0'
        struct.pack_into('<HH', content, 132, 0x14c, 1)
        struct.pack_into('<HH', content, 148, 224, 0x0002)
        struct.pack_into('<H', content, 152, 0x10b)
        self.content = bytes(content)
        self.path.write_bytes(self.content)
        self.digest = hashlib.sha256(self.content).hexdigest()
        # The test contract guarantees no actual executable can be started.
        self.popen_patch = patch.object(install.subprocess, 'Popen')
        self.popen = self.popen_patch.start()
        self.addCleanup(self.popen_patch.stop)

    def prepare(self, **changes):
        arguments = dict(path=self.path, version='2.19.0', cache_dir=self.cache, expected_digest=self.digest)
        arguments.update(changes)
        return install.prepare_install(**arguments)

    def test_preparation_records_the_exact_cache_file_digest_and_size(self):
        request = self.prepare()
        self.assertEqual(request.path, self.path)
        self.assertEqual(request.version, '2.19.0')
        self.assertEqual(request.size, len(self.content))
        self.assertEqual(request.sha256, self.digest)
        self.popen.assert_not_called()

    @unittest.skipUnless(install.sys.platform == 'win32', 'Windows 8.3 paths required')
    def test_preparation_accepts_short_file_and_cache_paths_without_weakening_checks(self):
        get_short_path = ctypes.WinDLL('kernel32', use_last_error=True).GetShortPathNameW
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

        short_file, short_cache = short_path(self.path), short_path(self.cache)
        if short_file == self.path and short_cache == self.cache:
            self.skipTest('8.3 aliases are not enabled on this volume')
        self.assertEqual(short_file.resolve(), self.path)
        self.assertEqual(short_cache.resolve(), self.cache)
        for path, cache in ((short_file, self.cache), (self.path, short_cache),
                            (short_file, short_cache)):
            with self.subTest(path=path, cache=cache):
                request = self.prepare(path=path, cache_dir=cache)
                self.assertEqual(request.path, self.path)
                self.assertEqual(request.size, len(self.content))
                self.assertEqual(request.sha256, self.digest)
                with self.assertRaises(ValueError):
                    self.prepare(path=path, cache_dir=cache, expected_digest='0' * 64)
                with self.assertRaises(ValueError):
                    self.prepare(path=path, cache_dir=cache.parent)
        self.popen.assert_not_called()

    def test_modified_same_size_download_is_rejected_during_preparation(self):
        self.path.write_bytes(self.content[:-1] + b'x')
        with self.assertRaises(ValueError):
            self.prepare()
        self.popen.assert_not_called()

    def test_truncated_download_and_invalid_checksum_formats_are_rejected(self):
        for digest in (None, '', 'a' * 63, 'g' * 64, self.digest.upper(), b'a' * 64):
            with self.assertRaises(ValueError):
                self.prepare(expected_digest=digest)
        self.path.write_bytes(b'MZ')
        with self.assertRaises(ValueError):
            self.prepare(expected_digest=hashlib.sha256(b'MZ').hexdigest())
        self.popen.assert_not_called()

    def test_files_outside_cache_and_in_subdirectories_are_rejected(self):
        for folder in (self.root / 'elsewhere', self.cache / 'nested'):
            folder.mkdir()
            outside = folder / self.path.name
            outside.write_bytes(self.content)
            with self.assertRaises(ValueError):
                self.prepare(path=outside)
        self.popen.assert_not_called()

    def test_filename_version_and_missing_file_are_rejected(self):
        other = self.cache / 'Other.exe'
        other.write_bytes(self.content)
        for changes in ({'path': other}, {'version': '2.20.0'}, {'version': '2.19.0-beta'},
                        {'version': '../2.19.0'}, {'version': None}):
            with self.assertRaises(ValueError):
                self.prepare(**changes)
        self.path.unlink()
        with self.assertRaises(ValueError):
            self.prepare()
        self.popen.assert_not_called()

    def test_junction_or_symlink_in_cache_ancestors_is_rejected(self):
        for method in ('is_symlink', 'is_junction'):
            for redirected in (self.path, self.cache, self.root):
                with self.subTest(method=method, redirected=redirected):
                    with patch.object(Path, method, lambda path: path == redirected):
                        with self.assertRaises(ValueError):
                            self.prepare()
        self.popen.assert_not_called()

    @unittest.skipUnless(install.sys.platform == 'win32', 'Windows junctions required')
    def test_real_junctions_in_cache_or_ancestor_are_rejected_before_resolution(self):
        import _winapi

        cache_link = self.root / 'cache-link'
        root_link = self.root / 'root-link'
        links = []
        try:
            for target, link in ((self.cache, cache_link), (self.root, root_link)):
                _winapi.CreateJunction(str(target), str(link))
                links.append(link)
                self.assertTrue(link.is_junction())
            for cache in (cache_link, root_link / self.cache.name):
                with self.subTest(cache=cache):
                    with self.assertRaises(ValueError):
                        self.prepare(path=cache / self.path.name, cache_dir=cache)
                    self.assertEqual(self.path.read_bytes(), self.content)
        finally:
            for link in reversed(links):
                link.rmdir()
        self.popen.assert_not_called()

    def test_file_modified_after_confirmation_is_rejected_before_launch(self):
        request = self.prepare()
        self.path.write_bytes(self.content[:-1] + b'x')
        with patch.object(install.sys, 'platform', 'win32'):
            with self.assertRaises(ValueError):
                install.launch_update(request, 'en')
        self.popen.assert_not_called()

    def test_request_size_is_rechecked_before_launch(self):
        request = replace(self.prepare(), size=999)
        with patch.object(install.sys, 'platform', 'win32'):
            with self.assertRaises(ValueError):
                install.launch_update(request)
        self.popen.assert_not_called()

    def test_other_platforms_cannot_launch_windows_installer(self):
        request = self.prepare()
        with patch.object(install.sys, 'platform', 'linux'):
            with self.assertRaises(ValueError):
                install.launch_update(request)
        self.popen.assert_not_called()

    def test_launch_has_explicit_language_detached_flags_and_no_shell(self):
        request = self.prepare()
        for language, expected in (('en', 'english'), ('fr', 'french'), ('unknown', 'french')):
            self.popen.reset_mock()
            with patch.object(install.sys, 'platform', 'win32'):
                with patch.object(install.sys, 'frozen', False, create=True):
                    with patch.object(install.subprocess, 'DETACHED_PROCESS', 8, create=True):
                        with patch.object(install.subprocess, 'CREATE_NEW_PROCESS_GROUP', 512, create=True):
                            result = install.launch_update(request, language)
            self.assertIs(result, self.popen.return_value)
            self.popen.assert_called_once()
            arguments, options = self.popen.call_args
            self.assertEqual(arguments, ([str(self.path), '/NORESTART', '/LANG=' + expected],))
            self.assertEqual(options['creationflags'], 8 | 512)
            self.assertTrue(options['close_fds'])
            self.assertEqual(options['cwd'], self.cache)
            self.assertFalse(options.get('shell', False))

    def test_launch_resets_child_pyinstaller_environment_without_mutating_parent(self):
        request = self.prepare()
        with patch.dict(os.environ, {'PYINSTALLER_RESET_ENVIRONMENT': '0', 'PATH': r'C:\Windows\System32'}):
            original = os.environ.copy()
            with patch.object(install.sys, 'platform', 'win32'):
                with patch.object(install.sys, 'frozen', False, create=True):
                    install.launch_update(request, 'en')
            child = self.popen.call_args.kwargs['env']
            self.assertEqual(child['PYINSTALLER_RESET_ENVIRONMENT'], '1')
            self.assertEqual(child['PATH'], original['PATH'])
            self.assertEqual(dict(os.environ), original)

    def test_frozen_runtime_dll_search_is_reset_and_bundle_removed_from_child_path(self):
        request = self.prepare()
        bundle = self.root / '_internal'
        library = Mock()
        library.kernel32.SetDllDirectoryW.return_value = 1
        system = str(self.root / 'system')
        with patch.dict(os.environ, {'PATH': os.pathsep.join((str(bundle), str(bundle / 'PySide6'), system))}):
            with patch.object(install.sys, 'platform', 'win32'):
                with patch.object(install.sys, 'frozen', True, create=True):
                    with patch.object(install.sys, '_MEIPASS', str(bundle), create=True):
                        with patch.object(ctypes, 'windll', library, create=True):
                            install.launch_update(request, 'en')
        library.kernel32.SetDllDirectoryW.assert_called_once_with(None)
        child = self.popen.call_args.kwargs['env']
        self.assertEqual(child['PATH'], system)
        self.assertEqual(child['PYINSTALLER_RESET_ENVIRONMENT'], '1')

    def test_process_start_failure_propagates_for_translated_application_message(self):
        request = self.prepare()
        self.popen.side_effect = OSError('process start refused')
        with patch.object(install.sys, 'platform', 'win32'):
            with patch.object(install.sys, 'frozen', False, create=True):
                with self.assertRaises(OSError):
                    install.launch_update(request, 'en')


if __name__ == '__main__':
    unittest.main()
