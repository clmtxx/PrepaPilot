"""Explicit installer hand-off, used only after data and the app lock are closed."""
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys


@dataclass(frozen=True)
class InstallRequest:
    path: Path
    version: str
    size: int
    sha256: str


def _plain(path):
    path = Path(os.path.abspath(path))
    if any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)):
        raise ValueError('Invalid installer path')
    # Windows 8.3 aliases are valid only after every redirect has been rejected.
    return path.resolve()


def _digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def prepare_install(path, version, cache_dir, expected_digest):
    path, cache = _plain(path), _plain(cache_dir)
    if (not isinstance(version, str) or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version)
            or path.parent != cache or path.name != f'PrepaPilot-{version}-Setup.exe'
            or not path.is_file() or not isinstance(expected_digest, str)
            or not re.fullmatch(r'[0-9a-f]{64}', expected_digest)):
        raise ValueError('Invalid installer')
    size = path.stat().st_size
    if not 64 <= size <= 512 * 1024 * 1024 or _digest(path) != expected_digest:
        raise ValueError('Installer changed')
    return InstallRequest(path, version, size, expected_digest)


def launch_update(request, language='fr'):
    if sys.platform != 'win32':
        raise ValueError('Windows installer required')
    checked = prepare_install(request.path, request.version, request.path.parent, request.sha256)
    if checked.size != request.size:
        raise ValueError('Installer changed')
    environment = os.environ.copy()
    # The new application, launched later by the installer, must start with its
    # own PyInstaller runtime instead of inheriting this process's boot state.
    environment['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    if getattr(sys, 'frozen', False):
        import ctypes
        ctypes.windll.kernel32.SetDllDirectoryW(None)
        bundle = str(Path(sys._MEIPASS).resolve()).casefold()
        environment['PATH'] = os.pathsep.join(item for item in environment.get('PATH', '').split(os.pathsep)
            if item.casefold() != bundle and not item.casefold().startswith(bundle + os.sep))
    return subprocess.Popen([str(request.path), '/NORESTART',
                             '/LANG=' + ('english' if language == 'en' else 'french')],
                            cwd=request.path.parent, env=environment,
                            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                            close_fds=True)
