"""Small Drive v3 transport for immutable PrépaPilot backup objects.

All network operations are synchronous and belong in a worker. Mutations never
delete Drive content. Data is streamed in bounded chunks and verified by size/MD5.
"""
from __future__ import annotations
from .i18n import tr

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request

from .google_auth import (GoogleCancelled, GoogleDriveError, _network_error, _open,
                          _validate_google_url, check_cancel, decode_json, request_bytes)


API = 'https://www.googleapis.com/drive/v3/files'
UPLOAD_API = 'https://www.googleapis.com/upload/drive/v3/files'
FOLDER_MIME = 'application/vnd.google-apps.folder'
FIELDS = 'id,name,mimeType,size,md5Checksum,appProperties,parents,trashed,modifiedTime'
CHUNK_SIZE = 1024 * 1024
MAX_PAGES = 1000
MAX_FILES = 100000


def _file_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,256}', value):
        raise GoogleDriveError(tr('L’identifiant du dossier ou fichier Google Drive est invalide.'))
    return value


def _metadata(value):
    if not isinstance(value, dict):
        raise GoogleDriveError(tr('Les informations du fichier Google Drive sont invalides.'))
    _file_id(value.get('id'))
    if not isinstance(value.get('name'), str) or not isinstance(value.get('mimeType'), str):
        raise GoogleDriveError(tr('Les informations du fichier Google Drive sont incomplètes.'))
    return value


def _size(metadata):
    value = metadata.get('size')
    if isinstance(value, bool) or not isinstance(value, (str, int)) or not re.fullmatch(r'\d{1,20}', str(value)):
        raise GoogleDriveError(tr('La taille du fichier Google Drive est invalide.'))
    return int(value)


def _checksum(metadata):
    value = metadata.get('md5Checksum')
    if not isinstance(value, str) or not re.fullmatch(r'[a-fA-F0-9]{32}', value):
        raise GoogleDriveError(tr('Google Drive n’a pas fourni l’empreinte du fichier. Réessaie.'))
    return value.lower()


def _properties(properties):
    if properties is None:
        return {}
    if not isinstance(properties, dict) or len(properties) > 30 or any(
        not isinstance(key, str) or not isinstance(value, str) or len(key.encode('utf-8')) + len(value.encode('utf-8')) > 124
        for key, value in properties.items()
    ):
        raise GoogleDriveError(tr('Les propriétés de la sauvegarde sont invalides.'))
    return properties


def _name(value):
    if not isinstance(value, str) or not value or len(value) > 240 or any(ord(char) < 32 for char in value):
        raise GoogleDriveError(tr('Le nom du fichier de sauvegarde est invalide.'))
    return value


class DriveClient:
    def __init__(self, credentials, cancel=None):
        self.credentials = credentials
        self.cancel = cancel

    def _headers(self, extra=None, *, refresh=False):
        token = self.credentials.access_token(cancel=self.cancel, force_refresh=refresh)
        if not isinstance(token, str) or not token or any(ord(char) < 32 for char in token):
            raise GoogleDriveError(tr('La connexion Google est invalide. Reconnecte ton compte.'))
        return {'Authorization': 'Bearer ' + token, **(extra or {})}

    def _request(self, url, *, method='GET', data=None, headers=None, accepted=()):
        check_cancel(self.cancel)
        for refresh in (False, True):
            try:
                return request_bytes(url, method=method, data=data, headers=self._headers(headers, refresh=refresh),
                                     cancel=self.cancel, accepted=accepted)
            except GoogleDriveError as exc:
                if exc.status != 401 or refresh:
                    raise

    def _json(self, url, *, method='GET', payload=None):
        data = json.dumps(payload, ensure_ascii=True, separators=(',', ':')).encode('utf-8') if payload is not None else None
        _, _, body = self._request(url, method=method, data=data,
                                  headers={'Content-Type': 'application/json; charset=utf-8'} if data is not None else None)
        return decode_json(body)

    def _list(self, query):
        found = []
        seen_ids, seen_tokens = set(), set()
        token = None
        for _ in range(MAX_PAGES):
            check_cancel(self.cancel)
            params = dict(q=query, spaces='drive', pageSize=1000,
                          fields='nextPageToken,incompleteSearch,files(' + FIELDS + ')')
            if token:
                params['pageToken'] = token
            data = self._json(API + '?' + urlencode(params))
            files = data.get('files')
            if not isinstance(files, list) or data.get('incompleteSearch'):
                raise GoogleDriveError(tr('Google Drive n’a pas renvoyé la liste complète. Réessaie.'))
            for item in files:
                item = _metadata(item)
                if item['id'] not in seen_ids:
                    found.append(item)
                    seen_ids.add(item['id'])
            if len(found) > MAX_FILES:
                raise GoogleDriveError(tr('Ce dossier comporte trop de fichiers pour une seule sauvegarde.'))
            token = data.get('nextPageToken')
            if not token:
                return found
            if not isinstance(token, str) or len(token) > 8192 or token in seen_tokens:
                raise GoogleDriveError(tr('La pagination Google Drive est invalide. Réessaie.'))
            seen_tokens.add(token)
        raise GoogleDriveError(tr('La liste Google Drive est trop longue ; opération interrompue.'))

    def list_children(self, parent_id):
        return self._list("'" + _file_id(parent_id) + "' in parents and trashed = false")

    def list_backup_folders(self):
        return self._list("trashed = false and mimeType = '" + FOLDER_MIME + "' and "
                          "appProperties has { key='prepapilot' and value='backup-v1' }")

    def get_file(self, file_id):
        value = _metadata(self._json(API + '/' + _file_id(file_id) + '?' + urlencode({'fields': FIELDS})))
        if value.get('trashed'):
            raise GoogleDriveError(tr('Ce fichier Google Drive est dans la corbeille.'))
        return value

    def create_folder(self, name, parent_id=None, properties=None):
        payload = {'name': _name(name), 'mimeType': FOLDER_MIME, 'appProperties': _properties(properties)}
        if parent_id is not None:
            payload['parents'] = [_file_id(parent_id)]
        return _metadata(self._json(API + '?' + urlencode({'fields': FIELDS}), method='POST', payload=payload))

    def _pause(self, attempt):
        if self.cancel is not None:
            self.cancel.wait(min(.4 * 2 ** attempt, 3))
        else:
            time.sleep(min(.4 * 2 ** attempt, 3))
        check_cancel(self.cancel)

    def _upload_call(self, url, data, content_range):
        return self._request(url, method='PUT', data=data,
                             headers={'Content-Type': 'application/octet-stream', 'Content-Range': content_range,
                                      'Content-Length': str(len(data))}, accepted=(308,))

    def _probe(self, session, size):
        for attempt in range(4):
            try:
                return self._upload_call(session, b'', f'bytes */{size}')
            except GoogleDriveError as exc:
                if isinstance(exc, GoogleCancelled) or exc.status not in (None, 408, 429, 500, 502, 503, 504) or attempt == 3:
                    raise
                self._pause(attempt)

    @staticmethod
    def _resume_offset(headers, size):
        acknowledged = headers.get('Range')
        if not acknowledged:
            return 0
        match = re.fullmatch(r'bytes=0-(\d{1,20})', acknowledged)
        if not match or not 0 < int(match.group(1)) + 1 <= size:
            raise GoogleDriveError(tr('Google Drive a indiqué une reprise de transfert invalide.'))
        return int(match.group(1)) + 1

    def upload_file(self, parent_id, name, path, mime_type='application/octet-stream', properties=None):
        check_cancel(self.cancel)
        parent_id = _file_id(parent_id)
        name = _name(name)
        if not isinstance(mime_type, str) or len(mime_type) > 150 or not re.fullmatch(r'[a-zA-Z0-9.+_-]+/[a-zA-Z0-9.+_-]+', mime_type):
            raise GoogleDriveError(tr('Le type du fichier de sauvegarde est invalide.'))
        path = Path(path)
        try:
            stream = path.open('rb')
        except OSError:
            raise GoogleDriveError(tr('Le fichier à sauvegarder est inaccessible.')) from None
        with stream:
            initial = os.fstat(stream.fileno())
            size = initial.st_size
            digest = hashlib.md5()
            while True:
                check_cancel(self.cancel)
                block = stream.read(CHUNK_SIZE)
                if not block:
                    break
                digest.update(block)
            if stream.tell() != size:
                raise GoogleDriveError(tr('Le fichier a changé pendant sa préparation. Réessaie.'))
            payload = dict(name=name, mimeType=mime_type, parents=[parent_id], appProperties=_properties(properties))
            _, headers, _ = self._request(UPLOAD_API + '?' + urlencode({'uploadType': 'resumable', 'fields': FIELDS}),
                method='POST', data=json.dumps(payload).encode('utf-8'), headers={
                    'Content-Type': 'application/json; charset=utf-8', 'X-Upload-Content-Type': mime_type,
                    'X-Upload-Content-Length': str(size)})
            session = headers.get('Location', '')
            _validate_google_url(session)
            # The server may choose a new upload ID, never a new host or API path.
            parts = urlsplit(session)
            if parts.hostname != 'www.googleapis.com' or parts.path != '/upload/drive/v3/files':
                raise GoogleDriveError(tr('La session de transfert Google Drive est invalide.'))
            offset, stalled = 0, 0
            while True:
                check_cancel(self.cancel)
                stream.seek(offset)
                block = stream.read(min(CHUNK_SIZE, size - offset))
                if size and not block and offset < size:
                    raise GoogleDriveError(tr('Le fichier a changé pendant son transfert. Réessaie.'))
                range_value = f'bytes {offset}-{offset + len(block) - 1}/{size}' if block else f'bytes */{size}'
                try:
                    status, reply_headers, body = self._upload_call(session, block, range_value)
                except GoogleDriveError as exc:
                    if isinstance(exc, GoogleCancelled) or exc.status not in (None, 408, 429, 500, 502, 503, 504):
                        raise
                    status, reply_headers, body = self._probe(session, size)
                if status in (200, 201):
                    value = _metadata(decode_json(body))
                    if 'size' not in value or 'md5Checksum' not in value:
                        value = self.get_file(value['id'])
                    current = os.fstat(stream.fileno())
                    if current.st_size != initial.st_size or current.st_mtime_ns != initial.st_mtime_ns:
                        raise GoogleDriveError(tr('Le fichier a changé pendant son transfert. Réessaie.'))
                    if _size(value) != size or _checksum(value) != digest.hexdigest():
                        raise GoogleDriveError(tr('La vérification du fichier envoyé a échoué. La sauvegarde reste incomplète ; réessaie.'))
                    return value
                if status != 308:
                    raise GoogleDriveError(tr('Google Drive n’a pas confirmé le transfert.'))
                next_offset = self._resume_offset(reply_headers, size)
                if next_offset > offset + len(block):
                    raise GoogleDriveError(tr('Google Drive a confirmé des données qui n’ont pas été envoyées.'))
                stalled = stalled + 1 if next_offset <= offset else 0
                if stalled > 3:
                    raise GoogleDriveError(tr('Le transfert Google Drive ne progresse plus. Réessaie.'))
                if stalled:
                    self._pause(stalled - 1)
                offset = next_offset

    def download_file(self, file_id, target, max_bytes):
        """Verify before atomic replacement; partial files never escape to caller."""
        check_cancel(self.cancel)
        if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 0:
            raise GoogleDriveError(tr('La limite de téléchargement est invalide.'))
        metadata = self.get_file(file_id)
        size = _size(metadata)
        expected_hash = _checksum(metadata)
        if size > max_bytes:
            raise GoogleDriveError(tr('Ce fichier dépasse la taille autorisée pour la restauration.'))
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.' + target.name + '-', suffix='.part', dir=target.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                url = API + '/' + _file_id(file_id) + '?alt=media'
                response = None
                for refresh in (False, True):
                    try:
                        response = _open(Request(url, headers=self._headers(refresh=refresh)), cancel=self.cancel)
                        break
                    except HTTPError as exc:
                        exc.close()
                        if exc.code != 401 or refresh:
                            raise _network_error(exc) from None
                with response:
                    count, digest = 0, hashlib.md5()
                    while True:
                        check_cancel(self.cancel)
                        block = response.read(min(CHUNK_SIZE, size - count + 1))
                        if not block:
                            break
                        count += len(block)
                        if count > size or count > max_bytes:
                            raise GoogleDriveError(tr('Le téléchargement dépasse la taille annoncée. Restauration interrompue.'))
                        digest.update(block)
                        stream.write(block)
                    if count != size or digest.hexdigest() != expected_hash:
                        raise GoogleDriveError(tr('Le fichier téléchargé est incomplet ou endommagé. Réessaie.'))
                stream.flush()
                os.fsync(stream.fileno())
            check_cancel(self.cancel)
            os.replace(temporary, target)
            return metadata
        except GoogleDriveError:
            raise
        except (HTTPError, URLError, OSError) as exc:
            raise _network_error(exc) from None
        finally:
            Path(temporary).unlink(missing_ok=True)
