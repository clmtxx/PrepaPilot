"""The focus lens never changes the real time or reads storage while drawing."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QAbstractAnimation, QEvent, QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

from mpsi_desktop.dashboard import FocusDial as DashboardDial
from mpsi_desktop.focus_visuals import FocusDial


APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class Context(QObject):
    theme_changed = Signal()
    data_changed = Signal()

    def __init__(self):
        super().__init__()
        self.theme = "light"
        self.db = Mock()
        self.db.get_setting.return_value = False


class FocusVisualTests(unittest.TestCase):
    def setUp(self):
        self.old_motion = APP.property("reducedMotion")
        APP.setProperty("reducedMotion", False)
        self.errors = []
        self.previous_hook = sys.excepthook
        sys.excepthook = lambda kind, value, tb: self.errors.append(str(value))
        self.ctx = Context()
        self.dial = FocusDial(self.ctx)
        self.dial.show()
        APP.processEvents()
        self.dial._reset_motion()

    def tearDown(self):
        self.dial.close()
        self.dial.deleteLater()
        APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        APP.processEvents()
        APP.setProperty("reducedMotion", self.old_motion)
        sys.excepthook = self.previous_hook
        self.assertEqual(self.errors, [])

    def test_dashboard_keeps_the_public_dial_api_and_exact_time(self):
        self.assertIs(DashboardDial, FocusDial)
        self.assertEqual((self.dial.width(), self.dial.height()), (168, 168))
        self.dial.set_seconds(65)
        self.assertEqual(self.dial.time_text, "01:05")
        self.assertIn("01:05", self.dial.accessibleName())
        self.assertNotEqual(self.dial.display_seconds, 65)
        self.dial.animation.setCurrentTime(self.dial.animation.duration())
        self.assertEqual(self.dial.display_seconds, 65)
        self.assertEqual(self.dial.time_text, "01:05")
        self.dial.total_seconds = 240 * 60
        self.dial.set_seconds(240 * 60)
        self.assertEqual(self.dial.time_text, "240:00")
        self.assertFalse(self.dial.grab().isNull())

    def test_countdown_and_hover_reuse_fixed_face_without_database_reads(self):
        self.dial.grab()
        cache = self.dial._artwork.layers["face"].cacheKey()
        with patch.object(self.ctx.db, "get_setting", side_effect=AssertionError("Storage read during motion")):
            self.dial.set_seconds(125)
            self.dial._shine()
            for time in (50, 150, 300):
                self.dial.animation.setCurrentTime(time)
                self.dial.sheen_animation.setCurrentTime(time)
                self.assertFalse(self.dial.grab().isNull())
                self.assertEqual(self.dial._artwork.layers["face"].cacheKey(), cache)
        self.assertEqual(self.dial.findChildren(QTimer), [])

    def test_both_themes_cache_separately_and_repeated_paints_are_identical(self):
        light = self.dial.grab().toImage()
        cache = self.dial._artwork.layers["face"].cacheKey()
        self.assertEqual(light, self.dial.grab().toImage())
        self.ctx.theme = "dark"
        self.ctx.theme_changed.emit()
        dark = self.dial.grab().toImage()
        self.assertNotEqual(light, dark)
        self.assertNotEqual(cache, self.dial._artwork.layers["face"].cacheKey())
        self.assertEqual(dark, self.dial.grab().toImage())

    def test_hiding_stops_all_effects_and_uses_exact_remaining_time(self):
        self.dial.set_seconds(123)
        self.dial._shine()
        self.dial.hide()
        self.assertEqual(self.dial.display_seconds, 123)
        for animation in self.dial.findChildren(QAbstractAnimation):
            self.assertEqual(animation.state(), QAbstractAnimation.State.Stopped)
        self.dial.set_seconds(0)
        self.assertEqual(self.dial.time_text, "00:00")
        self.assertEqual(self.dial.display_seconds, 0)
        self.assertEqual(self.dial.sheen_animation.state(), QAbstractAnimation.State.Stopped)
        self.dial.show()
        APP.processEvents()
        self.assertEqual(self.dial.animation.state(), QAbstractAnimation.State.Stopped)

    def test_global_and_saved_reduced_motion_stop_inflight_effects(self):
        self.dial.set_seconds(123)
        self.dial._shine()
        APP.setProperty("reducedMotion", True)
        self.assertEqual(self.dial.display_seconds, 123)
        self.assertTrue(all(animation.state() == QAbstractAnimation.State.Stopped
                            for animation in self.dial.findChildren(QAbstractAnimation)))
        APP.setProperty("reducedMotion", False)
        self.dial._shine()
        self.ctx.db.get_setting.return_value = True
        self.ctx.data_changed.emit()
        self.dial.set_seconds(60)
        self.dial._shine()
        self.assertEqual(self.dial.display_seconds, 60)
        self.assertTrue(all(animation.state() == QAbstractAnimation.State.Stopped
                            for animation in self.dial.findChildren(QAbstractAnimation)))

    def test_completion_glint_is_finite_and_does_not_repeat_at_zero(self):
        self.dial.set_seconds(0)
        self.assertTrue(self.dial._completion)
        self.assertEqual(self.dial.time_text, "00:00")
        self.assertEqual(self.dial.sheen_animation.state(), QAbstractAnimation.State.Running)
        self.dial.animation.setCurrentTime(self.dial.animation.duration())
        self.dial.sheen_animation.setCurrentTime(self.dial.sheen_animation.duration())
        self.dial.set_seconds(0)
        for animation in self.dial.findChildren(QAbstractAnimation):
            self.assertEqual(animation.loopCount(), 1)
            self.assertEqual(animation.state(), QAbstractAnimation.State.Stopped)
        self.assertEqual(self.dial._sheen, 1.0)


if __name__ == "__main__":
    unittest.main()
