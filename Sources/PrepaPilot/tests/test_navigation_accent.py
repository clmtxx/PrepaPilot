"""The moving page accent preserves native navigation and stops when inactive."""
import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QAbstractAnimation, QEvent, QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QHBoxLayout, QWidget
from mpsi_desktop.navigation_accent import NavigationAccent
from mpsi_desktop.widgets import button

APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class NavigationAccentTests(unittest.TestCase):
    def setUp(self):
        self.previous_motion = APP.property("reducedMotion")
        self.previous_theme = APP.property("visualTheme")
        APP.setProperty("reducedMotion", False)
        APP.setProperty("visualTheme", "light")
        self.errors = []
        self.previous_hook = sys.excepthook
        sys.excepthook = lambda kind, error, traceback: self.errors.append((kind.__name__, str(error)))
        self.sidebar = QWidget()
        self.sidebar.resize(760, 70)
        layout = QHBoxLayout(self.sidebar)
        layout.setContentsMargins(20, 10, 20, 10)
        self.buttons = {}
        for key, label in (("home", "Aujourd’hui"), ("time", "Gestion du temps"), ("notes", "Notes"), ("settings", "Réglages")):
            control = button(label)
            control.setCheckable(True)
            control.setProperty("role", "nav")
            layout.addWidget(control)
            self.buttons[key] = control
        self.accent = NavigationAccent(self.sidebar, self.buttons)
        self.sidebar.show()
        APP.processEvents()
        self.accent.sync()

    def tearDown(self):
        self.sidebar.close()
        self.sidebar.deleteLater()
        APP.sendPostedEvents(None, QEvent.DeferredDelete)
        APP.processEvents()
        APP.setProperty("reducedMotion", self.previous_motion)
        APP.setProperty("visualTheme", self.previous_theme)
        sys.excepthook = self.previous_hook
        self.assertEqual(self.errors, [])

    def test_navigation_has_one_bounded_animation_and_no_layout_shift(self):
        bounds = {key: control.geometry() for key, control in self.buttons.items()}
        start = self.accent.geometry()
        self.accent.select("notes")
        self.assertEqual(self.accent.animation.state(), QAbstractAnimation.Running)
        self.assertEqual(self.accent.animation.loopCount(), 1)
        self.assertLessEqual(self.accent.animation.duration(), 300)
        destination = self.accent._target_rect()
        self.accent.animation.setCurrentTime(100)
        self.assertGreater(self.accent.x(), start.x())
        self.assertLess(self.accent.x(), destination.x())
        self.assertLessEqual(self.accent.width(), 66)
        self.assertEqual(self.accent.height(), 9)
        self.accent.animation.setCurrentTime(self.accent.animation.duration())
        self.assertEqual(self.accent.geometry(), destination)
        self.assertEqual(self.accent.animation.state(), QAbstractAnimation.Stopped)
        self.assertEqual(bounds, {key: control.geometry() for key, control in self.buttons.items()})

    def test_rapid_navigation_continues_from_visible_position(self):
        self.accent.select("settings")
        self.accent.animation.setCurrentTime(100)
        position = self.accent.geometry()
        self.accent.select("time")
        self.assertEqual(self.accent.geometry(), position)
        self.accent.animation.setCurrentTime(self.accent.animation.duration())
        self.assertEqual(self.accent.current, "time")
        self.assertEqual(self.accent.geometry(), self.accent._target_rect())
        self.accent.select("unknown")
        self.assertEqual(self.accent.current, "time")
        self.assertEqual(self.accent.animation.state(), QAbstractAnimation.Stopped)

    def test_reduced_motion_snaps_immediately_and_suppresses_further_animation(self):
        self.accent.select("notes")
        self.accent.animation.setCurrentTime(80)
        APP.setProperty("reducedMotion", True)
        self.assertEqual(self.accent.animation.state(), QAbstractAnimation.Stopped)
        self.assertEqual(self.accent.geometry(), self.accent._target_rect())
        self.accent.select("settings")
        self.assertEqual(self.accent.animation.state(), QAbstractAnimation.Stopped)
        self.assertEqual(self.accent.geometry(), self.accent._target_rect())

    def test_resize_theme_hide_and_shutdown_stop_and_align(self):
        self.accent.select("notes")
        self.sidebar.resize(620, 76)
        APP.processEvents()
        self.assertEqual(self.accent.animation.state(), QAbstractAnimation.Stopped)
        self.assertEqual(self.accent.geometry(), self.accent._target_rect())
        self.assertTrue(self.sidebar.rect().contains(self.accent.geometry()))
        self.accent.select("time")
        APP.setProperty("visualTheme", "dark")
        self.accent.sync()
        self.assertEqual(self.accent._color, self.accent._page_color())
        self.assertEqual(self.accent.animation.state(), QAbstractAnimation.Stopped)
        self.accent.select("home")
        self.sidebar.hide()
        self.assertEqual(self.accent.animation.state(), QAbstractAnimation.Stopped)
        self.assertEqual(self.accent.geometry(), self.accent._target_rect())
        self.sidebar.show()
        self.assertEqual(self.accent.geometry(), self.accent._target_rect())
        self.accent.select("notes")
        self.accent.shutdown()
        self.accent.select("settings")
        self.assertEqual(self.accent.animation.state(), QAbstractAnimation.Stopped)
        self.assertTrue(self.accent.isHidden())

    def test_decoration_does_not_take_focus_or_clicks_and_keeps_checked_state(self):
        control = self.buttons["time"]
        self.assertEqual(self.accent.focusPolicy(), Qt.NoFocus)
        self.assertTrue(self.accent.testAttribute(Qt.WA_TransparentForMouseEvents))
        calls = []
        control.clicked.connect(lambda: calls.append(True))
        QTest.mouseClick(control, Qt.LeftButton, pos=QPoint(control.width() // 2, control.height() // 2))
        self.assertEqual(calls, [True])
        self.assertTrue(control.isChecked())
        self.accent.select("time", animate=False)
        self.assertTrue(control.isChecked())
        self.assertFalse(self.accent.grab().isNull())


if __name__ == "__main__":
    unittest.main()
