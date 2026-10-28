"""Page movement and reading feedback preserve native input and user drafts."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest

from PySide6.QtCore import QAbstractAnimation, QEvent, QPoint, QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QVBoxLayout, QWidget
from mpsi_desktop.context import AppContext
from mpsi_desktop.theme import apply_theme
from mpsi_desktop.window import MainWindow, notice_duration

APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class InterfaceFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ctx = AppContext(Path(self.temp.name) / 'data')
        self.ctx.db.set_setting('desktop_reduced_motion', False)
        self.window = MainWindow(self.ctx, show_welcome=False)
        self.window.resize(1024, 680)
        self.window.show()
        APP.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        APP.sendPostedEvents(None, QEvent.DeferredDelete)
        APP.processEvents()
        self.ctx.close()
        self.temp.cleanup()
        APP.setProperty('reducedMotion', False)

    def test_notice_lifetime_adapts_and_pauses_while_reading(self):
        short = 'Document ajouté.'
        long = 'Ce message contient des indications à lire attentivement. ' * 25
        self.assertGreater(notice_duration(long), notice_duration(short))
        self.assertLessEqual(notice_duration(long), 12000)
        self.assertGreaterEqual(notice_duration(short), 4200)
        self.window.notify(long)
        self.assertEqual(self.window.toast.text(), long)
        self.assertLessEqual(self.window.toast.height(), 320)
        self.window.hold_notice(True)
        remaining = self.window._notice_remaining_ms
        self.assertFalse(self.window.toast_timer.isActive())
        self.assertEqual(self.window.toast.lifetime_animation.state(), QAbstractAnimation.Paused)
        QTest.qWait(25)
        self.assertEqual(self.window._notice_remaining_ms, remaining)
        self.window.hold_notice(False)
        self.assertTrue(self.window.toast_timer.isActive())
        self.assertLessEqual(self.window.toast_timer.remainingTime(), remaining)

    def test_notifications_remain_plain_explicit_and_can_be_dismissed_while_held(self):
        text = '<b>Texte personnel</b> & détails'
        self.ctx.notice.emit(text)
        self.assertEqual(self.window.toast.text(), text)
        self.assertEqual(self.window.toast.message.textFormat(), Qt.PlainText)
        self.window.notify(text, kind='warning')
        self.assertEqual(self.window.toast.heading.text(), 'À vérifier')
        self.window.hold_notice(True)
        self.window.dismiss_notice()
        self.window.hold_notice(False)
        self.assertFalse(self.window.toast_timer.isActive())
        self.window.toast_exit.setCurrentTime(self.window.toast_exit.duration())
        self.assertFalse(self.window.toast.isVisible())

    def test_rapid_navigation_starts_from_visible_frame_and_preserves_draft(self):
        settings = self.window.pages['settings']
        settings.name.setText('Brouillon à conserver')
        self.window.navigate('notes')
        layer = self.window.transition
        layer.animation.pause()
        layer.advance(.45)
        visible = layer.capture(layer).toImage()
        self.window.navigate('documents')
        layer.animation.pause()
        self.assertEqual(layer.before.toImage(), visible)
        self.assertEqual(settings.name.text(), 'Brouillon à conserver')
        self.assertEqual(self.window.current_key, 'documents')

    def test_shortcuts_are_discoverable_without_changing_navigation_order(self):
        for index, key in enumerate(self.window.pages, 1):
            self.assertIn(f'Ctrl+{index}', self.window.nav[key][0].toolTip())

    def test_reducing_motion_finishes_a_notice_already_being_dismissed(self):
        self.window.notify('Message à fermer')
        self.window.dismiss_notice()
        self.assertEqual(self.window.toast_exit.state(), QAbstractAnimation.Running)
        self.ctx.db.set_setting('desktop_reduced_motion', True)
        self.ctx.mark_changed('profile')
        self.assertFalse(self.window.toast.isVisible())
        self.assertFalse(self.window.toast_timer.isActive())

    def test_transition_bounds_follow_persistent_session_controls(self):
        home = self.window.pages['home']
        home.focus_session.start('maths', minutes=25)
        home._sync_focus()
        self.window.navigate('notes')
        layer = self.window.transition
        layer.animation.pause()
        expected = QRect(self.window.stack.mapTo(self.window.central, QPoint()), self.window.stack.size())
        self.assertEqual(layer.geometry(), expected)
        self.assertTrue(self.window.focus_bar.isVisible())
        bar = QRect(self.window.focus_bar.mapTo(self.window.central, QPoint()), self.window.focus_bar.size())
        self.assertFalse(expected.intersects(bar))
        self.assertEqual(home.focus_session.status, 'running')

    def test_background_notice_does_not_take_typing_focus(self):
        self.window.navigate('settings', animate=False)
        field = self.window.pages['settings'].name
        field.setText('Brouillon')
        field.setFocus(Qt.OtherFocusReason)
        APP.processEvents()
        self.assertTrue(field.hasFocus())
        self.window.notify('Un document vient d’être ajouté.')
        APP.processEvents()
        self.assertTrue(field.hasFocus())
        QTest.keyClicks(field, 'X')
        self.assertEqual(field.text(), 'BrouillonX')


class NativeFocusFeedbackTests(unittest.TestCase):
    def test_focus_changes_material_without_moving_fields_or_editing_text(self):
        for theme in ('light', 'dark'):
            apply_theme(APP, theme)
            host = QWidget()
            layout = QVBoxLayout(host)
            field, other = QLineEdit('Chapitre 4 · Brouillon'), QLineEdit('Autre champ')
            layout.addWidget(field)
            layout.addWidget(other)
            host.resize(420, 180)
            host.show()
            host.activateWindow()
            other.setFocus()
            APP.processEvents()
            geometry, contents = field.geometry(), field.contentsRect()
            before = field.grab().toImage()
            field.setFocus(Qt.TabFocusReason)
            APP.processEvents()
            self.assertTrue(field.hasFocus())
            self.assertEqual(field.geometry(), geometry)
            self.assertEqual(field.contentsRect(), contents)
            self.assertEqual(field.text(), 'Chapitre 4 · Brouillon')
            self.assertNotEqual(field.grab().toImage(), before)
            host.close()
            host.deleteLater()
            APP.sendPostedEvents(None, QEvent.DeferredDelete)
        apply_theme(APP, 'light')


if __name__ == '__main__':
    unittest.main()
