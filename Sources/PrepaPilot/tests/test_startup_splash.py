"""Native loading-card rendering and parent/child lifecycle checks."""
import io
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import subprocess
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QApplication

from mpsi_desktop.startup_splash import StartupSplash, _read_commands, run_splash


APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class _CapturedSignal:
    def __init__(self):
        self.values = []

    def emit(self, *args):
        self.values.append(args)


class _TestBridge:
    def __init__(self):
        self.command = _CapturedSignal()
        self.finished = _CapturedSignal()


class StartupSplashTests(unittest.TestCase):
    def setUp(self):
        self.errors = []
        self.old_hook = sys.excepthook
        sys.excepthook = lambda kind, value, trace: self.errors.append(str(value))
        self.splash = StartupSplash()
        self.splash.show()
        APP.processEvents()

    def tearDown(self):
        self.splash.shutdown()
        self.splash.deleteLater()
        APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        APP.processEvents()
        sys.excepthook = self.old_hook
        self.assertEqual(self.errors, [])

    def test_two_themes_paint_and_status_is_accessible(self):
        images = []
        for theme in ("light", "dark"):
            self.splash.set_preferences(theme=theme, reduced_motion=True)
            self.splash.set_status("Préparation de tes documents…")
            images.append(self.splash.grab().toImage())
            self.assertFalse(images[-1].isNull())
            self.assertEqual(images[-1].size(), self.splash.size())
        self.assertNotEqual(images[0], images[1])
        self.assertIn("documents", self.splash.accessibleDescription())
        self.assertTrue(self.splash.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating))
        self.assertFalse(self.splash.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)

    def test_motion_changes_frames_and_reduced_motion_stops_it(self):
        self.assertTrue(self.splash.animation_timer.isActive())
        self.splash._phase = 0
        first = self.splash.grab().toImage()
        self.splash._phase = 1.2
        second = self.splash.grab().toImage()
        self.assertNotEqual(first, second)
        self.splash.set_preferences(reduced_motion=True)
        self.assertFalse(self.splash.animation_timer.isActive())
        resting = self.splash.grab().toImage()
        self.splash._advance()
        self.assertEqual(resting, self.splash.grab().toImage())
        self.splash.set_preferences(reduced_motion=False)
        self.assertTrue(self.splash.animation_timer.isActive())

    def test_hide_and_shutdown_stop_motion_and_close_once(self):
        closed = []
        self.splash.closed.connect(lambda: closed.append(True))
        self.splash.hide()
        self.assertFalse(self.splash.animation_timer.isActive())
        self.splash.show()
        self.assertTrue(self.splash.animation_timer.isActive())
        self.splash.shutdown()
        self.splash.shutdown()
        self.splash.set_preferences(reduced_motion=False)
        self.assertEqual(closed, [True])
        self.assertFalse(self.splash.isVisible())
        self.assertFalse(self.splash.animation_timer.isActive())

    def test_protocol_ignores_malformed_lines_and_eof_closes(self):
        bridge, closing = _TestBridge(), threading.Event()
        _read_commands(io.StringIO('oops\n[1]\n{"status":"Chargement…"}\n'), bridge, closing)
        self.assertEqual(bridge.command.values, [({"status": "Chargement…"},)])
        self.assertTrue(closing.is_set())
        self.assertEqual(bridge.finished.values, [()])

    def test_close_message_prevents_processing_later_commands(self):
        bridge, closing = _TestBridge(), threading.Event()
        _read_commands(io.StringIO('{"close":true}\n{"status":"Trop tard"}\n'), bridge, closing)
        self.assertEqual(bridge.command.values, [])
        self.assertTrue(closing.is_set())
        self.assertEqual(bridge.finished.values, [()])

    def test_helper_exits_on_immediate_eof_and_explicit_close(self):
        root = Path(__file__).resolve().parents[1]
        command = [sys.executable, "-B", "-c",
                   "from mpsi_desktop.startup_splash import run_splash; raise SystemExit(run_splash())"]
        for payload in ("", '{"theme":"dark","reduced_motion":true}\n{"close":true}\n'):
            result = subprocess.run(command, cwd=root, input=payload, text=True,
                                    capture_output=True, timeout=15,
                                    env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_parent_pipe_exits_without_a_window(self):
        with patch("mpsi_desktop.startup_splash._input_stream", return_value=None), \
                patch("mpsi_desktop.startup_splash.StartupSplash") as window:
            self.assertEqual(run_splash(), 0)
            window.assert_not_called()

    @unittest.skipUnless(sys.platform == "win32", "Windows windowed-executable pipe")
    def test_windowed_helper_reads_inherited_handle_without_sys_stdin(self):
        command = [sys.executable, "-B", "-c",
                   "import sys; sys.stdin = None; "
                   "from mpsi_desktop.startup_splash import run_splash; raise SystemExit(run_splash())"]
        process = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[1],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True,
                                   env={**os.environ, "QT_QPA_PLATFORM": "offscreen"})
        try:
            process.stdin.write('{"close":true}\n')
            process.stdin.flush()
            # Keep the pipe open: the explicit close command must suffice.
            self.assertEqual(process.wait(timeout=15), 0)
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
