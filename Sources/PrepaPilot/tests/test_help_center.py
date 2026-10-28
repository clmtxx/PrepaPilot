"""Offline help uses real destinations and copies no personal application data."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path
from string import Formatter
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLabel

from mpsi_desktop import __version__
from mpsi_desktop.context import AppContext
from mpsi_desktop.help_center import HelpCenterDialog, technical_summary
from mpsi_desktop.i18n import set_language, tr
from mpsi_desktop.translations_help import EN


APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class HelpCenterTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.ctx = AppContext(Path(self.temporary.name) / 'private-directory')
        self.ctx.db.set_setting('desktop_reduced_motion', True)
        self.calls = []
        self.dialog = HelpCenterDialog(self.ctx, self.navigate)
        self.dialog.show()
        self.dialog.activateWindow()
        APP.processEvents()

    def navigate(self, key):
        self.calls.append((key, self.dialog.isVisible(), self.dialog.result()))

    def tearDown(self):
        self.dialog.close()
        self.dialog.deleteLater()
        APP.sendPostedEvents(None, QEvent.DeferredDelete)
        APP.processEvents()
        self.ctx.close()
        self.temporary.cleanup()
        QApplication.clipboard().clear()
        set_language('fr')

    def test_navigation_closes_help_before_opening_real_space(self):
        QTest.mouseClick(self.dialog.destination_buttons['documents'], Qt.LeftButton)
        self.assertEqual(self.calls, [('documents', False, QDialog.Accepted)])

    def test_help_is_read_only_and_escape_cancels(self):
        before = self.ctx.db._connection.total_changes
        for index in range(self.dialog.tabs.count()):
            self.dialog.tabs.setCurrentIndex(index)
            APP.processEvents()
        QTest.keyClick(self.dialog, Qt.Key_Escape)
        self.assertEqual(self.dialog.result(), QDialog.Rejected)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.ctx.db._connection.total_changes, before)

    def test_support_clipboard_whitelists_five_technical_fields(self):
        self.ctx.db.set_setting('desktop_name', 'NOM-PRIVE-NE-PAS-COPIER')
        self.ctx.db.remember('secret', 'CONTENU-PRIVE-NE-PAS-COPIER')
        with patch.object(self.ctx.db, '_rows', side_effect=AssertionError('No database access expected')):
            expected = technical_summary(self.ctx)
            self.dialog.copy_technical_summary()
        self.assertEqual(QApplication.clipboard().text(), expected)
        self.assertEqual(len(expected.splitlines()), 5)
        self.assertIn(f'PrépaPilot {__version__}', expected)
        self.assertNotIn('NOM-PRIVE', expected)
        self.assertNotIn('CONTENU-PRIVE', expected)
        self.assertNotIn(self.temporary.name, expected)
        self.assertTrue(self.dialog.copy_status.text())

    def test_every_help_page_scrolls_without_horizontal_overflow_at_small_size(self):
        self.dialog.resize(600, 440)
        for index, scroll in enumerate(self.dialog.pages.values()):
            self.dialog.tabs.setCurrentIndex(index)
            APP.processEvents()
            state = (self.dialog.tabs.tabText(index), scroll.widget().width(),
                     scroll.viewport().width(), APP.font().family())
            self.assertEqual(scroll.horizontalScrollBar().maximum(), 0, state)
            self.assertLessEqual(scroll.widget().width(), scroll.viewport().width(), state)
        labels = [label.text() for label in self.dialog.findChildren(QLabel)]
        for shortcut in ('Ctrl+1', 'Ctrl+2', 'Ctrl+3', 'Ctrl+4', 'Ctrl+5', 'Ctrl+6', 'Ctrl+7', 'Ctrl+N', 'Ctrl+K', 'Ctrl+F', 'F1', 'F11'):
            self.assertIn(shortcut, labels)

    def test_help_translation_preserves_all_format_fields(self):
        formatter = Formatter()
        for source, target in EN.items():
            with self.subTest(source=source):
                fields = lambda text: {name for _, name, _, _ in formatter.parse(text) if name is not None}
                self.assertEqual(fields(source), fields(target))

    def test_about_and_fullscreen_copy_are_translated(self):
        set_language('en')
        self.assertEqual(tr('Quitter le plein écran'), 'Exit full screen')
        self.assertEqual(tr('Version {version}', version=__version__), f'Version {__version__}')
        self.assertEqual(tr('Un espace pour organiser tes études, retrouver tes documents et suivre tes progrès à ton rythme.'),
                         'A space to organise your studies, find your documents and follow your progress at your own pace.')


if __name__ == '__main__':
    unittest.main()
