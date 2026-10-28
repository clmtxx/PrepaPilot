"""Interaction, accessible QLabel behaviour and bounded native illustration motion."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
import traceback
import unittest

from PySide6.QtCore import QAbstractAnimation, QEvent, QPointF, Qt
from PySide6.QtGui import QEnterEvent, QFont, QFontDatabase, QMouseEvent
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QVBoxLayout, QWidget

from mpsi_desktop.visuals import ReflectiveTitle, StudySculpture


APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)
for filename in ("segoeui.ttf", "segoeuib.ttf"):
    QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + filename)


class VisualTests(unittest.TestCase):
    def setUp(self):
        self.previous_motion = APP.property("reducedMotion")
        self.previous_theme = APP.property("visualTheme")
        APP.setProperty("reducedMotion", False)
        APP.setProperty("visualTheme", "light")
        self.errors = []
        self.old_hook = sys.excepthook
        sys.excepthook = lambda kind, value, tb: self.errors.append((str(value), "".join(traceback.format_tb(tb))))
        self.host = QWidget()
        self.host.resize(500, 400)
        layout = QVBoxLayout(self.host)
        self.title = ReflectiveTitle("Tes études. À ton rythme.")
        self.title.setFont(QFont("Segoe UI", 28, QFont.Weight.Bold))
        self.title.setWordWrap(True)
        self.sculpture = StudySculpture()
        layout.addWidget(self.title)
        layout.addWidget(self.sculpture)
        self.host.show()
        APP.processEvents()
        self.title._rest()
        self.sculpture._rest()

    def tearDown(self):
        self.host.close()
        self.host.deleteLater()
        APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        APP.processEvents()
        APP.setProperty("reducedMotion", self.previous_motion)
        APP.setProperty("visualTheme", self.previous_theme)
        sys.excepthook = self.old_hook
        self.assertEqual(self.errors, [])

    def enter_title(self):
        APP.sendEvent(self.title, QEnterEvent(QPointF(12, 12), QPointF(12, 12), QPointF(12, 12)))

    def move_sculpture(self, x, y):
        position = QPointF(x, y)
        event = QMouseEvent(QEvent.Type.MouseMove, position, position, Qt.MouseButton.NoButton,
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
        APP.sendEvent(self.sculpture, event)

    def test_title_retains_native_label_size_text_and_wrapping_contract(self):
        native = QLabel(self.title.text(), self.host)
        for label in (native, self.title):
            # The title is already shown; polish the native comparator too,
            # before setting fonts, so a previous test's application stylesheet
            # cannot change only the comparator's font on its first sizeHint.
            label.ensurePolished()
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setFont(QFont("Segoe UI", 28, QFont.Weight.Bold))
            label.setWordWrap(True)
            label.setMargin(5)
            label.setIndent(8)
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        self.assertEqual(self.title.text(), "Tes études. À ton rythme.")
        self.assertIsInstance(self.title, QLabel)
        self.assertEqual(self.title.font(), native.font())
        self.assertEqual(self.title.sizeHint(), native.sizeHint())
        self.assertEqual(self.title.minimumSizeHint(), native.minimumSizeHint())
        self.assertEqual(self.title.heightForWidth(230), native.heightForWidth(230))
        self.title.setAccessibleName("Progression des études")
        self.assertEqual(self.title.accessibleName(), "Progression des études")
        self.title.grab()

    def test_default_title_treats_user_text_as_literal_and_rich_text_is_explicit(self):
        self.assertEqual(self.title.textFormat(), Qt.TextFormat.PlainText)
        self.title.setText("<b>Camille</b>")
        literal = self.title.grab().toImage()
        self.title.setTextFormat(Qt.TextFormat.RichText)
        markup = self.title.grab().toImage()
        self.assertNotEqual(literal, markup)
        self.assertEqual(self.title.text(), "<b>Camille</b>")
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.assertEqual(literal, self.title.grab().toImage())

    def test_reflection_runs_once_and_finishes_at_static_rest(self):
        self.enter_title()
        animation = self.title.reflection_animation
        self.assertEqual(animation.state(), QAbstractAnimation.State.Running)
        self.assertEqual(animation.loopCount(), 1)
        animation.setCurrentTime(animation.duration() // 2)
        self.assertIsNotNone(self.title._reflection)
        self.title.grab()
        animation.setCurrentTime(animation.duration())
        self.assertEqual(animation.state(), QAbstractAnimation.State.Stopped)
        self.assertIsNone(self.title._reflection)

    def test_reduced_motion_stops_active_visuals_immediately_and_prevents_restart(self):
        self.enter_title()
        self.move_sculpture(self.sculpture.width(), self.sculpture.height())
        self.sculpture.parallax_animation.setCurrentTime(80)
        self.assertNotEqual(self.sculpture._offset, QPointF())
        APP.setProperty("reducedMotion", True)
        for animation in (self.title.reflection_animation, self.sculpture.parallax_animation):
            self.assertEqual(animation.state(), QAbstractAnimation.State.Stopped)
        self.assertIsNone(self.title._reflection)
        self.assertEqual(self.sculpture._offset, QPointF())
        self.enter_title()
        self.move_sculpture(1, 1)
        self.assertEqual(self.title.reflection_animation.state(), QAbstractAnimation.State.Stopped)
        self.assertEqual(self.sculpture.parallax_animation.state(), QAbstractAnimation.State.Stopped)

    def test_sculpture_motion_is_small_bounded_and_returns_to_rest(self):
        self.move_sculpture(self.sculpture.width() * 3, -200)
        animation = self.sculpture.parallax_animation
        animation.setCurrentTime(animation.duration())
        self.assertEqual(self.sculpture._offset, QPointF(1, -1))
        self.assertEqual(animation.state(), QAbstractAnimation.State.Stopped)
        APP.sendEvent(self.sculpture, QEvent(QEvent.Type.Leave))
        self.assertEqual(animation.state(), QAbstractAnimation.State.Running)
        animation.setCurrentTime(animation.duration())
        self.assertEqual(self.sculpture._offset, QPointF())
        self.assertEqual(animation.loopCount(), 1)

    def test_hide_cancels_all_work_and_reopening_is_static(self):
        self.enter_title()
        self.move_sculpture(1, 1)
        self.host.hide()
        self.assertEqual(self.title.reflection_animation.state(), QAbstractAnimation.State.Stopped)
        self.assertEqual(self.sculpture.parallax_animation.state(), QAbstractAnimation.State.Stopped)
        self.assertEqual(self.sculpture._offset, QPointF())
        self.host.show()
        APP.processEvents()
        self.assertEqual(self.sculpture.parallax_animation.state(), QAbstractAnimation.State.Stopped)

    def test_static_paint_is_repeatable_and_theme_change_repaints_title(self):
        APP.setProperty("reducedMotion", True)
        light = self.title.grab().toImage()
        self.assertEqual(light, self.title.grab().toImage())
        APP.setProperty("visualTheme", "dark")
        dark = self.title.grab().toImage()
        self.assertNotEqual(light, dark)
        self.assertEqual(self.sculpture.grab().toImage(), self.sculpture.grab().toImage())

    def test_rich_plain_multiline_and_frame_render_without_losing_label_settings(self):
        self.title.setFrameShape(QFrame.Shape.Box)
        self.title.setTextFormat(Qt.TextFormat.RichText)
        self.title.setText("<b>Un titre</b><br>Deux lignes")
        self.title.grab()
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.title.setText("Une ligne\nUne autre ligne")
        self.title.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.title.grab()
        self.assertTrue(self.title.wordWrap())
        self.assertEqual(self.title.frameShape(), QFrame.Shape.Box)

    def test_sculpture_scales_without_forcing_parent_size_or_effects(self):
        self.assertLessEqual(self.sculpture.minimumSizeHint().width(), 180)
        self.assertLessEqual(self.sculpture.minimumSizeHint().height(), 130)
        self.assertIsNone(self.sculpture.graphicsEffect())
        for width, height in ((150, 105), (330, 230), (600, 420)):
            self.sculpture.resize(width, height)
            self.assertFalse(self.sculpture.grab().isNull())
        self.assertEqual(self.sculpture.parallax_animation.state(), QAbstractAnimation.State.Stopped)


if __name__ == "__main__":
    unittest.main()
