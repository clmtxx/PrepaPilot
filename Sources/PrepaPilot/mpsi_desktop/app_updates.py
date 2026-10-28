"""Public GitHub release checks and bounded, verified installer downloads.

This module uses only the standard library. Call its synchronous operations in a
worker. It never runs a downloaded file and sends no account or application data.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


MAX_INSTALLER_SIZE = 512 * 1024 * 1024
MAX_METADATA_SIZE = 2 * 1024 * 1024
MAX_CHECKSUM_SIZE = 128 * 1024
CHUNK_SIZE = 64 * 1024
NETWORK_TIMEOUT = 20
DOWNLOAD_SECONDS = 15 * 60
_VERSION = r'(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})\.(0|[1-9][0-9]{0,5})'
_REPOSITORY = re.compile(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9_.-]{1,100}')


class UpdateError(Exception):
    """A safe, stable error code for the translated interface."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    installer_name: str
    installer_url: str
    checksum_url: str
    release_url: str
    size: int
    repository: str


def _repository(value: str) -> str:
    if (not isinstance(value, str) or not _REPOSITORY.fullmatch(value)
            or value.split('/')[1] in ('.', '..') or value.endswith('.git')):
        raise UpdateError('invalid_channel')
    return value


def _version(value: str) -> tuple[int, int, int]:
    if not isinstance(value, str) or not re.fullmatch(_VERSION, value):
        raise UpdateError('invalid_release')
    return tuple(map(int, value.split('.')))


def read_channel(app_assets: Path) -> str | None:
    """Read the publisher's channel. An unconfigured source build stays offline."""
    path = Path(app_assets) / 'update-channel.json'
    if not path.exists():
        return None
    try:
        with path.open('rb') as stream:
            content = stream.read(4097)
        if len(content) > 4096:
            raise UpdateError('invalid_channel')
        config = json.loads(content.decode('utf-8-sig'))
        if not isinstance(config, dict):
            raise UpdateError('invalid_channel')
        repository = config.get('repository')
        if repository in (None, ''):
            return None
        return _repository(repository)
    except (OSError, UnicodeError, ValueError) as exc:
        raise UpdateError('invalid_channel') from exc


def _validate_url(url: str, repository: str, kind: str, *, redirect=False):
    """Only the configured GitHub repository may introduce an asset CDN URL."""
    if not isinstance(url, str) or len(url) > 12000 or any(ord(c) < 33 for c in url):
        raise UpdateError('invalid_release')
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise UpdateError('invalid_release') from exc
    if (parsed.scheme != 'https' or parsed.username or parsed.password
            or port not in (None, 443) or parsed.fragment or '\\' in url):
        raise UpdateError('invalid_release')
    if kind == 'api':
        valid = (parsed.hostname == 'api.github.com' and not parsed.query
                 and parsed.path.lower() == f'/repos/{repository}/releases/latest'.lower())
    elif redirect and parsed.hostname in ('release-assets.githubusercontent.com',
                                          'objects.githubusercontent.com'):
        valid = parsed.path.startswith('/github-production-release-asset-')
    else:
        prefix = f'/{repository}/releases/download/'
        valid = (parsed.hostname == 'github.com' and not parsed.query
                 and parsed.path.lower().startswith(prefix.lower())
                 and re.fullmatch(r'v' + _VERSION + r'/[A-Za-z0-9_.-]{1,180}',
                                  parsed.path[len(prefix):]) is not None)
    if not valid:
        raise UpdateError('invalid_release')


class _SafeRedirects(HTTPRedirectHandler):
    def __init__(self, repository: str, kind: str):
        super().__init__()
        self.repository, self.kind = repository, kind

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_url(newurl, self.repository, self.kind, redirect=True)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open(url: str, repository: str, kind: str):
    _validate_url(url, repository, kind)
    request = Request(url, headers={
        'Accept': 'application/vnd.github+json' if kind == 'api' else 'application/octet-stream',
        'Accept-Encoding': 'identity',
        'User-Agent': 'PrepaPilot-Updater',
        'X-GitHub-Api-Version': '2026-03-10',
    }, method='GET')
    response = build_opener(_SafeRedirects(repository, kind)).open(request, timeout=NETWORK_TIMEOUT)
    try:
        _validate_url(response.geturl(), repository, kind, redirect=True)
        if response.status != 200 or response.headers.get('Content-Encoding', 'identity') != 'identity':
            raise UpdateError('network')
        return response
    except BaseException:
        response.close()
        raise


def _network_error(exc):
    return UpdateError('rate_limited' if isinstance(exc, HTTPError) and exc.code in (403, 429) else 'network')


def _length(response, limit: int, *, exact: int | None = None):
    raw = response.headers.get('Content-Length')
    if raw is None:
        return
    if not re.fullmatch(r'[0-9]{1,12}', raw):
        raise UpdateError('download_size')
    size = int(raw)
    if size > limit or (exact is not None and size != exact):
        raise UpdateError('download_size')


def _small_request(url: str, repository: str, kind: str, limit: int) -> bytes:
    with _open(url, repository, kind) as response:
        _length(response, limit)
        deadline = time.monotonic() + 60
        parts, size = [], 0
        while True:
            if time.monotonic() > deadline:
                raise UpdateError('network')
            data = response.read(min(CHUNK_SIZE, limit + 1 - size))
            if not data:
                return b''.join(parts)
            size += len(data)
            if size > limit:
                raise UpdateError('download_size')
            parts.append(data)


def check_release(repository: str, current_version: str) -> ReleaseInfo | None:
    """Return a newer stable release, without downloading its installer."""
    repository = _repository(repository)
    current = _version(current_version)
    try:
        raw = _small_request(f'https://api.github.com/repos/{repository}/releases/latest',
                             repository, 'api', MAX_METADATA_SIZE)
    except HTTPError as exc:
        if exc.code == 404:
            return None
        raise _network_error(exc) from exc
    except (OSError, URLError) as exc:
        raise _network_error(exc) from exc
    try:
        data = json.loads(raw.decode('utf-8'))
        if not isinstance(data, dict):
            raise UpdateError('invalid_release')
        if data.get('draft') is not False or data.get('prerelease') is not False:
            return None
        tag = data.get('tag_name')
        if not isinstance(tag, str) or not re.fullmatch('v' + _VERSION, tag):
            return None
        version = tag[1:]
        if _version(version) <= current:
            return None
        release_url = f'https://github.com/{repository}/releases/tag/{tag}'
        if not isinstance(data.get('html_url'), str) or data['html_url'].casefold() != release_url.casefold():
            raise UpdateError('invalid_release')
        assets = data.get('assets')
        if not isinstance(assets, list) or len(assets) > 200:
            raise UpdateError('invalid_release')
        installer_name = f'PrepaPilot-{version}-Setup.exe'
        selected = {}
        for asset in assets:
            if not isinstance(asset, dict):
                raise UpdateError('invalid_release')
            name = asset.get('name')
            if name not in (installer_name, 'SHA256SUMS.txt'):
                continue
            if name in selected or asset.get('state') != 'uploaded':
                raise UpdateError('invalid_release')
            url = f'https://github.com/{repository}/releases/download/{tag}/{name}'
            asset_url = asset.get('browser_download_url')
            if not isinstance(asset_url, str) or asset_url.casefold() != url.casefold():
                raise UpdateError('invalid_release')
            size = asset.get('size')
            limit = MAX_INSTALLER_SIZE if name == installer_name else MAX_CHECKSUM_SIZE
            if isinstance(size, bool) or not isinstance(size, int) or not 1 <= size <= limit:
                raise UpdateError('invalid_release')
            selected[name] = asset
        if set(selected) != {installer_name, 'SHA256SUMS.txt'}:
            raise UpdateError('invalid_release')
        download_base = f'https://github.com/{repository}/releases/download/{tag}/'
        return ReleaseInfo(version, installer_name, download_base + installer_name,
                           download_base + 'SHA256SUMS.txt', release_url,
                           selected[installer_name]['size'], repository)
    except (UnicodeError, ValueError, TypeError) as exc:
        raise UpdateError('invalid_release') from exc


def _expected_checksum(raw: bytes, installer_name: str) -> str:
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeError as exc:
        raise UpdateError('invalid_checksum') from exc
    checksums = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r'([a-fA-F0-9]{64}) [ *]([A-Za-z0-9_.-]{1,180})', line)
        if not match or match[2] in checksums or match[2] in ('.', '..'):
            raise UpdateError('invalid_checksum')
        checksums[match[2]] = match[1].lower()
    if installer_name not in checksums:
        raise UpdateError('invalid_checksum')
    return checksums[installer_name]


def _validate_installer(path: Path):
    """Inno's installer is PE32 even when its payload targets Windows x64."""
    size = path.stat().st_size
    with path.open('rb') as stream:
        header = stream.read(64)
        if len(header) != 64 or header[:2] != b'MZ':
            raise UpdateError('invalid_installer')
        offset = struct.unpack_from('<I', header, 60)[0]
        if not 64 <= offset <= min(size - 26, 1024 * 1024):
            raise UpdateError('invalid_installer')
        stream.seek(offset)
        pe = stream.read(26)
        if len(pe) != 26 or pe[:4] != b'PE\0\0':
            raise UpdateError('invalid_installer')
        machine, sections = struct.unpack_from('<HH', pe, 4)
        optional_size, characteristics = struct.unpack_from('<HH', pe, 20)
        magic = struct.unpack_from('<H', pe, 24)[0]
        if (not 1 <= sections <= 96 or not characteristics & 0x0002
                or characteristics & 0x2000 or optional_size < 96
                or offset + 24 + optional_size + sections * 40 > size
                or (machine, magic) not in ((0x014c, 0x010b), (0x8664, 0x020b))):
            raise UpdateError('invalid_installer')


def _validate_info(info: ReleaseInfo):
    repository = _repository(info.repository)
    _version(info.version)
    name = f'PrepaPilot-{info.version}-Setup.exe'
    base = f'https://github.com/{repository}/releases/'
    if (info.installer_name != name
            or info.installer_url != f'{base}download/v{info.version}/{name}'
            or info.checksum_url != f'{base}download/v{info.version}/SHA256SUMS.txt'
            or info.release_url != f'{base}tag/v{info.version}'
            or isinstance(info.size, bool) or not isinstance(info.size, int)
            or not 1 <= info.size <= MAX_INSTALLER_SIZE):
        raise UpdateError('invalid_release')


def download_release(info: ReleaseInfo, cache_dir: Path, progress=None) -> Path:
    """Download, hash and validate an installer before atomically exposing it.

    ``progress(received_bytes, total_bytes)`` runs in the calling worker. The
    returned path is safe to offer for explicit installation; it is never run.
    """
    _validate_info(info)
    partial = None
    try:
        checksum = _expected_checksum(_small_request(info.checksum_url, info.repository,
                                                     'asset', MAX_CHECKSUM_SIZE), info.installer_name)
        cache_dir = Path(cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix=info.installer_name + '.', suffix='.part', dir=cache_dir)
        partial = Path(name)
        digest, received = hashlib.sha256(), 0
        deadline = time.monotonic() + DOWNLOAD_SECONDS
        with os.fdopen(descriptor, 'wb') as output:
            with _open(info.installer_url, info.repository, 'asset') as response:
                _length(response, MAX_INSTALLER_SIZE, exact=info.size)
                if progress:
                    progress(0, info.size)
                while True:
                    if time.monotonic() > deadline:
                        raise UpdateError('network')
                    block = response.read(min(CHUNK_SIZE, info.size + 1 - received))
                    if not block:
                        break
                    received += len(block)
                    if received > info.size:
                        raise UpdateError('download_size')
                    output.write(block)
                    digest.update(block)
                    if progress:
                        progress(received, info.size)
            output.flush()
            os.fsync(output.fileno())
        if received != info.size:
            raise UpdateError('download_size')
        if digest.hexdigest() != checksum:
            raise UpdateError('checksum_mismatch')
        _validate_installer(partial)
        destination = cache_dir / info.installer_name
        os.replace(partial, destination)
        partial = None
        return destination
    except HTTPError as exc:
        raise _network_error(exc) from exc
    except (URLError, TimeoutError, ConnectionError) as exc:
        raise UpdateError('network') from exc
    except OSError as exc:
        raise UpdateError('disk_error') from exc
    finally:
        if partial is not None:
            try:
                partial.unlink(missing_ok=True)
            except OSError:
                pass
