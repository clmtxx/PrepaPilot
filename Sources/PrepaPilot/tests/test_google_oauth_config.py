"""Shared release identities are desktop clients, never user connections."""
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from mpsi_desktop.google_oauth_config import (GOOGLE_OAUTH_ASSET, MAX_CLIENT_BYTES,
    normalize_google_oauth_client, read_google_oauth_client, select_google_oauth_client,
    write_google_oauth_client)


CLIENT = {'installed': {'client_id': '123456789-publisher.apps.googleusercontent.com', 'client_secret': 'fixture-desktop-secret'}}


class GoogleOAuthConfigTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def client_file(self, value=CLIENT, name='desktop-client.json'):
        path = self.root / name
        path.write_text(json.dumps(value), encoding='utf-8')
        return path

    def test_official_download_is_normalized_to_only_the_desktop_identity(self):
        official = {'installed': {**CLIENT['installed'], 'project_id': 'publisher-project',
            'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
            'token_uri': 'https://oauth2.googleapis.com/token',
            'auth_provider_x509_cert_url': 'https://www.googleapis.com/oauth2/v1/certs',
            'redirect_uris': ['http://localhost']}}
        path = self.client_file(official)
        before = path.read_bytes()
        config = read_google_oauth_client(path)
        self.assertEqual(config, CLIENT)
        write_google_oauth_client(self.root / 'assets', config)
        self.assertEqual(json.loads((self.root / 'assets' / GOOGLE_OAUTH_ASSET).read_text()), CLIENT)
        self.assertEqual(path.read_bytes(), before)

    def test_tokens_account_service_account_and_web_clients_are_rejected(self):
        for value in ({'web': CLIENT['installed']}, {'type': 'service_account', 'private_key': 'fixture'},
                      {'refresh_token': 'fixture'}, {'installed': CLIENT['installed'], 'token': 'fixture'},
                      {'installed': CLIENT['installed'], 'account': 'fixture'},
                      *({'installed': {**CLIENT['installed'], key: 'fixture'}} for key in
                        ('access_token', 'refresh_token', 'id_token', 'token', 'account', 'client_email', 'private_key'))):
            with self.subTest(keys=list(value)), self.assertRaises(ValueError):
                normalize_google_oauth_client(value)

    def test_malformed_oversize_duplicate_nonfinite_and_invalid_identity_rejected(self):
        path = self.root / 'invalid.json'
        for raw in ('[]', 'not json', '{"installed":{},"installed":{}}', '{"installed":{"client_id":NaN}}',
                    '{"installed":{"client_id":Infinity}}', ' ' * (MAX_CLIENT_BYTES + 1)):
            path.write_text(raw, encoding='utf-8')
            with self.subTest(raw=raw[:60]), self.assertRaises(ValueError) as error:
                read_google_oauth_client(path)
            self.assertTrue(str(error.exception))
        for client_id in ('', None, 'https://outside.invalid/client', 'a.apps.googleusercontent.com', 'bad\n.apps.googleusercontent.com'):
            with self.subTest(client_id=client_id), self.assertRaises(ValueError):
                normalize_google_oauth_client({'installed': {'client_id': client_id}})
        for secret in (123, None, 'a' * 513, 'a\nb'):
            with self.subTest(secret=secret), self.assertRaises(ValueError):
                normalize_google_oauth_client({'installed': {**CLIENT['installed'], 'client_secret': secret}})

    def test_optional_dev_client_require_flag_and_explicit_override(self):
        assets = self.root / 'assets'
        assets.mkdir()
        self.assertIsNone(select_google_oauth_client(assets))
        with self.assertRaisesRegex(ValueError, '--google-oauth-client'):
            select_google_oauth_client(assets, required=True)
        source = self.client_file()
        self.assertEqual(select_google_oauth_client(assets, source, required=True), CLIENT)
        (assets / GOOGLE_OAUTH_ASSET).write_text('{"token":"fixture"}', encoding='utf-8')
        with self.assertRaises(ValueError):
            select_google_oauth_client(assets)
        self.assertEqual(select_google_oauth_client(assets, source), CLIENT)
        with self.assertRaises(ValueError):
            select_google_oauth_client(assets, self.root / 'missing.json')

    def test_no_user_cloud_directory_is_ever_used_as_a_fallback(self):
        assets = self.root / 'assets'
        personal = self.root / 'data' / 'cloud'
        personal.mkdir(parents=True)
        (personal / 'client.json').write_text(json.dumps(CLIENT), encoding='utf-8')
        (personal / 'credentials.bin').write_bytes(b'PRIVATE_USER_TOKEN')
        self.assertIsNone(select_google_oauth_client(assets))
        with self.assertRaises(ValueError):
            select_google_oauth_client(assets, required=True)

    def test_windows_junction_in_client_parent_is_rejected(self):
        folder = self.root / 'linked-parent'
        folder.mkdir()
        path = folder / 'client.json'
        path.write_text(json.dumps(CLIENT), encoding='utf-8')
        original = Path.lstat
        def reparse_parent(candidate, *args, **kwargs):
            info = original(candidate, *args, **kwargs)
            if candidate == folder:
                class Reparse:
                    st_mode = info.st_mode
                    st_file_attributes = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)
                return Reparse()
            return info
        with patch.object(Path, 'lstat', reparse_parent), self.assertRaisesRegex(ValueError, 'jonction'):
            read_google_oauth_client(path)


if __name__ == '__main__':
    unittest.main()
