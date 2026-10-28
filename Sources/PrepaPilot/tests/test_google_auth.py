"""Google authorization tests use only disposable local fixtures, never Google."""
import base64
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit

from mpsi_desktop import google_auth as auth


CLIENT_ID = '123456789-test.apps.googleusercontent.com'


class GoogleAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='prepapilot-google-auth-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.connection = auth.GoogleConnection(self.root / 'data')

    def config(self, **extras):
        path = self.root / 'desktop.json'
        path.write_text(json.dumps({'installed': {'client_id': CLIENT_ID, 'client_secret': 'fixture-only', **extras}}))
        return path

    def tokens(self):
        return dict(client_id=CLIENT_ID, access_token='fixture-access', refresh_token='fixture-refresh', expires_at=time.time() + 3600)

    def save_tokens_fixture(self, value=None):
        self.connection.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection.token_path.write_bytes(json.dumps(value or self.tokens()).encode())

    def test_configuration_keeps_only_desktop_identity_not_imported_endpoints(self):
        self.connection.configure(self.config(token_uri='https://outside.invalid/steal', auth_uri='https://outside.invalid/steal'))
        saved = json.loads(self.connection.config_path.read_text())
        self.assertEqual(set(saved['installed']), {'client_id', 'client_secret'})
        self.assertTrue(self.connection.configured)
        self.assertFalse(self.connection.connected)
        self.assertEqual(self.connection.cloud_dir, self.root / 'data' / 'cloud')

    def packaged_client(self):
        assets = self.root / 'packaged-app' / 'assets'
        assets.mkdir(parents=True)
        path = assets / 'google-oauth-client.json'
        path.write_bytes(self.config().read_bytes())
        return assets.parent

    def test_shared_packaged_client_needs_no_setup_or_shared_account_on_fresh_pcs(self):
        package = self.packaged_client()
        other = auth.GoogleConnection(self.root / 'second-pc' / 'data')
        with patch.object(auth.sys, '_MEIPASS', str(package), create=True), \
             patch.object(auth, '_form') as network:
            for connection in (self.connection, other):
                self.assertTrue(connection.configured)
                self.assertFalse(connection.connected)
                self.assertEqual(connection._configuration()['client_id'], CLIENT_ID)
                self.assertFalse(connection.cloud_dir.exists())
            network.assert_not_called()

    def test_shared_client_authorization_stays_in_each_users_own_local_storage(self):
        package = self.packaged_client()
        other = auth.GoogleConnection(self.root / 'second-pc' / 'data')
        response = dict(access_token='fixture-new', refresh_token='fixture-refresh', expires_in=3600)
        with patch.object(auth.sys, '_MEIPASS', str(package), create=True), \
             patch.object(auth, '_authorize', return_value=('fixture-code', 'http://127.0.0.1:12345/', 'fixture-verifier')), \
             patch.object(auth, '_form', return_value=response), \
             patch.object(auth, '_protect', side_effect=lambda raw, **kwargs: raw):
            self.connection.connect()
            self.assertTrue(self.connection.connected)
            self.assertFalse(other.connected)
            self.assertFalse(self.connection.config_path.exists())
            self.assertFalse(other.cloud_dir.exists())
        self.assertEqual(set((package / 'assets').iterdir()), {package / 'assets' / 'google-oauth-client.json'})

    def test_local_advanced_client_keeps_priority_over_shared_packaged_client(self):
        package = self.packaged_client()
        local_id = '987654321-personal.apps.googleusercontent.com'
        with patch.object(auth.sys, '_MEIPASS', str(package), create=True):
            local = self.root / 'personal.json'
            local.write_text(json.dumps({'installed': {'client_id': local_id}}))
            self.connection.configure(local)
            self.assertEqual(self.connection._configuration()['client_id'], local_id)
            self.assertEqual(json.loads((package / 'assets' / 'google-oauth-client.json').read_text())['installed']['client_id'], CLIENT_ID)

    def test_missing_packaged_client_explains_that_publisher_provides_connection(self):
        with patch.object(auth.sys, '_MEIPASS', str(self.root / 'unconfigured-app'), create=True):
            self.assertFalse(self.connection.configured)
            with self.assertRaisesRegex(auth.GoogleDriveError, 'éditeur'):
                self.connection._configuration()

    def test_bad_or_oversize_config_cannot_replace_current_config_or_tokens(self):
        self.connection.configure(self.config())
        self.save_tokens_fixture()
        previous = self.connection.config_path.read_bytes()
        for content in ['{"web":{}}', '{"installed":{"client_id":"bad"}}', ' ' * 65537]:
            path = self.root / 'invalid.json'
            path.write_text(content)
            with self.assertRaises(auth.GoogleDriveError):
                self.connection.configure(path)
            self.assertEqual(self.connection.config_path.read_bytes(), previous)
            self.assertTrue(self.connection.token_path.exists())

    def test_configuration_change_unlinks_only_local_credentials(self):
        self.connection.configure(self.config())
        self.save_tokens_fixture()
        self.connection.configure(self.config())
        self.assertTrue(self.connection.token_path.exists())
        alternate = self.root / 'alternate.json'
        alternate.write_text(json.dumps({'installed': {'client_id': '987654321-other.apps.googleusercontent.com'}}))
        self.connection.configure(alternate)
        self.assertFalse(self.connection.token_path.exists())

    @unittest.skipUnless(os.name == 'nt', 'Windows DPAPI')
    def test_dpapi_roundtrip_and_corruption_never_fall_back_to_plaintext(self):
        plain = b'local-fixture-not-a-real-token'
        encrypted = auth._protect(plain)
        self.assertNotIn(plain, encrypted)
        self.assertEqual(auth._protect(encrypted, decrypt=True), plain)
        with self.assertRaises(auth.GoogleDriveError):
            auth._protect(b'invalid-protected-blob', decrypt=True)

    def test_corrupt_or_foreign_local_tokens_are_disconnected_without_network(self):
        self.connection.configure(self.config())
        with patch.object(auth, '_form') as network, patch.object(auth, '_protect', side_effect=lambda raw, **kwargs: raw):
            self.save_tokens_fixture({**self.tokens(), 'client_id': 'different'})
            self.assertFalse(self.connection.connected)
            self.save_tokens_fixture({**self.tokens(), 'expires_at': float('nan')})
            self.assertFalse(self.connection.connected)
            self.connection.token_path.write_bytes(b'not json')
            self.assertFalse(self.connection.connected)
            network.assert_not_called()

    def test_refresh_preserves_refresh_token_and_persists_atomically(self):
        self.connection.configure(self.config())
        self.save_tokens_fixture({**self.tokens(), 'expires_at': time.time() - 1})
        with patch.object(auth, '_protect', side_effect=lambda raw, **kwargs: raw), patch.object(auth, '_form', return_value={
            'access_token': 'fixture-renewed', 'expires_in': 3600, 'token_type': 'Bearer', 'scope': auth.DRIVE_SCOPE,
        }) as form:
            self.assertEqual(self.connection.access_token(), 'fixture-renewed')
            self.assertEqual(self.connection.access_token(), 'fixture-renewed')
            self.assertTrue(self.connection.connected)
            self.assertEqual(form.call_count, 1)
            self.assertEqual(form.call_args.args[0], auth.TOKEN_URL)
            self.assertEqual(form.call_args.args[1]['grant_type'], 'refresh_token')
            saved = json.loads(self.connection.token_path.read_bytes())
            self.assertEqual(saved['refresh_token'], 'fixture-refresh')
            self.assertEqual(list(self.connection.cloud_dir.glob('.*')), [])

    def test_failed_connection_preserves_previous_credentials_and_scope_rejection(self):
        self.connection.configure(self.config())
        self.save_tokens_fixture()
        previous = self.connection.token_path.read_bytes()
        with patch.object(auth, '_authorize', return_value=('fixture-code', 'http://127.0.0.1:12345/', 'fixture-verifier')), \
             patch.object(auth, '_form', return_value={'access_token': 'unused', 'expires_in': 3600, 'scope': 'other'}):
            with self.assertRaises(auth.GoogleDriveError):
                self.connection.connect()
        self.assertEqual(self.connection.token_path.read_bytes(), previous)

    def test_connect_sends_code_verifier_and_fixed_token_endpoint(self):
        self.connection.configure(self.config(token_uri='https://outside.invalid'))
        response = dict(access_token='fixture-new', refresh_token='fixture-refresh', expires_in=3600)
        with patch.object(auth, '_authorize', return_value=('fixture-code', 'http://127.0.0.1:12345/', 'fixture-verifier')), \
             patch.object(auth, '_form', return_value=response) as form, \
             patch.object(auth, '_protect', side_effect=lambda raw, **kwargs: raw):
            self.connection.connect()
            self.assertTrue(self.connection.connected)
        self.assertEqual(form.call_args.args[0], auth.TOKEN_URL)
        self.assertEqual(form.call_args.args[1]['code_verifier'], 'fixture-verifier')
        self.assertEqual(form.call_args.args[1]['grant_type'], 'authorization_code')

    def test_disconnect_only_forgets_this_pc_without_revoking_other_computers(self):
        self.connection.configure(self.config())
        self.save_tokens_fixture()
        with patch.object(auth, '_protect', side_effect=lambda raw, **kwargs: raw), \
             patch.object(auth, '_form', side_effect=auth.GoogleDriveError('offline')) as form:
            self.connection.disconnect()
            form.assert_not_called()
        self.assertFalse(self.connection.token_path.exists())
        self.assertTrue(self.connection.config_path.exists())

    def test_network_rejects_non_google_https_and_redirects_without_forwarding_tokens(self):
        for url in ['http://www.googleapis.com/drive/v3/files', 'https://outside.invalid',
                    'https://www.googleapis.com.outside.invalid', 'https://user@www.googleapis.com',
                    'https://www.googleapis.com:444/drive/v3/files']:
            with self.assertRaises(auth.GoogleDriveError):
                auth._validate_google_url(url)
        self.assertIsNone(auth._NoRedirect().redirect_request(None, None, 302, None, None, 'https://outside.invalid'))
        with patch.object(auth, '_open', side_effect=HTTPError('https://www.googleapis.com', 403, 'private-token', {}, io.BytesIO(b'private-token'))):
            with self.assertRaises(auth.GoogleDriveError) as caught:
                auth.request_bytes('https://www.googleapis.com/drive/v3/files')
        self.assertNotIn('private-token', str(caught.exception))
        self.assertEqual(caught.exception.status, 403)

    def test_loopback_pkce_state_validation_and_listener_cleanup(self):
        opened, replies, threads = [], [], []

        def open_browser(url, **kwargs):
            opened.append(parse_qs(urlsplit(url).query))
            query = opened[0]
            redirect = urlsplit(query['redirect_uri'][0])

            def callbacks():
                for state in ['wrong-state', query['state'][0]]:
                    connection = http.client.HTTPConnection(redirect.hostname, redirect.port, timeout=5)
                    connection.request('GET', '/?' + urlencode({'state': state, 'code': 'fixture-code'}))
                    reply = connection.getresponse()
                    replies.append(reply.status)
                    self.assertNotIn(b'fixture-code', reply.read())
                    connection.close()
            thread = threading.Thread(target=callbacks, daemon=True)
            threads.append(thread)
            thread.start()
            return True

        with patch.object(auth.webbrowser, 'open', side_effect=open_browser):
            code, redirect, verifier = auth._authorize(CLIENT_ID, timeout=5)
        for thread in threads:
            thread.join(5)
        self.assertEqual(replies, [400, 200])
        self.assertEqual(code, 'fixture-code')
        params = opened[0]
        expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
        self.assertEqual(params['code_challenge'], [expected])
        self.assertEqual(params['code_challenge_method'], ['S256'])
        self.assertEqual(params['scope'], [auth.DRIVE_SCOPE])
        self.assertGreaterEqual(len(verifier), 43)
        self.assertLessEqual(len(verifier), 128)
        parts = urlsplit(redirect)
        with socket.socket() as probe:
            probe.settimeout(.5)
            self.assertNotEqual(probe.connect_ex((parts.hostname, parts.port)), 0)

    def test_auth_cancel_and_timeout_do_not_leave_listener_alive(self):
        cancel = threading.Event()
        cancel.set()
        with patch.object(auth.webbrowser, 'open') as browser:
            with self.assertRaises(auth.GoogleCancelled):
                auth._authorize(CLIENT_ID, cancel)
            browser.assert_not_called()
        with patch.object(auth.webbrowser, 'open', return_value=True):
            with self.assertRaisesRegex(auth.GoogleDriveError, 'expiré'):
                auth._authorize(CLIENT_ID, timeout=.02)


if __name__ == '__main__':
    unittest.main()
