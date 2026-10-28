"""Standard-library validation for the publisher's shared desktop OAuth client.

This module does not import Qt, contact Google or load account credentials.
Only the desktop application identity is allowed into a distribution.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat


GOOGLE_OAUTH_ASSET = 'google-oauth-client.json'
MAX_CLIENT_BYTES = 64 * 1024
_DESKTOP_FIELDS = frozenset({'client_id', 'client_secret', 'project_id', 'auth_uri',
                            'token_uri', 'auth_provider_x509_cert_url', 'redirect_uris'})


def _plain_path(path):
    path = Path(os.path.abspath(Path(path).expanduser()))
    for candidate in (path, *path.parents):
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400):
            raise ValueError('La configuration OAuth commune ne doit pas être un lien ou une jonction.')
    return path


def normalize_google_oauth_client(value):
    """Strip official download metadata; reject accounts, tokens and other clients."""
    if not isinstance(value, dict) or set(value) != {'installed'} or not isinstance(value['installed'], dict):
        raise ValueError('La configuration Google commune doit être un client OAuth « Application de bureau », sans compte ni jeton.')
    installed = value['installed']
    if set(installed) - _DESKTOP_FIELDS:
        raise ValueError('La configuration Google commune contient des champs non autorisés ; aucun compte ou jeton personnel ne peut être distribué.')
    client_id = installed.get('client_id')
    if not isinstance(client_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{6,220}\.apps\.googleusercontent\.com', client_id):
        raise ValueError('L’identifiant du client OAuth Google commun est invalide.')
    secret = installed.get('client_secret', '')
    if not isinstance(secret, str) or len(secret) > 512 or any(ord(char) < 32 for char in secret):
        raise ValueError('La configuration du client OAuth Google commun est invalide.')
    return {'installed': {'client_id': client_id, 'client_secret': secret}}


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('Le fichier OAuth Google commun contient une clé JSON en double.')
        result[key] = value
    return result


def read_google_oauth_client(path):
    path = _plain_path(path)
    try:
        with path.open('rb') as stream:
            raw = stream.read(MAX_CLIENT_BYTES + 1)
        if len(raw) > MAX_CLIENT_BYTES:
            raise ValueError('Le fichier OAuth Google commun dépasse la limite de 64 Ko.')
        def invalid_constant(_):
            raise ValueError('Le fichier OAuth Google commun contient une valeur JSON invalide.')
        value = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=_pairs, parse_constant=invalid_constant)
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError('Le fichier OAuth Google commun est absent, illisible ou invalide.') from exc
    return normalize_google_oauth_client(value)


def select_google_oauth_client(assets, explicit=None, required=False):
    """Explicit input wins. Never infer a client from a user's data/cloud folder."""
    if explicit is not None:
        return read_google_oauth_client(explicit)
    candidate = _plain_path(Path(assets) / GOOGLE_OAUTH_ASSET)
    if candidate.exists():
        return read_google_oauth_client(candidate)
    if required:
        raise ValueError('Google Drive doit être prêt pour cette distribution. Fournis le client OAuth commun avec --google-oauth-client CHEMIN.')
    return None


def write_google_oauth_client(assets, configuration):
    if configuration is None:
        return
    assets = _plain_path(assets)
    assets.mkdir(parents=True, exist_ok=True)
    target = _plain_path(assets / GOOGLE_OAUTH_ASSET)
    target.write_text(json.dumps(normalize_google_oauth_client(configuration), ensure_ascii=True, indent=2) + '\n', encoding='utf-8')
