"""Notice text, bounded reading space and neutral status survive every effect."""
import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QAbstractAnimation, QCoreApplication, QEvent, QPointF, Qt
from PySide6.QtGui import QEnterEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from mpsi_desktop.i18n import set_language
from mpsi_desktop.notice_card import NoticeCard
from mpsi_desktop.theme import apply_theme

APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class NoticeCardTests(unittest.TestCase):
    def setUp(self):
        self.old_motion = APP.property('reducedMotion')
        self.old_theme = APP.property('visualTheme')
        self.errors = []
        self.old_hook = sys.excepthook
        sys.excepthook = lambda kind, value, trace: self.errors.append((kind.__name__, str(value)))
        set_language('fr')
        APP.setProperty('reducedMotion', False)
        apply_theme(APP, 'light')
        self.host = QWidget()
        self.host.setFocusPolicy(Qt.StrongFocus)
        self.host.resize(1024, 680)
        self.card = NoticeCard(self.host)
        self.card.setText('Document ajouté.')
        self.card.fit_width(520, max_height=240)
        self.host.show()
        self.card.show()
        self.host.activateWindow()
        self.host.setFocus()
        APP.processEvents()

    def tearDown(self):
        self.host.close()
        self.host.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        APP.processEvents()
        sys.excepthook = self.old_hook
        APP.setProperty('reducedMotion', self.old_motion)
        apply_theme(APP, self.old_theme or 'light')
        self.assertEqual(self.errors, [])

    def test_plain_label_preserves_markup_line_breaks_and_copies_the_entire_message(self):
        text = '<b>Fichier introuvable</b>\n<img src="file:///private.png">\nNom exact : contrôle · ∑'
        self.card.setText(text)
        self.assertIsInstance(self.card.message, QLabel)
        self.assertEqual(self.card.message.textFormat(), Qt.PlainText)
        self.assertEqual(self.card.heading.textFormat(), Qt.PlainText)
        self.assertEqual(self.card.text(), text)
        self.assertEqual(self.card.message.text(), text)
        self.assertEqual(self.card.accessibleName(), text)
        with patch('mpsi_desktop.notice_card.QApplication.clipboard') as clipboard:
            QTest.mouseClick(self.card.copy_button, Qt.LeftButton)
            clipboard.return_value.setText.assert_called_once_with(text)
        self.card.message.setSelection(0, 3)
        self.assertEqual(self.card.message.selectedText(), '<b>')
        self.assertTrue(self.card.message.textInteractionFlags() & Qt.TextSelectableByKeyboard)

    def test_status_is_explicit_and_never_guessed_from_message_wording(self):
        for message in ('Erreur de connexion.', 'Succès : tout est terminé.', 'Ce document a été supprimé.'):
            self.card.setText(message)
            self.assertEqual(self.card.kind, 'info')
            self.assertEqual(self.card.heading.text(), 'Information')
        images = []
        for kind, title in (('info', 'Information'), ('warning', 'À vérifier'),
                            ('error', 'Erreur'), ('success', 'Action confirmée')):
            self.card.setText('Message identique.', kind=kind)
            self.assertEqual(self.card.heading.text(), title)
            self.assertEqual(self.card.orb.kind, kind)
            images.append(self.card.orb.grab().toImage())
        for left in range(len(images)):
            for right in range(left + 1, len(images)):
                self.assertNotEqual(images[left], images[right])
        self.card.setText('Même contenu.', kind='unknown', title='<b>Titre littéral</b>')
        self.assertEqual(self.card.kind, 'info')
        self.assertEqual(self.card.heading.text(), '<b>Titre littéral</b>')

    def test_short_notice_is_compact_and_long_paragraphs_scroll_without_hiding_close(self):
        self.assertLessEqual(self.card.height(), 80)
        self.assertEqual(self.card.orb.size().width(), 32)
        text = '\n'.join(f'Ligne {i} : vérifie les fichiers et leur dossier avant de continuer.' for i in range(90))
        self.card.setText(text)
        self.card.fit_width(520, max_height=240)
        APP.processEvents()
        self.assertLessEqual(self.card.height(), 240)
        self.assertGreater(self.card.message_area.verticalScrollBar().maximum(), 0)
        self.assertEqual(self.card.message_area.horizontalScrollBar().maximum(), 0)
        self.card.message_area.verticalScrollBar().setValue(self.card.message_area.verticalScrollBar().maximum())
        self.assertEqual(self.card.text(), text)
        for control in (self.card.close_button, self.card.copy_button):
            point = control.mapTo(self.card, control.rect().bottomRight())
            self.assertTrue(self.card.rect().contains(point))
        self.card.copy_message()
        self.assertEqual(QApplication.clipboard().text(), text)

    def test_resizing_recalculates_wrapping_and_short_messages_recover_compact_height(self):
        self.card.setText('Un texte de contrôle avec des mots et des retours à la ligne. ' * 24)
        for width, cap in ((360, 180), (620, 240), (420, 160)):
            self.card.fit_width(width, max_height=cap)
            APP.processEvents()
            self.assertEqual(self.card.width(), width)
            self.assertLessEqual(self.card.height(), cap)
            self.assertEqual(self.card.message_area.horizontalScrollBar().maximum(), 0)
            self.assertTrue(self.card.close_button.isVisible())
        self.card.setText('Fichier conservé.')
        self.card.fit_width(420, max_height=160)
        APP.processEvents()
        self.assertLessEqual(self.card.height(), 80)
        self.assertEqual(self.card.message_area.verticalScrollBar().maximum(), 0)

    def test_unbroken_long_identifiers_remain_readable_and_copyable(self):
        text = 'Identifiant :\n' + 'ABCD1234' * 120
        self.card.setText(text)
        self.card.fit_width(360, max_height=180)
        APP.processEvents()
        self.assertLessEqual(self.card.height(), 180)
        self.assertGreater(self.card.message_area.horizontalScrollBar().maximum(), 0)
        self.card.copy_message()
        self.assertEqual(QApplication.clipboard().text(), text)
        self.assertTrue(self.card.rect().contains(self.card.close_button.mapTo(self.card, self.card.close_button.rect().center())))

    def test_dismiss_button_supports_keyboard_focus_and_one_native_activation(self):
        dismissed = []
        self.card.dismissed.connect(lambda: dismissed.append(True))
        self.card.close_button.setFocus()
        APP.processEvents()
        self.assertTrue(self.card.close_button.hasFocus())
        QTest.keyClick(self.card.close_button, Qt.Key_Space)
        self.assertEqual(dismissed, [True])

    def test_hover_and_keyboard_reading_signal_interaction_without_an_idle_poll(self):
        changes = []
        self.card.interaction_changed.connect(changes.append)
        self.card._pointer_inside = False
        self.host.setFocus()
        APP.processEvents()
        self.card._sync_interaction()
        changes.clear()
        point = QPointF(12, 12)
        APP.sendEvent(self.card, QEnterEvent(point, point, point))
        self.assertEqual(changes, [True])
        APP.sendEvent(self.card, QEvent(QEvent.Leave))
        self.assertEqual(changes, [True, False])
        self.card.copy_button.setFocus()
        APP.processEvents()
        self.assertTrue(changes[-1])
        self.host.setFocus()
        APP.processEvents()
        self.assertFalse(changes[-1])
        self.assertFalse(self.card._interaction_timer.isActive())

    def test_motion_is_finite_and_stops_immediately_when_hidden_or_reduced(self):
        self.card.set_duration(9000)
        self.card.restart()
        self.assertEqual(self.card.lifetime_animation.duration(), 9000)
        self.assertEqual(self.card.orb.animation.duration(), 520)
        for animation in self.card.findChildren(QAbstractAnimation):
            self.assertEqual(animation.loopCount(), 1)
            animation.setCurrentTime(animation.duration())
            self.assertEqual(animation.state(), QAbstractAnimation.Stopped)
        self.card.restart()
        self.card.orb.animation.setCurrentTime(200)
        APP.setProperty('reducedMotion', True)
        self.assertEqual(self.card._remaining, 1.)
        self.assertTrue(all(animation.state() == QAbstractAnimation.Stopped for animation in self.card.findChildren(QAbstractAnimation)))
        self.card.restart()
        self.assertTrue(all(animation.state() == QAbstractAnimation.Stopped for animation in self.card.findChildren(QAbstractAnimation)))
        APP.setProperty('reducedMotion', False)
        self.card.restart()
        self.card.hide()
        self.assertTrue(all(animation.state() == QAbstractAnimation.Stopped for animation in self.card.findChildren(QAbstractAnimation)))

    def test_themes_and_rail_bounds_do_not_change_text_or_layout(self):
        text = self.card.text()
        for theme in ('light', 'dark'):
            self.card.apply_theme(theme)
            for value, expected in ((-1, 0.), (.4, .4), (2, 1.), (float('nan'), 1.)):
                self.card.set_remaining(value)
                self.assertEqual(self.card._remaining, expected)
                self.assertFalse(self.card.grab().isNull())
                self.assertEqual(self.card.text(), text)


if __name__ == '__main__':
    unittest.main()
