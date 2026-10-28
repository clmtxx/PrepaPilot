"""Drive transfer protocol tests; HTTP is mocked, no account is contacted."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

from mpsi_desktop import google_drive as drive
from mpsi_desktop.google_auth import GoogleCancelled, GoogleDriveError


def metadata(file_id='file123', content=b'abc', **extra):
    return dict(id=file_id, name='fixture.bin', mimeType='application/octet-stream', size=str(len(content)),
                md5Checksum=hashlib.md5(content).hexdigest(), appProperties={}, **extra)


def reply(value, status=200, headers=None):
    return status, headers or {}, json.dumps(value).encode()


class GoogleDriveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='prepapilot-google-drive-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.credentials = Mock()
        self.credentials.access_token.return_value = 'fixture-access-token'
        self.client = drive.DriveClient(self.credentials)
        self.session = drive.UPLOAD_API + '?uploadType=resumable&upload_id=fixture'

    def test_pagination_collects_each_id_once_and_search_is_limited(self):
        with patch.object(self.client, '_json', side_effect=[
            {'files': [metadata('first')], 'nextPageToken': 'page-two'},
            {'files': [metadata('first'), metadata('second')]},
        ]) as request:
            self.assertEqual([row['id'] for row in self.client.list_children('folder')], ['first', 'second'])
        queries = [parse_qs(urlsplit(call.args[0]).query) for call in request.call_args_list]
        self.assertEqual(queries[0]['q'], ["'folder' in parents and trashed = false"])
        self.assertEqual(queries[1]['pageToken'], ['page-two'])
        with patch.object(self.client, '_json', return_value={'files': []}) as request:
            self.client.list_backup_folders()
        self.assertIn("key='prepapilot' and value='backup-v1'", parse_qs(urlsplit(request.call_args.args[0]).query)['q'][0])

    def test_invalid_ids_incomplete_search_and_pagination_cycles_fail_closed(self):
        with patch.object(self.client, '_json') as request:
            for invalid in ["x' or trashed=true", '../other', 'https://drive.google.com/file/a', None]:
                with self.assertRaises(GoogleDriveError):
                    self.client.list_children(invalid)
            request.assert_not_called()
        with patch.object(self.client, '_json', return_value={'files': [], 'incompleteSearch': True}):
            with self.assertRaises(GoogleDriveError):
                self.client.list_children('folder')
        with patch.object(self.client, '_json', return_value={'files': [], 'nextPageToken': 'repeat'}):
            with self.assertRaises(GoogleDriveError):
                self.client.list_children('folder')

    def test_unauthorized_request_refreshes_once_then_reports_failure(self):
        with patch.object(drive, 'request_bytes', side_effect=[GoogleDriveError('expired', status=401), reply({})]) as request:
            self.client._request(drive.API)
            self.assertEqual(request.call_count, 2)
        self.assertEqual(self.credentials.access_token.call_args.kwargs['force_refresh'], True)
        with patch.object(drive, 'request_bytes', side_effect=GoogleDriveError('expired', status=401)) as request:
            with self.assertRaises(GoogleDriveError):
                self.client._request(drive.API)
            self.assertEqual(request.call_count, 2)

    def test_folder_create_has_no_delete_or_replace_operation(self):
        folder = dict(id='folder', name='PrépaPilot', mimeType=drive.FOLDER_MIME)
        with patch.object(self.client, '_json', return_value=folder) as request:
            self.client.create_folder('PrépaPilot', properties={'prepapilot': 'backup-v1'})
        self.assertEqual(request.call_args.kwargs['method'], 'POST')
        self.assertEqual(request.call_args.kwargs['payload']['appProperties'], {'prepapilot': 'backup-v1'})
        self.assertNotIn('parents', request.call_args.kwargs['payload'])

    def test_large_upload_chunks_resume_from_server_acknowledgement_and_verify(self):
        content = b'x' * (drive.CHUNK_SIZE + 47)
        source = self.root / 'fixture.bin'
        source.write_bytes(content)
        values = [
            (200, {'Location': self.session}, b''),
            GoogleDriveError('network interrupted'),
            (308, {'Range': 'bytes=0-524287'}, b''),
            reply(metadata(content=content), status=201),
        ]
        with patch.object(self.client, '_request', side_effect=values) as request:
            result = self.client.upload_file('folder', 'fixture.bin', source, properties={'sha256': hashlib.sha256(content).hexdigest()})
        self.assertEqual(result['size'], str(len(content)))
        calls = request.call_args_list
        self.assertEqual(calls[0].kwargs['method'], 'POST')
        self.assertEqual(calls[1].kwargs['headers']['Content-Range'], f'bytes 0-{drive.CHUNK_SIZE - 1}/{len(content)}')
        self.assertEqual(calls[2].kwargs['headers']['Content-Range'], f'bytes */{len(content)}')
        self.assertEqual(calls[3].kwargs['headers']['Content-Range'], f'bytes 524288-{len(content)-1}/{len(content)}')
        self.assertEqual(calls[3].kwargs['data'], content[524288:])

    def test_empty_upload_and_server_hash_failure(self):
        source = self.root / 'empty.bin'
        source.write_bytes(b'')
        with patch.object(self.client, '_request', side_effect=[(200, {'Location': self.session}, b''), reply(metadata(content=b''), 201)]) as request:
            self.client.upload_file('folder', 'empty.bin', source)
        self.assertEqual(request.call_args.kwargs['headers']['Content-Range'], 'bytes */0')
        source.write_bytes(b'abc')
        with patch.object(self.client, '_request', side_effect=[(200, {'Location': self.session}, b''), reply(metadata(content=b'bad'), 201)]):
            with self.assertRaisesRegex(GoogleDriveError, 'vérification'):
                self.client.upload_file('folder', 'fixture.bin', source)

    def test_upload_rejects_untrusted_session_and_impossible_resume_offset(self):
        source = self.root / 'fixture.bin'
        source.write_bytes(b'abc')
        for session in ['https://outside.invalid/upload', 'https://www.googleapis.com/another/api', 'http://www.googleapis.com/upload/drive/v3/files']:
            with patch.object(self.client, '_request', return_value=(200, {'Location': session}, b'')) as request:
                with self.assertRaises(GoogleDriveError):
                    self.client.upload_file('folder', 'fixture.bin', source)
                self.assertEqual(request.call_count, 1)
        with patch.object(self.client, '_request', side_effect=[(200, {'Location': self.session}, b''), (308, {'Range': 'bytes=0-300'}, b'')]):
            with self.assertRaises(GoogleDriveError):
                self.client.upload_file('folder', 'fixture.bin', source)

    def test_upload_stall_and_retry_are_bounded(self):
        source = self.root / 'fixture.bin'
        source.write_bytes(b'abc')
        with patch.object(self.client, '_request', side_effect=[(200, {'Location': self.session}, b'')] + [(308, {}, b'')] * 5) as request, \
             patch.object(self.client, '_pause'):
            with self.assertRaisesRegex(GoogleDriveError, 'progresse'):
                self.client.upload_file('folder', 'fixture.bin', source)
            self.assertEqual(request.call_count, 5)
        with patch.object(self.client, '_request', side_effect=GoogleDriveError('network')), patch.object(self.client, '_pause'):
            with self.assertRaises(GoogleDriveError):
                self.client._probe(self.session, 3)

    def test_download_verifies_before_replacing_target_and_removes_partial_file(self):
        target = self.root / 'download.bin'
        target.write_bytes(b'previous')
        with patch.object(self.client, 'get_file', return_value=metadata()), patch.object(drive, '_open', return_value=io.BytesIO(b'abc')):
            result = self.client.download_file('file123', target, 3)
        self.assertEqual(result['id'], 'file123')
        self.assertEqual(target.read_bytes(), b'abc')
        for bad in [b'ab', b'bad', b'abcdef']:
            target.write_bytes(b'previous')
            with patch.object(self.client, 'get_file', return_value=metadata()), patch.object(drive, '_open', return_value=io.BytesIO(bad)):
                with self.assertRaises(GoogleDriveError):
                    self.client.download_file('file123', target, 3)
            self.assertEqual(target.read_bytes(), b'previous')
            self.assertEqual(list(self.root.glob('*.part')), [])

    def test_download_rejects_oversized_file_before_network_and_missing_hash(self):
        with patch.object(self.client, 'get_file', return_value=metadata()), patch.object(drive, '_open') as request:
            with self.assertRaises(GoogleDriveError):
                self.client.download_file('file123', self.root / 'download.bin', 2)
            request.assert_not_called()
        item = metadata()
        del item['md5Checksum']
        with patch.object(self.client, 'get_file', return_value=item):
            with self.assertRaises(GoogleDriveError):
                self.client.download_file('file123', self.root / 'download.bin', 4)

    def test_download_cancel_preserves_target_and_discards_partial(self):
        cancel = threading.Event()
        self.client.cancel = cancel
        target = self.root / 'download.bin'
        target.write_bytes(b'previous')

        class CancelOnRead(io.BytesIO):
            def read(stream, size=-1):
                cancel.set()
                return super().read(size)

        with patch.object(self.client, 'get_file', return_value=metadata()), patch.object(drive, '_open', return_value=CancelOnRead(b'abc')):
            with self.assertRaises(GoogleCancelled):
                self.client.download_file('file123', target, 3)
        self.assertEqual(target.read_bytes(), b'previous')
        self.assertEqual(list(self.root.glob('*.part')), [])


if __name__ == '__main__':
    unittest.main()
