"""Check the real windowed loading helper, including its inherited Windows pipe."""
import argparse
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import subprocess
import time

from chemins import WORKSPACE, local_root


def windows_for_process(pid):
    user = ctypes.WinDLL('user32', use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    matches = []

    @callback_type
    def visit(handle, _):
        owner = wintypes.DWORD()
        user.GetWindowThreadProcessId(handle, ctypes.byref(owner))
        if owner.value == pid and user.IsWindowVisible(handle):
            title = ctypes.create_unicode_buffer(256)
            user.GetWindowTextW(handle, title, len(title))
            if title.value == 'PrépaPilot — Ouverture':
                matches.append(handle)
        return True

    user.EnumWindows(visit, 0)
    return matches


def verify_startup(executable):
    executable = Path(executable).resolve(strict=True)
    for mode in ('close', 'eof'):
        process = subprocess.Popen([str(executable), '--startup-splash'], cwd=executable.parent,
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            process.stdin.write(json.dumps(dict(status='Préparation de tes pages…', theme='dark', reduced_motion=False)) + '\n')
            process.stdin.flush()
            deadline = time.monotonic() + 12
            while not windows_for_process(process.pid):
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError('La fenêtre de chargement compilée ne s’affiche pas.')
                time.sleep(.04)
            # Let the independent event loop run while this parent is occupied.
            time.sleep(.25)
            if process.poll() is not None:
                raise RuntimeError('L’écran a quitté avant la fin du chargement.')
            process.stdin.write(json.dumps(dict(theme='light', reduced_motion=True)) + '\n')
            process.stdin.flush()
            if mode == 'close':
                process.stdin.write('{"close":true}\n')
                process.stdin.flush()
                # The explicit command must work even with the pipe still open.
            else:
                process.stdin.close()
            if process.wait(timeout=5) != 0:
                raise RuntimeError('La fermeture du chargement a échoué.')
            if windows_for_process(process.pid):
                raise RuntimeError('Une fenêtre de chargement est restée ouverte.')
        finally:
            if process.stdin is not None and not process.stdin.closed:
                process.stdin.close()
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
    print('Démarrage vérifié : fenêtre Windows affichée, préférences transmises, fermeture sur commande et sur fin du parent, aucun processus restant.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installed', action='store_true', help='Contrôler la version installée plutôt que la livraison.')
    options = parser.parse_args()
    folder = WORKSPACE / 'Application' / 'PrepaPilot' if options.installed else local_root() / 'Livraison' / 'PrepaPilot'
    verify_startup(folder / 'PrepaPilot.exe')
