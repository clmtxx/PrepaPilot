"""Updater protocol tests. All HTTP is mocked; no release is contacted."""
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import Request

from mpsi_desktop import app_updates as updates


REPOSITORY = 'school/PrepaPilot'
VERSION = '2.19.0'
NAME = f'PrepaPilot-{VERSION}-Setup.exe'
BASE = f'https://github.com/{REPOSITORY}/releases/'


def pe_content(machine=0x14c):
    content = bytearray(1024)
    content[:2] = b'MZ'
    struct.pack_into('<I', content, 60, 128)
    content[128:132] = b'PE\0\0'
    struct.pack_into('<HH', content, 132, machine, 1)
    struct.pack_into('<HH', content, 148, 224 if machine == 0x14c else 240, 0x0002)
    struct.pack_into('<H', content, 152, 0x10b if machine == 0x14c else 0x20b)
    return bytes(content)


def release(content=None, **changes):
    content = pe_content() if content is None else content
    data = dict(tag_name='v' + VERSION, draft=False, prerelease=False,
                html_url=BASE + 'tag/v' + VERSION, assets=[
                    dict(name=NAME, size=len(content), state='uploaded',
                         browser_download_url=BASE + 'download/v' + VERSION + '/' + NAME),
                    dict(name='SHA256SUMS.txt', size=180, state='uploaded',
                         browser_download_url=BASE + 'download/v' + VERSION + '/SHA256SUMS.txt'),
                ])
    data.update(changes)
    return data


class Response(io.BytesIO):
    def __init__(self, content, headers=None, url=None, status=200):
        super().__init__(content)
        self.headers = {} if headers is None else headers
        self.url, self.status = url, status

    def geturl(self):
        return self.url


class AppUpdatesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pp-updates-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def assert_code(self, code, callable_, *args, **kwargs):
        with self.assertRaises(updates.UpdateError) as caught:
            callable_(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def info(self, content=None):
        content = pe_content() if content is None else content
        return updates.ReleaseInfo(VERSION, NAME, BASE + 'download/v' + VERSION + '/' + NAME,
                                   BASE + 'download/v' + VERSION + '/SHA256SUMS.txt',
                                   BASE + 'tag/v' + VERSION, len(content), REPOSITORY)

    def replies(self, content=None, checksum=None, *, headers=None):
        content = pe_content() if content is None else content
        checksum = (hashlib.sha256(content).hexdigest() + '  ' + NAME + '\n').encode() if checksum is None else checksum
        return [Response(checksum), Response(content, headers)]

    def check(self, data=None, current='2.18.0'):
        with patch.object(updates, '_open', return_value=Response(json.dumps(release() if data is None else data).encode())):
            return updates.check_release(REPOSITORY, current)

    def test_absent_or_empty_channel_stays_offline(self):
        self.assertIsNone(updates.read_channel(self.root))
        for value in ({}, {'repository': ''}, {'repository': None}):
            (self.root / 'update-channel.json').write_text(json.dumps(value), encoding='utf-8')
            self.assertIsNone(updates.read_channel(self.root))

    def test_channel_reads_bounded_repository_configuration(self):
        path = self.root / 'update-channel.json'
        path.write_text(json.dumps({'repository': REPOSITORY}), encoding='utf-8-sig')
        self.assertEqual(updates.read_channel(self.root), REPOSITORY)
        for value in ('https://github.com/school/app', 'owner/../app', 'a/.', 'owner/app.git',
                      'owner-/app', '-owner/app', 'a' * 40 + '/app', 12, 'a/b?token=secret'):
            path.write_text(json.dumps({'repository': value}), encoding='utf-8')
            self.assert_code('invalid_channel', updates.read_channel, self.root)
        for value in ('[]', '{broken', ' ' * 4097):
            path.write_text(value, encoding='utf-8')
            self.assert_code('invalid_channel', updates.read_channel, self.root)

    def test_newer_release_uses_exact_setup_checksum_and_numeric_version_order(self):
        info = self.check(current='2.9.99')
        self.assertEqual(info, self.info())
        self.assertIsNone(self.check(current='2.19.0'))
        self.assertIsNone(self.check(current='3.0.0'))

    def test_prereleases_drafts_and_noncanonical_tags_are_never_offered(self):
        for changes in ({'draft': True}, {'prerelease': True}, {'tag_name': 'v2.19.0-beta'},
                        {'tag_name': '2.19.0'}, {'tag_name': 'v02.19.0'}, {'tag_name': 'v9999999.0.0'}):
            self.assertIsNone(self.check(release(**changes)))

    def test_incomplete_ambiguous_or_oversized_assets_are_rejected(self):
        for mutation in ('missing', 'duplicate', 'oversized', 'not_uploaded', 'size_boolean'):
            data = release()
            if mutation == 'missing':
                data['assets'].pop()
            elif mutation == 'duplicate':
                data['assets'].append(data['assets'][0].copy())
            elif mutation == 'oversized':
                data['assets'][0]['size'] = updates.MAX_INSTALLER_SIZE + 1
            elif mutation == 'not_uploaded':
                data['assets'][0]['state'] = 'new'
            else:
                data['assets'][0]['size'] = True
            self.assert_code('invalid_release', self.check, data)

    def test_release_and_download_urls_cannot_escape_configured_repository(self):
        for change in ('page', 'installer', 'checksum'):
            data = release()
            if change == 'page':
                data['html_url'] = 'https://github.com/other/app/releases/tag/v2.19.0'
            else:
                data['assets'][0 if change == 'installer' else 1]['browser_download_url'] = 'https://evil.example/installer.exe'
            self.assert_code('invalid_release', self.check, data)

    def test_github_canonical_repository_case_does_not_disable_updates(self):
        data = release()
        data['html_url'] = data['html_url'].replace('/school/', '/School/')
        for asset in data['assets']:
            asset['browser_download_url'] = asset['browser_download_url'].replace('/school/', '/School/')
        self.assertEqual(self.check(data), self.info())

    def test_network_and_rate_limit_errors_are_safe_and_404_means_no_release(self):
        for status in (403, 404, 429, 500):
            error = HTTPError('https://api.github.com', status, 'private untrusted response', {}, None)
            with patch.object(updates, '_open', side_effect=error):
                if status == 404:
                    self.assertIsNone(updates.check_release(REPOSITORY, '2.18.0'))
                else:
                    code = 'rate_limited' if status in (403, 429) else 'network'
                    self.assert_code(code, updates.check_release, REPOSITORY, '2.18.0')
        for error in (URLError('offline'), TimeoutError('timeout')):
            with patch.object(updates, '_open', side_effect=error):
                self.assert_code('network', updates.check_release, REPOSITORY, '2.18.0')

    def test_metadata_response_is_bounded_and_invalid_json_is_rejected(self):
        for content, code in ((b'x' * (updates.MAX_METADATA_SIZE + 1), 'download_size'),
                              (b'not json', 'invalid_release'), (b'[]', 'invalid_release')):
            with patch.object(updates, '_open', return_value=Response(content)):
                self.assert_code(code, updates.check_release, REPOSITORY, '2.18.0')

    def test_https_redirects_only_allow_github_repository_and_its_asset_cdn(self):
        initial = self.info().installer_url
        handler = updates._SafeRedirects(REPOSITORY, 'asset')
        request = Request(initial)
        for allowed in (initial, 'https://release-assets.githubusercontent.com/github-production-release-asset-2e65be/1/file?sig=test',
                        'https://objects.githubusercontent.com/github-production-release-asset-2e65be/1/file'):
            self.assertIsNotNone(handler.redirect_request(request, None, 302, 'Moved', {}, allowed))
        for bad in ('http://github.com/school/PrepaPilot/releases/download/v2.19.0/' + NAME,
                    'https://github.com/other/app/releases/download/v2.19.0/' + NAME,
                    'https://github.com.evil.example/x', 'https://evil.example/x',
                    'https://release-assets.githubusercontent.com/other/file',
                    'https://[invalid/file',
                    'https://user:password@github.com/school/PrepaPilot/releases/download/v2.19.0/' + NAME,
                    initial + '#fragment', initial.replace('github.com', 'github.com:444')):
            self.assert_code('invalid_release', handler.redirect_request, request, None, 302, 'Moved', {}, bad)
        # A caller cannot introduce a CDN address as its initial trusted request.
        self.assert_code('invalid_release', updates._validate_url,
                         'https://release-assets.githubusercontent.com/github-production-release-asset-x/file', REPOSITORY, 'asset')

    def test_api_redirect_cannot_move_to_another_repository_or_a_cdn(self):
        handler = updates._SafeRedirects(REPOSITORY, 'api')
        request = Request(f'https://api.github.com/repos/{REPOSITORY}/releases/latest')
        for url in ('https://api.github.com/repos/other/app/releases/latest',
                    'https://release-assets.githubusercontent.com/github-production-release-asset-x/file'):
            self.assert_code('invalid_release', handler.redirect_request, request, None, 302, 'Moved', {}, url)

    def test_requests_are_get_only_with_no_authentication_and_validate_final_url(self):
        info = self.info()
        opener = unittest.mock.Mock()
        response = Response(b'fixture', url=info.installer_url)
        opener.open.return_value = response
        with patch.object(updates, 'build_opener', return_value=opener):
            self.assertIs(updates._open(info.installer_url, REPOSITORY, 'asset'), response)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_method(), 'GET')
        self.assertIsNone(request.data)
        self.assertNotIn('Authorization', request.headers)
        self.assertEqual(opener.open.call_args.kwargs['timeout'], updates.NETWORK_TIMEOUT)
        for url, status, headers in (('https://evil.example/installer.exe', 200, {}),
                                     (info.installer_url, 206, {}),
                                     (info.installer_url, 200, {'Content-Encoding': 'gzip'})):
            response = Response(b'fixture', headers=headers, url=url, status=status)
            opener.open.return_value = response
            with patch.object(updates, 'build_opener', return_value=opener):
                self.assert_code('invalid_release' if status == 200 and not headers else 'network',
                                 updates._open, info.installer_url, REPOSITORY, 'asset')
            self.assertTrue(response.closed)

    def test_verified_pe32_and_pe64_downloads_are_atomic_and_report_progress(self):
        for machine in (0x14c, 0x8664):
            content = pe_content(machine)
            progress = []
            cache = self.root / str(machine)
            with patch.object(updates, '_open', side_effect=self.replies(content)):
                path = updates.download_release(self.info(content), cache, lambda done, total: progress.append((done, total)))
            self.assertEqual(path.name, NAME)
            self.assertEqual(path.read_bytes(), content)
            self.assertEqual(list(cache.glob('*.part')), [])
            self.assertEqual(progress[0], (0, len(content)))
            self.assertEqual(progress[-1], (len(content), len(content)))

    def test_checksum_rejects_missing_duplicate_malformed_and_traversal_entries(self):
        digest = hashlib.sha256(pe_content()).hexdigest()
        for text in (digest + '  Other.exe', digest + '  ' + NAME + '\n' + digest + '  ' + NAME,
                     'not a checksum', digest + '  ../' + NAME, digest[:-1] + '  ' + NAME,
                     digest + '  ' + NAME + '\n' + digest + '  /absolute.exe'):
            with patch.object(updates, '_open', return_value=Response(text.encode())) as request:
                self.assert_code('invalid_checksum', updates.download_release, self.info(), self.root)
                self.assertEqual(request.call_count, 1)
            self.assertEqual(list(self.root.iterdir()), [])

    def test_binary_marker_bom_and_additional_portable_checksum_are_supported(self):
        digest = hashlib.sha256(pe_content()).hexdigest()
        text = '\ufeff' + digest.upper() + ' *' + NAME + '\n' + 'a' * 64 + '  PrepaPilot-2.19.0-Windows-portable.zip\n'
        self.assertEqual(updates._expected_checksum(text.encode(), NAME), digest)

    def test_modified_download_is_deleted_without_replacing_existing_cached_installer(self):
        destination = self.root / NAME
        destination.write_bytes(b'previous verified file')
        replies = self.replies(checksum=('0' * 64 + '  ' + NAME).encode())
        with patch.object(updates, '_open', side_effect=replies):
            self.assert_code('checksum_mismatch', updates.download_release, self.info(), self.root)
        self.assertEqual(destination.read_bytes(), b'previous verified file')
        self.assertEqual(list(self.root.glob('*.part')), [])

    def test_truncated_oversized_or_wrong_content_length_downloads_are_deleted(self):
        for content, headers in ((pe_content()[:-1], {}), (pe_content() + b'x', {}),
                                  (pe_content(), {'Content-Length': '1023'}),
                                  (pe_content(), {'Content-Length': 'invalid'})):
            with patch.object(updates, '_open', side_effect=self.replies(content, headers=headers)):
                self.assert_code('download_size', updates.download_release, self.info(), self.root)
            self.assertEqual(list(self.root.iterdir()), [])

    def test_html_or_invalid_pe_cannot_be_offered_even_with_matching_hash(self):
        fixtures = [b'<html>not an installer</html>', b'MZ' + bytes(1022)]
        for offset, replacement in ((128, b'NOPE'), (132, b'\x00\x00'), (152, b'\x00\x00')):
            content = bytearray(pe_content())
            content[offset:offset + len(replacement)] = replacement
            fixtures.append(bytes(content))
        for content in fixtures:
            with patch.object(updates, '_open', side_effect=self.replies(content)):
                self.assert_code('invalid_installer', updates.download_release, self.info(content), self.root)
            self.assertEqual(list(self.root.iterdir()), [])

    def test_interrupted_download_removes_own_partial_file(self):
        checksum, response = self.replies()
        with patch.object(response, 'read', side_effect=[pe_content()[:512], URLError('disconnected')]):
            with patch.object(updates, '_open', side_effect=[checksum, response]):
                self.assert_code('network', updates.download_release, self.info(), self.root)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_download_has_an_overall_time_bound(self):
        with patch.object(updates, '_open', side_effect=self.replies()):
            with patch.object(updates.time, 'monotonic', side_effect=[0, 1, 2, 3, updates.DOWNLOAD_SECONDS + 4]):
                self.assert_code('network', updates.download_release, self.info(), self.root)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_untrusted_release_info_cannot_make_network_requests_or_escape_cache(self):
        info = self.info()
        for changes in ({'installer_name': '../escape.exe'}, {'size': updates.MAX_INSTALLER_SIZE + 1},
                        {'checksum_url': 'https://evil.example/checksums'}, {'repository': 'a/b/../c'}):
            forged = updates.ReleaseInfo(**(vars(info) | changes))
            with patch.object(updates, '_open') as request:
                self.assert_code('invalid_channel' if 'repository' in changes else 'invalid_release',
                                 updates.download_release, forged, self.root)
                request.assert_not_called()

    def test_disk_errors_are_reported_and_never_expose_partial_download(self):
        with patch.object(updates, '_open', side_effect=self.replies()):
            with patch.object(updates.os, 'replace', side_effect=PermissionError('locked')):
                self.assert_code('disk_error', updates.download_release, self.info(), self.root)
        self.assertEqual(list(self.root.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
