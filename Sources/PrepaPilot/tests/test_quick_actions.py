"""Keyboard launching and search must not mutate data until an action is chosen."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from mpsi_desktop.context import AppContext
from mpsi_desktop.i18n import set_language
from mpsi_desktop.quick_actions import QuickAction, QuickActionsDialog
from mpsi_desktop.window import MainWindow


APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class QuickActionsTests(unittest.TestCase):
    def setUp(self):
        set_language('fr')
        self.temporary = tempfile.TemporaryDirectory()
        self.ctx = AppContext(Path(self.temporary.name) / 'data')
        self.ctx.db.set_setting('desktop_reduced_motion', True)
        self.dialog = QuickActionsDialog(self.ctx, [
            QuickAction('grade', 'Ajouter une note', 'Évaluation et coefficient', 'chart'),
            QuickAction('document', 'Ajouter un document', 'Bibliothèque de fichiers', 'book'),
            QuickAction('settings', 'Réglages', 'Personnaliser mon espace', 'settings'),
        ])
        self.dialog.show()
        self.dialog.activateWindow()
        APP.processEvents()

    def tearDown(self):
        self.dialog.close()
        self.dialog.deleteLater()
        APP.sendPostedEvents(None, QEvent.DeferredDelete)
        APP.processEvents()
        self.ctx.close()
        self.temporary.cleanup()
        set_language('fr')

    def test_accent_insensitive_search_accepts_multiple_terms(self):
        self.dialog.search.setText('ajouter evaluation')
        self.assertEqual(self.dialog.results.count(), 1)
        self.assertEqual(self.dialog.results.currentItem().data(Qt.UserRole), 'grade')
        self.dialog.search.setText('reglages')
        self.assertEqual(self.dialog.results.count(), 1)
        self.assertEqual(self.dialog.results.currentItem().data(Qt.UserRole), 'settings')

    def test_arrows_and_enter_launch_from_search_field(self):
        self.assertTrue(self.dialog.search.hasFocus())
        QTest.keyClick(self.dialog.search, Qt.Key_Down)
        self.assertEqual(self.dialog.results.currentRow(), 1)
        QTest.keyClick(self.dialog.search, Qt.Key_Return)
        self.assertEqual(self.dialog.result(), QDialog.Accepted)
        self.assertEqual(self.dialog.selected_key, 'document')

    def test_empty_search_never_launches_stale_selection(self):
        self.dialog.search.setText('introuvablexyz')
        self.assertEqual(self.dialog.results.count(), 0)
        self.assertTrue(self.dialog.empty.isVisible())
        self.assertFalse(self.dialog.open_button.isEnabled())
        QTest.keyClick(self.dialog.search, Qt.Key_Return)
        self.assertTrue(self.dialog.isVisible())
        self.assertIsNone(self.dialog.selected_key)
        self.dialog.search.clear()
        self.assertEqual(self.dialog.results.count(), 3)
        self.assertTrue(self.dialog.open_button.isEnabled())

    def test_escape_cancels_without_data_changes(self):
        previous = self.ctx.db._connection.total_changes
        QTest.keyClick(self.dialog.search, Qt.Key_Escape)
        self.assertFalse(self.dialog.isVisible())
        self.assertEqual(self.dialog.result(), QDialog.Rejected)
        self.assertIsNone(self.dialog.selected_key)
        self.assertEqual(self.ctx.db._connection.total_changes, previous)

    def test_exact_page_title_precedes_matches_in_descriptions(self):
        self.dialog.actions = (
            QuickAction('search', 'Rechercher', 'Documents, notes et repères'),
            QuickAction('page:documents', 'Documents', 'Bibliothèque'),
        )
        self.dialog.search.setText('documents')
        self.assertEqual(self.dialog.results.currentRow(), 0)
        self.assertEqual(self.dialog.results.currentItem().data(Qt.UserRole), 'page:documents')


class QuickActionsIntegrationTests(unittest.TestCase):
    def setUp(self):
        set_language('fr')
        self.temporary = tempfile.TemporaryDirectory()
        self.ctx = AppContext(Path(self.temporary.name) / 'data')
        self.ctx.db.set_setting('desktop_reduced_motion', True)
        self.window = MainWindow(self.ctx, show_welcome=False)
        self.window.show()
        self.window.activateWindow()
        QTest.qWait(20)

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        APP.sendPostedEvents(None, QEvent.DeferredDelete)
        APP.processEvents()
        self.ctx.close()
        self.temporary.cleanup()
        set_language('fr')

    def test_ctrl_k_opens_palette_from_a_focused_input_and_navigates(self):
        self.window.navigate('settings', animate=False)
        field = self.window.pages['settings'].name
        field.setFocus()
        def choose(dialog):
            dialog.search.setText('documents')
            dialog.activate_selected()
            return dialog.result()
        with patch.object(QuickActionsDialog, 'exec', new=choose):
            QTest.keyClick(field, Qt.Key_K, Qt.ControlModifier)
        self.assertEqual(self.window.current_key, 'documents')

    def test_command_runs_real_page_callback_only_after_acceptance(self):
        def choose(dialog):
            dialog.selected_key = 'add_grade'
            return QDialog.Accepted
        with patch.object(self.window.pages['notes'], 'add_note') as add:
            with patch.object(QuickActionsDialog, 'exec', return_value=QDialog.Rejected):
                self.window.open_quick_actions()
            add.assert_not_called()
            with patch.object(QuickActionsDialog, 'exec', new=choose):
                self.window.open_quick_actions()
            add.assert_called_once_with()
        self.assertEqual(self.window.current_key, 'notes')

    def test_active_focus_command_describes_pause_and_does_not_pause_on_open(self):
        home = self.window.pages['home']
        home.focus_session.start(None, minutes=25)
        home._sync_focus()
        def inspect(dialog):
            self.assertEqual(dialog.actions[0].title, 'Mettre la séance en pause')
            return QDialog.Rejected
        with patch.object(QuickActionsDialog, 'exec', new=inspect):
            self.window.open_quick_actions()
        self.assertEqual(home.focus_session.status, 'running')


if __name__ == '__main__':
    unittest.main()
