"""Optional startup feedback, isolated from the application's loading thread."""
from .i18n import tr
from pathlib import Path
import json
import os
import subprocess
import sys


class StartupScreen:
    """Own exactly one disposable helper; it never accesses personal data."""

    def __init__(self, command=None):
        self.process = None
        self.command = command or ([sys.executable, '--startup-splash'] if getattr(sys, 'frozen', False)
                                   else [sys.executable, '-B', str(Path(__file__).resolve().parents[1] / 'lancer.py'), '--startup-splash'])

    def start(self):
        if self.process is not None:
            return
        options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
        try:
            self.process = subprocess.Popen(self.command, stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                text=True, encoding='utf-8', bufsize=1, **options)
            self.update('PrépaPilot')
        except OSError:
            # Feedback is optional: a failed helper must never prevent startup.
            self.process = None

    @staticmethod
    def _send(process, message):
        try:
            if process.poll() is None and process.stdin is not None:
                # ASCII JSON also survives Windows' inherited console encoding.
                process.stdin.write(json.dumps(message, ensure_ascii=True) + '\n')
                process.stdin.flush()
        except (OSError, ValueError):
            pass

    def update(self, status=None, *, theme=None, reduced_motion=None, language=None):
        process = self.process
        if process is None:
            return
        message = {}
        if language in ('fr', 'en'):
            message['language'] = language
        if status is not None:
            message['status'] = str(status)[:240]
        if theme in ('light', 'dark'):
            message['theme'] = theme
        if reduced_motion is not None:
            message['reduced_motion'] = bool(reduced_motion)
        self._send(process, message)

    def close(self):
        process, self.process = self.process, None
        if process is None:
            return
        self._send(process, {'close': True})
        try:
            if process.stdin is not None:
                process.stdin.close()
        except (OSError, ValueError):
            pass
        try:
            process.wait(timeout=.7)
        except subprocess.TimeoutExpired:
            # Only terminate the helper created above, never another app process.
            try:
                process.terminate()
                process.wait(timeout=.5)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                    process.wait(timeout=.5)
                except (OSError, subprocess.TimeoutExpired):
                    pass
            except OSError:
                pass
        except OSError:
            pass
