"""Desktop Google OAuth: browser + PKCE, with Windows-bound local credentials.

Only drive.file is requested. No credentials are kept in the application database,
and no OAuth response, URL or token is ever logged by this module.
"""
from __future__ import annotations
from .i18n import tr, language

import base64
import ctypes
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import math
import os
from pathlib import Path
import re
import secrets
import socket
import ssl
import sys
import tempfile
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener
import webbrowser


DRIVE_SCOPE = 'https://www.googleapis.com/auth/drive.file'
AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URL = 'https://oauth2.googleapis.com/token'
REVOKE_URL = 'https://oauth2.googleapis.com/revoke'
NETWORK_TIMEOUT = 20
MAX_JSON = 2 * 1024 * 1024


class GoogleDriveError(ValueError):
    """A deliberately sanitized error suitable for the application's dialog."""

    def __init__(self, message: str, *, status: int | None = None):
        super().__init__(message)
        self.status = status


class GoogleCancelled(GoogleDriveError):
    def __init__(self):
        super().__init__(tr('Opération Google Drive annulée.'))


def check_cancel(cancel=None):
    if cancel is not None and cancel.is_set():
        raise GoogleCancelled()


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Even a valid server response must not forward an Authorization header.
        return None


def _opener():
    return build_opener(_NoRedirect(), HTTPSHandler(context=ssl.create_default_context()))


def _validate_google_url(url: str):
    try:
        parts = urlsplit(url)
        valid = (parts.scheme == 'https' and parts.hostname in
                 {'www.googleapis.com', 'oauth2.googleapis.com'} and
                 parts.port in (None, 443) and not parts.username and
                 not parts.password and not parts.fragment)
    except (ValueError, TypeError):
        valid = False
    if not valid:
        raise GoogleDriveError(tr('Adresse Google non autorisée ; transfert interrompu.'))


def _open(request: Request, *, cancel=None):
    check_cancel(cancel)
    _validate_google_url(request.full_url)
    return _opener().open(request, timeout=NETWORK_TIMEOUT)


def _network_error(exc):
    if isinstance(exc, HTTPError):
        code = exc.code
        messages = {
            400: tr('Google a refusé la demande. Vérifie la configuration ou reconnecte ton compte.'),
            401: tr('La connexion Google a expiré. Reconnecte ton compte.'),
            403: tr('Google refuse cet accès. Vérifie les autorisations et l’activation de l’API Drive.'),
            404: tr('Ce fichier ou dossier Google Drive est introuvable ou inaccessible à cette application.'),
            429: tr('Google Drive est temporairement sollicité. Réessaie dans quelques instants.'),
        }
        return GoogleDriveError(messages.get(code, tr('Google Drive est momentanément indisponible. Réessaie.')), status=code)
    return GoogleDriveError(tr('Connexion à Google impossible. Vérifie Internet et réessaie.'))


def request_bytes(url, *, method='GET', data=None, headers=None, cancel=None, accepted=()):
    """Bounded HTTPS response; no retries on a potentially mutating request."""
    check_cancel(cancel)
    request = Request(url, data=data, headers=headers or {}, method=method)
    try:
        try:
            response = _open(request, cancel=cancel)
        except HTTPError as exc:
            if exc.code not in accepted:
                raise
            response = exc
        with response:
            body = response.read(MAX_JSON + 1)
            if len(body) > MAX_JSON:
                raise GoogleDriveError(tr('La réponse Google est trop volumineuse.'))
            status = response.status if hasattr(response, 'status') else response.code
            result = status, response.headers, body
        check_cancel(cancel)
        return result
    except GoogleDriveError:
        raise
    except (HTTPError, URLError, OSError) as exc:
        if isinstance(exc, HTTPError):
            exc.close()
        raise _network_error(exc) from None


def decode_json(body):
    try:
        value = json.loads(body)
    except (ValueError, UnicodeError, RecursionError):
        raise GoogleDriveError(tr('Réponse Google illisible ; réessaie plus tard.')) from None
    if not isinstance(value, dict):
        raise GoogleDriveError(tr('Réponse Google inattendue ; réessaie plus tard.'))
    return value


def _form(url, fields, cancel=None):
    _, _, body = request_bytes(url, method='POST', data=urlencode(fields).encode('ascii'),
                              headers={'Content-Type': 'application/x-www-form-urlencoded'}, cancel=cancel)
    return decode_json(body) if body else {}


def _read_json_file(path: Path, limit=64 * 1024):
    try:
        with path.open('rb') as stream:
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise ValueError()
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except (OSError, ValueError, UnicodeError, RecursionError):
        raise GoogleDriveError(tr('Le fichier de configuration Google est illisible ou invalide.')) from None


def _client_config(value):
    installed = value.get('installed')
    if not isinstance(installed, dict):
        raise GoogleDriveError(tr('Choisis un fichier OAuth Google de type « Application de bureau ».'))
    client_id = installed.get('client_id')
    if not isinstance(client_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{6,220}\.apps\.googleusercontent\.com', client_id):
        raise GoogleDriveError(tr('L’identifiant du client Google est invalide.'))
    secret = installed.get('client_secret', '')
    if not isinstance(secret, str) or len(secret) > 512 or any(ord(char) < 32 for char in secret):
        raise GoogleDriveError(tr('La configuration du client Google est invalide.'))
    # Never trust configurable auth/token/redirect URIs from an imported file.
    return {'client_id': client_id, 'client_secret': secret}


def _atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _protect(data: bytes, *, decrypt=False) -> bytes:
    """DPAPI current-user protection. Never falls back to plaintext storage."""
    if os.name != 'nt':
        raise GoogleDriveError(tr('La connexion sécurisée Google est disponible dans la version Windows.'))

    class Blob(ctypes.Structure):
        _fields_ = [('size', ctypes.c_ulong), ('data', ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(data)
    incoming = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    outgoing = Blob()
    crypt32 = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    if decrypt:
        operation = crypt32.CryptUnprotectData
        operation.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob),
                              ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(Blob)]
        second = None
    else:
        operation = crypt32.CryptProtectData
        operation.argtypes = [ctypes.POINTER(Blob), ctypes.c_wchar_p, ctypes.POINTER(Blob),
                              ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(Blob)]
        second = 'PrépaPilot Google Drive'
    operation.restype = ctypes.c_int
    if not operation(ctypes.byref(incoming), second, None, None, None, 1, ctypes.byref(outgoing)):
        raise GoogleDriveError(tr('La connexion Google enregistrée ne peut pas être ouverte sur cette session Windows. Reconnecte ton compte.'))
    try:
        return ctypes.string_at(outgoing.data, outgoing.size)
    finally:
        if outgoing.data:
            ctypes.memset(outgoing.data, 0, outgoing.size)
            kernel32.LocalFree(outgoing.data)


def _valid_tokens(value, client_id):
    if not isinstance(value, dict) or value.get('client_id') != client_id:
        return False
    expiry = value.get('expires_at')
    try:
        valid_expiry = type(expiry) in (float, int) and math.isfinite(expiry)
    except OverflowError:
        valid_expiry = False
    return (isinstance(value.get('refresh_token'), str) and 0 < len(value['refresh_token']) < 16384 and
            isinstance(value.get('access_token'), str) and 0 < len(value['access_token']) < 16384 and
            valid_expiry)


class GoogleConnection:
    """UI operations are local except connect/disconnect/access_token/client use."""

    def __init__(self, data_dir):
        self.cloud_dir = Path(data_dir) / 'cloud'
        self.config_path = self.cloud_dir / 'client.json'
        self.token_path = self.cloud_dir / 'credentials.bin'
        self._lock = threading.RLock()

    def _configuration(self):
        path = self.config_path
        if not path.exists():
            path = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent)) / 'assets' / 'google-oauth-client.json'
        if not path.exists():
            raise GoogleDriveError(tr('La connexion Google n’est pas incluse dans cette version de PrépaPilot. Demande une version configurée à son éditeur.'))
        return _client_config(_read_json_file(path))

    @property
    def configured(self):
        try:
            self._configuration()
            return True
        except GoogleDriveError:
            return False

    def _load_tokens(self, config):
        if not self.token_path.exists():
            return None
        try:
            with self.token_path.open('rb') as stream:
                raw = stream.read(65537)
            if len(raw) > 65536:
                return None
            tokens = json.loads(_protect(raw, decrypt=True))
        except (OSError, ValueError, UnicodeError, RecursionError):
            return None
        return tokens if _valid_tokens(tokens, config['client_id']) else None

    @property
    def connected(self):
        # Atomic file replacement makes this a safe local snapshot. Do not wait
        # for the worker's lock while the browser consent page is open.
        try:
            return self._load_tokens(self._configuration()) is not None
        except GoogleDriveError:
            return False

    def configure(self, path):
        config = _client_config(_read_json_file(Path(path)))
        with self._lock:
            try:
                changed = self._configuration()['client_id'] != config['client_id']
            except GoogleDriveError:
                changed = True
            _atomic_write(self.config_path, json.dumps({'installed': config}, ensure_ascii=True).encode('utf-8'))
            if changed:
                self.token_path.unlink(missing_ok=True)

    def _save_tokens(self, response, config, previous=None):
        scope = response.get('scope', DRIVE_SCOPE)
        if not isinstance(scope, str) or DRIVE_SCOPE not in scope.split():
            raise GoogleDriveError(tr('L’autorisation Google Drive n’a pas été accordée.'))
        try:
            expires = float(response['expires_in'])
            if not math.isfinite(expires) or not 0 < expires <= 86400:
                raise ValueError()
            tokens = dict(client_id=config['client_id'], access_token=response['access_token'],
                          refresh_token=response.get('refresh_token') or (previous or {}).get('refresh_token'),
                          expires_at=time.time() + expires)
        except (KeyError, ValueError, TypeError, OverflowError):
            raise GoogleDriveError(tr('La réponse de connexion Google est incomplète.')) from None
        token_type = response.get('token_type', 'Bearer')
        if not _valid_tokens(tokens, config['client_id']) or not isinstance(token_type, str) or token_type.lower() != 'bearer':
            raise GoogleDriveError(tr('La connexion Google n’a pas fourni de jeton renouvelable. Reconnecte ton compte.'))
        encrypted = _protect(json.dumps(tokens).encode('utf-8'))
        _atomic_write(self.token_path, encrypted)
        return tokens

    def connect(self, cancel=None):
        check_cancel(cancel)
        with self._lock:
            config = self._configuration()
            code, redirect, verifier = _authorize(config['client_id'], cancel)
            fields = dict(client_id=config['client_id'], code=code, redirect_uri=redirect,
                          code_verifier=verifier, grant_type='authorization_code')
            if config['client_secret']:
                fields['client_secret'] = config['client_secret']
            response = _form(TOKEN_URL, fields, cancel)
            check_cancel(cancel)
            self._save_tokens(response, config)

    def access_token(self, cancel=None, *, force_refresh=False):
        check_cancel(cancel)
        with self._lock:
            config = self._configuration()
            tokens = self._load_tokens(config)
            if not tokens:
                raise GoogleDriveError(tr('Connecte ton compte Google pour continuer.'))
            if not force_refresh and tokens['expires_at'] > time.time() + 60:
                return tokens['access_token']
            fields = dict(client_id=config['client_id'], refresh_token=tokens['refresh_token'], grant_type='refresh_token')
            if config['client_secret']:
                fields['client_secret'] = config['client_secret']
            response = _form(TOKEN_URL, fields, cancel)
            tokens = self._save_tokens(response, config, tokens)
            return tokens['access_token']

    def disconnect(self):
        """Disconnect this PC only. Revocation would also affect the other PCs."""
        with self._lock:
            self.token_path.unlink(missing_ok=True)

    def client(self, cancel=None):
        from .google_drive import DriveClient
        return DriveClient(self, cancel=cancel)


def _authorize(client_id, cancel=None, *, timeout=180):
    """Receive one verified loopback response, with a cancelable finite lifetime."""
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode('ascii')).digest()).rstrip(b'=').decode('ascii')
    result = {}

    class Callback(BaseHTTPRequestHandler):
        def setup(self):
            self.request.settimeout(2)
            super().setup()

        def log_message(self, *_args):
            pass  # BaseHTTPRequestHandler would otherwise log the code and state.

        def do_GET(self):
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query, max_num_fields=12)
            received = query.get('state', [''])
            valid = (parsed.path == '/' and len(received) == 1 and
                     secrets.compare_digest(received[0], state) and
                     self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}')
            if not valid:
                self.send_response(400)
                message = tr('Cette réponse de connexion est invalide. Reviens dans PrépaPilot.')
            else:
                if query.get('error'):
                    result['error'] = True
                elif len(query.get('code', [])) == 1 and 0 < len(query['code'][0]) < 8192:
                    result['code'] = query['code'][0]
                else:
                    result['error'] = True
                self.send_response(200)
                message = tr('Tu peux fermer cet onglet et revenir dans PrépaPilot.')
            body = (f'<!doctype html><html lang="{language()}"><meta charset="utf-8"><title>PrépaPilot</title>'
                    '<body style="font:18px system-ui;padding:48px;color:#20243a;background:#f4f6ff">'
                    '<h1>PrépaPilot</h1><p>' + message + '</p></body></html>').encode('utf-8')
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'")
            self.end_headers()
            try:
                self.wfile.write(body)
            except OSError:
                pass

    class QuietServer(HTTPServer):
        allow_reuse_address = False

        def server_bind(self):
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            super().server_bind()

        def handle_error(self, *_args):
            pass  # Malformed local requests must not leak the callback in logs.

    try:
        server = QuietServer(('127.0.0.1', 0), Callback)
    except OSError:
        raise GoogleDriveError(tr('Impossible d’ouvrir la connexion locale sécurisée. Réessaie.')) from None
    with server:
        server.timeout = .2
        redirect = f'http://127.0.0.1:{server.server_port}/'
        url = AUTH_URL + '?' + urlencode(dict(client_id=client_id, redirect_uri=redirect,
              response_type='code', scope=DRIVE_SCOPE, state=state, code_challenge=challenge,
              code_challenge_method='S256', access_type='offline', prompt='consent select_account'))
        check_cancel(cancel)
        if not webbrowser.open(url, new=1, autoraise=True):
            raise GoogleDriveError(tr('Le navigateur ne s’est pas ouvert. Vérifie ton navigateur par défaut et réessaie.'))
        deadline = time.monotonic() + timeout
        while not result:
            check_cancel(cancel)
            if time.monotonic() >= deadline:
                raise GoogleDriveError(tr('La connexion Google a expiré. Réessaie lorsque tu es prêt à choisir ton compte.'))
            server.handle_request()
        check_cancel(cancel)
        if 'code' not in result:
            raise GoogleDriveError(tr('La connexion Google a été refusée ou annulée.'))
        return result['code'], redirect, verifier
