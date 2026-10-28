"""Cross-page user journeys on disposable data, including interrupted edits."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path
import random
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication, QDialog
from shiboken6 import isValid

from mpsi_desktop.context import AppContext
from mpsi_desktop.i18n import set_language
from mpsi_desktop.notes import GradeDialog
from mpsi_desktop.window import MainWindow

APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class AuditUserJourneys(unittest.TestCase):
    def setUp(self):
        set_language('fr')
        self.temp = tempfile.TemporaryDirectory(prefix='audit-ui-')
        self.ctx = AppContext(Path(self.temp.name) / 'data')
        self.ctx.db.set_setting('desktop_reduced_motion', True)
        self.errors = []
        self.old_hook = sys.excepthook
        sys.excepthook = lambda kind, value, tb: self.errors.append((kind.__name__, str(value)))
        self.windows = [MainWindow(self.ctx, show_welcome=False)]
        self.window = self.windows[0]
        self.window.show()
        APP.processEvents()

    def tearDown(self):
        for window in reversed(self.windows):
            if isValid(window):
                window.close()
                window.deleteLater()
        APP.sendPostedEvents(None, QEvent.DeferredDelete)
        APP.processEvents()
        self.ctx.close()
        self.temp.cleanup()
        sys.excepthook = self.old_hook
        set_language('fr')
        self.assertEqual(self.errors, [])

    def test_unsaved_edits_and_running_session_survive_repeated_language_changes(self):
        title = 'Idée <personnelle> & méthode 🧭'
        content = 'Première ligne\nDeuxième ligne : ∑, 中文, العربية.'
        memory = self.window.pages['memory']
        memory.key_input.setText(title)
        memory.value_input.setPlainText(content)
        settings = self.window.pages['settings']
        settings.name.setText('Zoé & <Camille>')
        settings.name.setModified(True)
        session = self.window.pages['home'].focus_session
        session.start(None, minutes=25)
        self.window.navigate('memory', animate=False)
        for code in ('en', 'fr', 'en', 'fr'):
            self.ctx.set_language(code)
            APP.processEvents()
            self.window = APP._prepapilot_window
            self.windows.append(self.window)
            self.assertEqual(self.window.current_key, 'memory')
            self.assertEqual(self.window.pages['memory'].key_input.text(), title)
            self.assertEqual(self.window.pages['memory'].value_input.toPlainText(), content)
            self.assertEqual(self.window.pages['settings'].name.text(), 'Zoé & <Camille>')
            self.assertTrue(self.window.pages['settings'].name.isModified())
            self.assertEqual(self.window.pages['home'].focus_session.status, 'running')
            self.assertEqual(self.ctx.db.memories(), {})
        self.window.pages['memory'].save_memory()
        self.assertEqual(self.ctx.db.memories(), {title: content})

    def test_seeded_navigation_themes_and_resizing_preserve_rows_and_draft(self):
        identity = self.ctx.db.add_grade('maths', 'Projet personnel', 7.5, 10,
                                         f'{self.ctx.year}-10-01', '<Étude> & données')
        self.ctx.mark_changed('grades')
        draft = 'Travail non enregistré : ne pas perdre.'
        self.window.pages['memory'].value_input.setPlainText(draft)
        rng = random.Random(20261025)
        for step in range(56):
            key = rng.choice(list(self.window.pages))
            self.window.navigate(key, animate=False)
            self.ctx.set_theme(rng.choice(('light', 'dark')))
            self.window.resize(*rng.choice(((1024, 680), (1360, 900))))
            APP.processEvents()
            self.assertEqual(self.window.current_key, key)
            self.assertIs(self.window.stack.currentWidget(), self.window.wrappers[key])
            self.assertTrue(self.window.nav[key][0].isChecked())
            self.assertEqual(self.window.pages['memory'].value_input.toPlainText(), draft)
        rows = self.ctx.db.list_grades()
        self.assertEqual([row['id'] for row in rows], [identity])
        self.assertEqual(rows[0]['normalized_score'], 15)
        self.assertEqual(rows[0]['label'], '<Étude> & données')

    def test_memory_write_failure_preserves_draft_and_allows_retry(self):
        page = self.window.pages['memory']
        page.key_input.setText('Méthode')
        page.value_input.setPlainText('Vérifier chaque étape.')
        with patch.object(self.ctx.db, 'remember', side_effect=sqlite3.OperationalError('locked')):
            with self.assertRaises(sqlite3.OperationalError):
                page.save_memory()
        self.assertEqual(self.ctx.db.memories(), {})
        self.assertEqual(page.value_input.toPlainText(), 'Vérifier chaque étape.')
        self.assertFalse(page.key_input.isReadOnly())
        page.save_memory()
        self.assertEqual(self.ctx.db.memories(), {'Méthode': 'Vérifier chaque étape.'})

    def test_failed_grade_submit_retry_and_duplicate_click_keep_one_row(self):
        dialog = GradeDialog(self.ctx, parent=self.window)
        dialog.score.setValue(3.5)
        dialog.scale.setValue(7)
        dialog.label.setText('Évaluation 🧭 <essai>')
        with patch.object(self.ctx.db, 'add_grade', side_effect=sqlite3.OperationalError('locked')):
            dialog.save()
        self.assertEqual(self.ctx.db.list_grades(), [])
        self.assertTrue(dialog.save_button.isEnabled())
        dialog.save()
        dialog.save()
        self.assertEqual(dialog.result(), QDialog.Accepted)
        rows = self.ctx.db.list_grades()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['normalized_score'], 10)
        self.assertEqual(rows[0]['label'], 'Évaluation 🧭 <essai>')

    def test_import_notice_distinguishes_incomplete_recovery_from_full_backup(self):
        page = self.window.pages['settings']
        notices = []
        self.ctx.notice.connect(notices.append)
        for suffix, expected in (('.zip', 'Copie de récupération incomplète'),
                                 ('.prepapilot', 'Sauvegarde précédente')):
            plan = MagicMock()
            backup = Path('avant-import' + suffix)
            with patch('mpsi_desktop.settings_page.QFileDialog.getOpenFileName', return_value=('test.prepapilot', '')), \
                 patch('mpsi_desktop.settings_page.inspect_archive', return_value=plan), \
                 patch('mpsi_desktop.settings_page.confirm', return_value=True), \
                 patch('mpsi_desktop.settings_page.apply_import', return_value=backup):
                page.import_all()
            self.assertIn(expected, notices[-1])
            self.assertIn(backup.name, notices[-1])
            plan.close.assert_called_once()

    def test_cloud_import_status_identifies_incomplete_recovery(self):
        from types import SimpleNamespace
        from mpsi_desktop.cloud_dialog import CloudBackupDialog
        dialog = CloudBackupDialog(self.ctx, parent=self.window,
                                   connection=SimpleNamespace(configured=False, connected=False))
        plan = SimpleNamespace(cloud_selection=['grades'], cloud_counts={'grades': 1}, close=MagicMock())
        with patch('mpsi_desktop.cloud_dialog.confirm', return_value=True), \
             patch('mpsi_desktop.cloud_dialog.validate_restore_target'), \
             patch('mpsi_desktop.cloud_dialog.apply_import', return_value=Path('etat-incomplet.zip')):
            dialog._confirm_restore(plan)
        self.assertIn('Copie de récupération incomplète', dialog.status.text())
        self.assertIn('etat-incomplet.zip', dialog.status.text())
        plan.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
