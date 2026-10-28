"""Navigation remains immediate and usable while its decorative layer animates."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QEvent, Qt, QAbstractAnimation
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from mpsi_desktop.context import AppContext
from mpsi_desktop.window import MainWindow

APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class PageTransitionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ctx = AppContext(Path(self.temp.name) / 'data')
        self.ctx.db.set_setting('desktop_reduced_motion', False)
        self.window = MainWindow(self.ctx, show_welcome=False)
        self.window.show()
        APP.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        APP.sendPostedEvents(None, QEvent.DeferredDelete)
        APP.processEvents()
        self.ctx.close()
        self.temp.cleanup()

    def test_snapshot_finishes_and_releases_images_without_moving_live_widgets(self):
        geometry = self.window.stack.geometry()
        self.window.navigate('notes')
        layer = self.window.transition
        self.assertEqual(self.window.current_key, 'notes')
        self.assertIs(self.window.stack.currentWidget(), self.window.wrappers['notes'])
        self.assertTrue(layer.isVisible())
        self.assertFalse(layer.before.isNull())
        self.assertFalse(layer.after.isNull())
        self.assertEqual(self.window.stack.geometry(), geometry)
        layer.animation.setCurrentTime(layer.animation.duration())
        self.assertFalse(layer.isVisible())
        self.assertTrue(layer.before.isNull())
        self.assertTrue(layer.after.isNull())
        self.assertTrue(layer._light.isNull())

    def test_decorative_frames_reuse_captures_and_shortcuts_cancel_immediately(self):
        self.window.navigate('notes')
        layer = self.window.transition
        layer.animation.pause()
        with patch.object(layer, 'capture', side_effect=AssertionError('No capture during a frame')), \
                patch.object(layer, '_prepare_light', side_effect=AssertionError('No light rebuild during a frame')):
            for progress in (0.15, 0.5, 0.85):
                layer.advance(progress)
                self.assertFalse(layer.grab().isNull())
        APP.sendEvent(self.window, QKeyEvent(QEvent.ShortcutOverride, Qt.Key_Tab, Qt.NoModifier))
        self.assertFalse(layer.isVisible())
        self.assertEqual(layer.animation.state(), QAbstractAnimation.Stopped)
        self.assertTrue(layer._light.isNull())

    def test_rapid_navigation_ends_on_last_page_and_click_remains_effective(self):
        for key in ('time', 'notes', 'documents', 'settings'):
            self.window.navigate(key)
        self.assertEqual(self.window.current_key, 'settings')
        field = self.window.pages['settings'].name
        QTest.mouseClick(field, Qt.LeftButton)
        self.assertFalse(self.window.transition.isVisible())
        QTest.keyClicks(field, 'Camille')
        self.assertEqual(field.text(), 'Camille')

    def test_large_display_capture_has_bounded_memory_and_preserves_native_geometry(self):
        self.window.resize(3840, 2160)
        APP.processEvents()
        geometry = self.window.stack.geometry()
        image = self.window.transition.capture(self.window.stack)
        self.assertFalse(image.isNull())
        self.assertLessEqual(image.width() * image.height(), self.window.transition.MAX_CAPTURE_PIXELS)
        self.assertEqual(self.window.stack.geometry(), geometry)

    def test_reduced_motion_theme_resize_and_close_cancel_decorations(self):
        self.window.navigate('notes')
        self.ctx.db.set_setting('desktop_reduced_motion', True)
        self.ctx.mark_changed()
        self.assertFalse(self.window.transition.isVisible())
        self.assertEqual(self.window.animation.state(), QAbstractAnimation.Stopped)
        self.window.navigate('time')
        self.assertFalse(self.window.transition.isVisible())
        self.ctx.db.set_setting('desktop_reduced_motion', False)
        self.ctx.mark_changed()
        self.window.navigate('documents')
        self.ctx.set_theme('dark')
        self.assertFalse(self.window.transition.isVisible())
        self.window.navigate('memory')
        self.window.resize(self.window.width() + 20, self.window.height())
        self.assertFalse(self.window.transition.isVisible())
        self.window.navigate('settings')
        self.window.close()
        self.assertTrue(self.window.transition.before.isNull())
        self.assertEqual(self.window.animation.state(), QAbstractAnimation.Stopped)


if __name__ == '__main__': unittest.main()
