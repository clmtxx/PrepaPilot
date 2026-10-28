"""Native widget input, bounded feedback and live accessibility preferences."""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QAbstractAnimation, QCoreApplication, QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QEnterEvent, QKeyEvent, QMouseEvent, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
from mpsi_desktop.widgets import (
    AnimatedDialog, Card, _PreferenceObserver, _RowFeedback,
    animate_table_row, button, motion_enabled, scroll_page,
)

APP = QApplication.instance() or QApplication([])


def enter(widget):
    point = QPointF(8, 8)
    APP.sendEvent(widget, QEnterEvent(point, point, point))


class WidgetMotionTests(unittest.TestCase):
    def setUp(self):
        self.previous_motion = APP.property('reducedMotion')
        self.previous_theme = APP.property('visualTheme')
        APP.setProperty('reducedMotion', False)
        APP.setProperty('visualTheme', 'light')
        self.errors = []
        self.previous_hook = sys.excepthook
        sys.excepthook = lambda kind, error, traceback: self.errors.append((kind.__name__, str(error)))
        self.host = QWidget()
        self.host.resize(640, 500)
        self.layout = QVBoxLayout(self.host)
        self.host.show()

    def tearDown(self):
        self.host.close()
        self.host.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        APP.processEvents()
        APP.setProperty('reducedMotion', self.previous_motion)
        APP.setProperty('visualTheme', self.previous_theme)
        sys.excepthook = self.previous_hook
        self.assertEqual(self.errors, [])

    def add_button(self, primary=True):
        control = button('Ajouter une note', primary=primary)
        self.layout.addWidget(control)
        APP.processEvents()
        control._reset_motion()
        return control

    def test_mouse_space_and_disabled_input_keep_one_native_activation(self):
        control = self.add_button()
        calls = []
        control.clicked.connect(lambda: calls.append(True))
        bounds = control.geometry()
        position = QPoint(12, control.height() // 2)
        QTest.mouseClick(control, Qt.LeftButton, pos=position)
        self.assertEqual(calls, [True])
        self.assertEqual(control._origin, QPointF(position))
        self.assertEqual(control.press_animation.state(), QAbstractAnimation.Running)
        control.setFocus()
        QTest.keyClick(control, Qt.Key_Space)
        self.assertEqual(calls, [True, True])
        self.assertEqual(control._origin, QPointF(control.rect().center()))
        self.assertEqual(control.geometry(), bounds)
        self.assertTrue(control.hitButton(position))
        control.setEnabled(False)
        QTest.mouseClick(control, Qt.LeftButton, pos=position)
        QTest.keyClick(control, Qt.Key_Space)
        enter(control)
        self.assertEqual(calls, [True, True])
        self.assertTrue(all(animation.state() == QAbstractAnimation.Stopped for animation in control.findChildren(QAbstractAnimation)))
        self.assertEqual((control._hover, control._ripple, control._sheen), (0.0, 1.0, 1.0))

    def test_default_dialog_return_uses_native_button_without_changing_layout(self):
        dialog = AnimatedDialog(self.host)
        layout = QVBoxLayout(dialog)
        control = button('Enregistrer', primary=True)
        layout.addWidget(control)
        control.setDefault(True)
        calls = []
        control.clicked.connect(lambda: calls.append(True))
        dialog.show()
        APP.processEvents()
        bounds = control.geometry()
        control.setFocus()
        QTest.keyClick(control, Qt.Key_Return)
        self.assertEqual(calls, [True])
        self.assertEqual(control.geometry(), bounds)
        self.assertEqual(control.press_animation.state(), QAbstractAnimation.Running)
        dialog.hide()
        self.assertEqual(dialog.windowOpacity(), 1.0)
        self.assertEqual(dialog._entrance.state(), QAbstractAnimation.Stopped)
        self.assertEqual(control.press_animation.state(), QAbstractAnimation.Stopped)

    def test_primary_sheen_is_one_shot_and_all_feedback_has_finite_duration(self):
        primary = self.add_button()
        secondary = self.add_button(primary=False)
        enter(primary)
        enter(secondary)
        self.assertEqual(primary.sheen_animation.state(), QAbstractAnimation.Running)
        self.assertEqual(secondary.sheen_animation.state(), QAbstractAnimation.Stopped)
        primary._press_at(QPointF(12, 20))
        for animation in primary.findChildren(QAbstractAnimation):
            self.assertEqual(animation.loopCount(), 1)
            self.assertGreater(animation.duration(), 0)
            self.assertLessEqual(animation.duration(), 700)
            animation.setCurrentTime(animation.duration())
            self.assertEqual(animation.state(), QAbstractAnimation.Stopped)
        self.assertEqual(primary._ripple, 1.0)
        self.assertEqual(primary._sheen, 1.0)
        APP.sendEvent(primary, QEvent(QEvent.Leave))
        primary.hover_animation.setCurrentTime(primary.hover_animation.duration())
        self.assertEqual(primary._hover, 0.0)

    def test_auto_repeat_and_right_click_do_not_start_extra_pulses(self):
        control = self.add_button()
        QTest.mouseClick(control, Qt.RightButton)
        self.assertEqual(control.press_animation.state(), QAbstractAnimation.Stopped)
        repeated = QKeyEvent(QEvent.KeyPress, Qt.Key_Space, Qt.NoModifier, ' ', True, 2)
        APP.sendEvent(control, repeated)
        self.assertEqual(control.press_animation.state(), QAbstractAnimation.Stopped)

    def test_pointer_lens_is_bounded_finite_and_keeps_native_hit_target(self):
        control = self.add_button()
        bounds = control.geometry()
        enter(control)
        control.hover_animation.setCurrentTime(control.hover_animation.duration())
        control.sheen_animation.setCurrentTime(control.sheen_animation.duration())
        control.sparkle_animation.setCurrentTime(control.sparkle_animation.duration())
        animations = control.findChildren(QAbstractAnimation)
        images = []
        for position in (QPointF(-120, -50), QPointF(control.width() + 120, control.height() + 50)):
            event = QMouseEvent(QEvent.MouseMove, position,
                                QPointF(control.mapToGlobal(position.toPoint())),
                                Qt.NoButton, Qt.NoButton, Qt.NoModifier)
            APP.sendEvent(control, event)
            self.assertEqual(control.light_animation.state(), QAbstractAnimation.Running)
            control.light_animation.setCurrentTime(control.light_animation.duration())
            self.assertEqual(control.light_animation.state(), QAbstractAnimation.Stopped)
            self.assertGreaterEqual(control._light.x(), 0.15)
            self.assertLessEqual(control._light.x(), 0.85)
            self.assertGreaterEqual(control._light.y(), 0.2)
            self.assertLessEqual(control._light.y(), 0.8)
            images.append(control.grab().toImage())
        self.assertNotEqual(images[0], images[1])
        self.assertEqual(control.geometry(), bounds)
        self.assertTrue(control.hitButton(control.rect().center()))
        self.assertEqual(control.findChildren(QAbstractAnimation), animations)
        self.assertTrue(all(animation.state() == QAbstractAnimation.Stopped for animation in animations))
        self.assertEqual(control.light_animation.loopCount(), 1)
        self.assertLessEqual(control.light_animation.duration(), 180)

    def test_lens_stops_on_leave_hide_disable_and_live_reduced_motion(self):
        control = self.add_button()
        enter(control)
        APP.sendEvent(control, QEvent(QEvent.Leave))
        self.assertEqual(control.light_animation.state(), QAbstractAnimation.Stopped)
        for stop in (control.hide, lambda: control.setEnabled(False),
                     lambda: APP.setProperty('reducedMotion', True)):
            control.show()
            control.setEnabled(True)
            APP.setProperty('reducedMotion', False)
            enter(control)
            control.light_animation.setCurrentTime(60)
            self.assertNotEqual(control._light, QPointF(0.5, 0.2))
            stop()
            self.assertEqual(control._light, QPointF(0.5, 0.2))
            self.assertTrue(all(animation.state() == QAbstractAnimation.Stopped
                                for animation in control.findChildren(QAbstractAnimation)))
        control._track_light(QPointF(control.width(), control.height()))
        self.assertEqual(control.light_animation.state(), QAbstractAnimation.Stopped)

    def test_bevel_and_press_are_visible_in_both_themes_without_layout_effects(self):
        control = self.add_button()
        bounds = control.geometry()
        for theme in ('light', 'dark'):
            APP.setProperty('visualTheme', theme)
            for role in ('primary', 'secondary', 'nav', 'danger', 'link'):
                control.setProperty('role', role)
                control._reset_motion()
                resting = control.grab().toImage()
                enter(control)
                control.hover_animation.setCurrentTime(control.hover_animation.duration())
                control.sheen_animation.setCurrentTime(control.sheen_animation.duration())
                control.light_animation.setCurrentTime(control.light_animation.duration())
                hovered = control.grab().toImage()
                self.assertNotEqual(resting, hovered, (theme, role))
                control._press_at(QPointF(control.rect().center()))
                control.press_animation.setCurrentTime(95)
                pressed = control.grab().toImage()
                self.assertNotEqual(hovered, pressed, (theme, role))
                self.assertEqual(control.geometry(), bounds)
                self.assertIsNone(control.graphicsEffect())

    def test_reduced_motion_stops_and_resets_immediately_without_processing_events(self):
        control = self.add_button()
        card = Card()
        self.layout.addWidget(card)
        APP.processEvents()
        enter(control)
        enter(card)
        control._press_at(QPointF(14, 20))
        control.hover_animation.setCurrentTime(70)
        control.sheen_animation.setCurrentTime(120)
        control.press_animation.setCurrentTime(80)
        card.hover_animation.setCurrentTime(90)
        self.assertGreater(card._hover, 0)
        APP.setProperty('reducedMotion', True)
        self.assertEqual((control._hover, control._ripple, control._sheen), (0.0, 1.0, 1.0))
        self.assertEqual(card._hover, 0.0)
        self.assertTrue(all(animation.state() == QAbstractAnimation.Stopped for animation in self.host.findChildren(QAbstractAnimation)))
        enter(control)
        enter(card)
        QTest.mouseClick(control, Qt.LeftButton)
        self.assertTrue(all(animation.state() == QAbstractAnimation.Stopped for animation in self.host.findChildren(QAbstractAnimation)))
        APP.setProperty('reducedMotion', False)
        self.assertEqual(control.sheen_animation.state(), QAbstractAnimation.Stopped)
        enter(control)
        self.assertEqual(control.sheen_animation.state(), QAbstractAnimation.Running)

    def test_cards_keep_child_input_layout_and_paint_in_both_themes_without_effect(self):
        card = Card()
        child = button('Ouvrir le document')
        card.body.addWidget(QLabel('Mes documents'))
        card.body.addWidget(child)
        self.layout.addWidget(card)
        APP.processEvents()
        initial_geometry, margins = card.geometry(), card.body.contentsMargins()
        clicks = []
        child.clicked.connect(lambda: clicks.append(True))
        for theme in ('light', 'dark'):
            APP.setProperty('visualTheme', theme)
            enter(card)
            card.hover_animation.setCurrentTime(110)
            enter(child)
            child._press_at(QPointF(child.rect().center()))
            child.press_animation.setCurrentTime(90)
            self.assertFalse(card.grab().isNull())
            self.assertFalse(child.grab().isNull())
            QTest.mouseClick(child, Qt.LeftButton)
        self.assertEqual(clicks, [True, True])
        self.assertEqual(card.geometry(), initial_geometry)
        self.assertEqual(card.body.contentsMargins(), margins)
        self.assertIsNone(card.graphicsEffect())
        self.assertLessEqual(card.hover_animation.duration(), 300)
        self.assertEqual(card.hover_animation.loopCount(), 1)
        card.hide()
        self.assertEqual(card.hover_animation.state(), QAbstractAnimation.Stopped)
        self.assertEqual(card._hover, 0)

    def test_one_shared_observer_handles_deletion_and_does_not_restart_on_theme_change(self):
        controls = [self.add_button() for _ in range(12)]
        observers = APP.findChildren(_PreferenceObserver)
        self.assertEqual(len(observers), 1)
        dead = controls.pop()
        dead.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        APP.setProperty('visualTheme', 'dark')
        self.assertNotIn(dead, observers[0].widgets)
        self.assertTrue(all(control.press_animation.state() == QAbstractAnimation.Stopped for control in controls))
        APP.setProperty('reducedMotion', True)
        self.assertEqual(len(APP.findChildren(_PreferenceObserver)), 1)

    def test_reduced_motion_cancels_active_row_feedback_and_overrides_context(self):
        context = SimpleNamespace(db=SimpleNamespace(get_setting=lambda *_: False))
        table = QTableWidget(1, 1)
        item = QTableWidgetItem('Nouvelle note')
        item.setData(Qt.UserRole, 1)
        table.setItem(0, 0, item)
        self.layout.addWidget(table)
        APP.processEvents()
        animate_table_row(table, 0, context)
        feedback = table.findChildren(_RowFeedback)[0]
        self.assertEqual(feedback.animation.state(), QAbstractAnimation.Running)
        animate_table_row(table, 0, context)
        self.assertEqual(feedback.animation.state(), QAbstractAnimation.Stopped)
        self.assertFalse(feedback.isVisible())
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.assertEqual(len(table.findChildren(_RowFeedback)), 1)
        feedback = table.findChildren(_RowFeedback)[0]
        table.hide()
        self.assertEqual(feedback.animation.state(), QAbstractAnimation.Stopped)
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.assertEqual(table.findChildren(_RowFeedback), [])
        table.show()
        animate_table_row(table, 0, context)
        feedback = table.findChildren(_RowFeedback)[0]
        APP.setProperty('reducedMotion', True)
        self.assertFalse(motion_enabled(context))
        self.assertEqual(feedback.animation.state(), QAbstractAnimation.Stopped)
        self.assertFalse(feedback.isVisible())
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        animate_table_row(table, 0, context)
        self.assertEqual(table.findChildren(_RowFeedback), [])

    def test_row_feedback_repaints_only_the_row_and_never_reads_database_per_frame(self):
        get_setting = Mock(return_value=False)
        context = SimpleNamespace(db=SimpleNamespace(get_setting=get_setting))
        table = QTableWidget(20, 1)
        item = QTableWidgetItem('Nouvelle note')
        item.setData(Qt.UserRole, 1)
        table.setItem(0, 0, item)
        self.layout.addWidget(table)
        APP.processEvents()
        animate_table_row(table, 0, context)
        feedback = table.findChildren(_RowFeedback)[0]
        get_setting.reset_mock()
        for elapsed in (100, 200, 300):
            feedback.animation.setCurrentTime(elapsed)
            self.assertFalse(feedback.grab().isNull())
        get_setting.assert_not_called()
        self.assertEqual(feedback.height(), table.visualItemRect(item).height())
        self.assertLess(feedback.height(), table.viewport().height())

    def scroll_area(self):
        content = QWidget()
        content.setMinimumHeight(3000)
        area = scroll_page(content)
        self.layout.addWidget(area)
        APP.processEvents()
        return area

    def wheel(self, area, *, pixels=None, phase=Qt.NoScrollPhase):
        viewport = area.viewport()
        event = QWheelEvent(QPointF(20, 20), QPointF(viewport.mapToGlobal(QPoint(20, 20))),
                            pixels or QPoint(), QPoint(0, -120), Qt.NoButton,
                            Qt.NoModifier, phase, False)
        APP.sendEvent(viewport, event)
        return event

    def test_mouse_wheel_animation_accumulates_and_preserves_exact_destination(self):
        area = self.scroll_area()
        bar = area.verticalScrollBar()
        step = APP.wheelScrollLines() * bar.singleStep()
        self.wheel(area)
        self.assertEqual(area.scroll_animation.state(), QAbstractAnimation.Running)
        area.scroll_animation.setCurrentTime(60)
        self.assertGreater(bar.value(), 0)
        self.assertLess(bar.value(), step)
        self.wheel(area)
        area.scroll_animation.setCurrentTime(area.scroll_animation.duration())
        self.assertEqual(bar.value(), step * 2)
        self.assertEqual(area.scroll_animation.state(), QAbstractAnimation.Stopped)

    def test_native_scroll_input_and_motion_preferences_interrupt_wheel_easing(self):
        area = self.scroll_area()
        bar = area.verticalScrollBar()
        self.wheel(area)
        bar.setValue(250)
        self.assertEqual(area.scroll_animation.state(), QAbstractAnimation.Stopped)
        self.assertEqual(bar.value(), 250)
        self.wheel(area)
        self.wheel(area, pixels=QPoint(0, -20), phase=Qt.ScrollUpdate)
        self.assertEqual(area.scroll_animation.state(), QAbstractAnimation.Stopped)
        self.wheel(area)
        APP.setProperty('reducedMotion', True)
        self.assertEqual(area.scroll_animation.state(), QAbstractAnimation.Stopped)
        self.wheel(area)
        self.assertEqual(area.scroll_animation.state(), QAbstractAnimation.Stopped)
        APP.setProperty('reducedMotion', False)
        self.wheel(area)
        area.hide()
        self.assertEqual(area.scroll_animation.state(), QAbstractAnimation.Stopped)


if __name__ == '__main__':
    unittest.main()
