"""The new control finish is tactile, finite and leaves native input intact."""
import os
import sys
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QAbstractAnimation, QCoreApplication, QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import QEnterEvent, QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget
from mpsi_desktop.widgets import AnimatedButton, button
from mpsi_desktop.theme import apply_theme, palette_for
from mpsi_desktop.button_material import paint_rim, paint_sparkles

APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class ButtonMaterialTests(unittest.TestCase):
    def setUp(self):
        self.before_motion = APP.property('reducedMotion')
        self.before_theme = APP.property('visualTheme')
        APP.setProperty('reducedMotion', False)
        apply_theme(APP, 'light')
        self.errors = []
        self.before_hook = sys.excepthook
        sys.excepthook = lambda kind, value, trace: self.errors.append((kind.__name__, str(value)))
        self.host = QWidget()
        self.layout = QVBoxLayout(self.host)
        self.control = button('Commencer une séance', primary=True)
        self.control.setFixedSize(260, 48)
        self.layout.addWidget(self.control)
        self.host.show()
        APP.processEvents()
        self.control._reset_motion()

    def tearDown(self):
        self.host.close()
        self.host.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        APP.processEvents()
        sys.excepthook = self.before_hook
        APP.setProperty('reducedMotion', self.before_motion)
        apply_theme(APP, self.before_theme or 'light')
        self.assertEqual(self.errors, [])

    def enter(self):
        p = QPointF(60, 8)
        APP.sendEvent(self.control, QEnterEvent(p, p, p))

    def test_physical_rim_is_visible_at_rest_and_with_reduced_motion(self):
        for theme in ('light', 'dark'):
            apply_theme(APP, theme)
            self.control._reset_motion()
            resting = self.control.grab().toImage()
            native = QPushButton(self.control.text(), self.host)
            native.setProperty('role', 'primary')
            native.setFixedSize(self.control.size())
            native.show()
            APP.processEvents()
            # Native style and typography remain, with a distinct physical edge.
            self.assertNotEqual(native.grab().toImage(), resting)
            APP.setProperty('reducedMotion', True)
            self.assertEqual(self.control.grab().toImage(), resting)
            self.assertTrue(all(item.state() == QAbstractAnimation.Stopped
                                for item in self.control.findChildren(QAbstractAnimation)))
            APP.setProperty('reducedMotion', False)
            native.hide()
            native.deleteLater()

    def test_specular_glints_change_the_rim_without_covering_the_text(self):
        control = self.control
        control._reset_motion()
        resting = control.grab().toImage()
        control._set_sparkle(.48)
        shining = control.grab().toImage()
        self.assertNotEqual(resting, shining)
        self.assertEqual(resting.copy(12, 12, resting.width() - 24, resting.height() - 24),
                         shining.copy(12, 12, shining.width() - 24, shining.height() - 24))
        control._set_sparkle(1)
        self.assertEqual(control.grab().toImage(), resting)

    def test_press_then_release_has_a_small_overshoot_without_moving_or_reclicking(self):
        control = self.control
        bounds = control.geometry()
        calls = []
        control.clicked.connect(lambda: calls.append(True))
        center = control.rect().center()
        QTest.mousePress(control, Qt.LeftButton, pos=center)
        control.depth_animation.setCurrentTime(control.depth_animation.duration())
        self.assertEqual(control._depth, 1)
        pressed = control.grab().toImage()
        QTest.mouseRelease(control, Qt.LeftButton, pos=center)
        control.depth_animation.setCurrentTime(round(control.depth_animation.duration() * .65))
        self.assertLess(control._depth, 0)
        self.assertGreaterEqual(control._depth, -.22)
        self.assertNotEqual(control.grab().toImage(), pressed)
        self.assertEqual(calls, [True])
        self.assertEqual(control.geometry(), bounds)
        self.assertTrue(control.hitButton(center))
        self.assertIsNone(control.graphicsEffect())
        control.depth_animation.setCurrentTime(control.depth_animation.duration())
        self.assertEqual(control._depth, 0)

    def test_glints_are_one_shot_and_cancel_at_hide_disable_and_accessibility_change(self):
        for stop in (self.control.hide, lambda: self.control.setEnabled(False),
                     lambda: APP.setProperty('reducedMotion', True)):
            APP.setProperty('reducedMotion', False)
            self.control.setEnabled(True)
            self.control.show()
            self.enter()
            self.assertEqual(self.control.sparkle_animation.state(), QAbstractAnimation.Running)
            self.control.sparkle_animation.setCurrentTime(270)
            self.assertGreater(self.control._sparkle, 0)
            self.control._press_at(QPointF(70, 20))
            stop()
            self.assertEqual((self.control._sparkle, self.control._depth), (1, 0))
            for animation in self.control.findChildren(QAbstractAnimation):
                self.assertEqual(animation.state(), QAbstractAnimation.Stopped)
                self.assertEqual(animation.loopCount(), 1)
                self.assertLessEqual(animation.duration(), 700)

    def test_role_and_theme_changes_keep_glints_deterministic(self):
        for theme in ('light', 'dark'):
            apply_theme(APP, theme)
            for role in ('primary', 'secondary', 'nav', 'tab', 'danger', 'link'):
                self.control.setProperty('role', role)
                self.control._reset_motion()
                self.control._set_sparkle(.42)
                first = self.control.grab().toImage()
                self.assertEqual(first, self.control.grab().toImage(), (theme, role))
                self.assertFalse(first.isNull())

    def test_constructing_controls_inside_a_disabled_host_is_safe(self):
        self.host.setEnabled(False)
        for _ in range(8):
            control = AnimatedButton('Ouvrir', self.host)
            self.layout.addWidget(control)
            control.hide()
        APP.processEvents()

    def material_image(self, role='primary', *, accent=None, dark=False, enabled=True,
                       checked=False, hover=0.0, sparkles=False):
        image = QImage(260, 48, QImage.Format_ARGB32_Premultiplied)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        try:
            if sparkles:
                paint_sparkles(painter, QRectF(0, 0, 260, 48), role, .48,
                               dark=dark, material_accent=accent)
            else:
                paint_rim(painter, QRectF(0, 0, 260, 48), palette_for('dark' if dark else 'light'), role,
                          dark=dark, enabled=enabled, checked=checked, hover=hover,
                          material_accent=accent)
        finally:
            painter.end()
        return image

    def test_page_pigment_changes_action_inlays_without_touching_labels_or_disabled_state(self):
        for dark in (False, True):
            for role, checked in (('primary', False), ('tab', True)):
                blue = self.material_image(role, accent='#2479B4', dark=dark, checked=checked)
                green = self.material_image(role, accent='#397E61', dark=dark, checked=checked)
                self.assertNotEqual(blue, green)
                self.assertEqual(blue.copy(14, 14, 232, 20), green.copy(14, 14, 232, 20))
                self.assertEqual(self.material_image(role, accent='#2479B4', dark=dark, enabled=False, checked=checked),
                                 self.material_image(role, accent='#397E61', dark=dark, enabled=False, checked=checked))

    def test_danger_keeps_red_reflections_and_quiet_roles_have_no_permanent_inlay(self):
        for dark in (False, True):
            for sparkles in (False, True):
                red = self.material_image('danger', accent='#2479B4', dark=dark, hover=.7, sparkles=sparkles)
                self.assertEqual(red, self.material_image('danger', accent='#397E61', dark=dark,
                                                          hover=.7, sparkles=sparkles))
                self.assertTrue(any(red.pixelColor(x, y).alpha() > 20 and
                                    red.pixelColor(x, y).red() > red.pixelColor(x, y).blue() * 1.2
                                    for y in range(red.height()) for x in range(red.width())))
            for role in ('link', 'nav'):
                quiet = self.material_image(role, accent='#2479B4', dark=dark)
                self.assertEqual(quiet, self.material_image(role, accent='#397E61', dark=dark))
            fallback = self.material_image(accent=None, dark=dark)
            self.assertEqual(fallback, self.material_image(accent='invalid colour', dark=dark))


if __name__ == '__main__':
    unittest.main()
