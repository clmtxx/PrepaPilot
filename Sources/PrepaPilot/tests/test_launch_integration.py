"""The launch features reach real content without losing session or editor state."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from datetime import timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from mpsi_desktop.context import AppContext
from mpsi_desktop.global_search import GlobalSearchDialog
from mpsi_desktop.help_center import HelpCenterDialog
from mpsi_desktop.i18n import set_language
from mpsi_desktop.window import MainWindow

APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class LaunchIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ctx = AppContext(Path(self.temp.name) / 'data')
        self.ctx.db.set_setting('desktop_reduced_motion', True)
        self.window = MainWindow(self.ctx, show_welcome=False)
        self.window.resize(1024, 680)
        self.window.show()
        APP.processEvents()
        self.home = self.window.pages['home']

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        APP.sendPostedEvents(None, QEvent.DeferredDelete)
        APP.processEvents()
        self.ctx.close()
        self.temp.cleanup()
        set_language('fr')

    def test_ctrl_f_opens_search_from_an_editor_and_reaches_document(self):
        sample = Path(self.temp.name) / 'Projet.txt'
        sample.write_text('Fiche de démonstration', encoding='utf-8')
        identity = self.ctx.db.import_document(sample, 'maths', 'cours')
        self.ctx.mark_changed('documents')
        documents = self.window.pages['documents']
        documents.search.setText('aucun résultat')
        documents.refresh()
        self.window.navigate('settings', animate=False)
        field = self.window.pages['settings'].name
        field.setFocus()

        def choose(dialog):
            dialog.search.setText('projet')
            dialog.run_search()
            dialog.activate_selected()
            return dialog.result()

        with patch.object(GlobalSearchDialog, 'exec', new=choose):
            QTest.keyClick(field, Qt.Key_F, Qt.ControlModifier)
        self.assertEqual(self.window.current_key, 'documents')
        self.assertEqual(documents._selected_id, identity)
        self.assertEqual(documents.selected_document_ids(), [identity])
        self.assertEqual(documents.search.text(), '')

    def test_search_reaches_grade_subject_and_row(self):
        identity = self.ctx.db.add_grade('physique', 'ds', 15, 20, f'{self.ctx.year}-09-20', 'Projet énergie')
        self.ctx.mark_changed('grades')
        self.window.open_search_result(dict(kind='grade', id=identity))
        page = self.window.pages['notes']
        self.assertEqual(self.window.current_key, 'notes')
        self.assertEqual(page.subject, 'physique')
        self.assertEqual(page.selected_grade()['id'], identity)

    def test_search_reaches_memory_and_preserves_unsaved_editor_on_cancel(self):
        self.ctx.db.remember('Méthode', 'Contenu enregistré')
        self.ctx.mark_changed('memories')
        page = self.window.pages['memory']
        page.new_memory()
        page.key_input.setText('Mon brouillon')
        page.value_input.setPlainText('Texte à conserver')
        self.window.navigate('settings', animate=False)
        with patch('mpsi_desktop.window.confirm', return_value=False):
            self.window.open_search_result(dict(kind='memory', key='Méthode'))
        self.assertEqual(self.window.current_key, 'settings')
        self.assertEqual(page.key_input.text(), 'Mon brouillon')
        self.assertEqual(page.value_input.toPlainText(), 'Texte à conserver')
        with patch('mpsi_desktop.window.confirm', return_value=True):
            self.window.open_search_result(dict(kind='memory', key='Méthode'))
        self.assertEqual(self.window.current_key, 'memory')
        self.assertEqual(page.key_input.text(), 'Méthode')
        self.assertEqual(page.value_input.toPlainText(), 'Contenu enregistré')

    def test_stale_result_is_reported_without_changing_page(self):
        self.window.navigate('settings', animate=False)
        with patch.object(self.window, 'notify') as notice:
            for result in (dict(kind='document', id=9999), dict(kind='grade', id=9999), dict(kind='memory', key='absent')):
                self.window.open_search_result(result)
        self.assertEqual(notice.call_count, 3)
        self.assertEqual(self.window.current_key, 'settings')

    def test_session_bar_tracks_state_and_return_does_not_pause(self):
        bar = self.window.focus_bar
        self.assertTrue(bar.isHidden())
        self.home.focus_session.start('maths', minutes=25, title='Travail de démonstration')
        self.home._sync_focus()
        self.assertTrue(bar.isHidden())
        self.window.navigate('documents', animate=False)
        self.assertTrue(bar.isVisible())
        self.assertEqual(bar.time_label.text(), '25:00')
        QTest.mouseClick(bar.toggle_button, Qt.LeftButton)
        self.assertEqual(self.home.focus_session.status, 'paused')
        self.assertIn('PAUSE', bar.status_label.text())
        QTest.mouseClick(bar.return_button, Qt.LeftButton)
        self.assertEqual(self.window.current_key, 'home')
        self.assertEqual(self.home.focus_session.status, 'paused')
        self.assertTrue(bar.isHidden())

    def test_f1_works_and_cancelled_search_does_not_pause_work(self):
        self.home.focus_session.start('maths', minutes=25)
        self.home._sync_focus()
        self.window.navigate('notes', animate=False)
        with patch.object(HelpCenterDialog, 'exec', return_value=QDialog.Rejected) as help_open:
            QTest.keyClick(self.window, Qt.Key_F1)
        help_open.assert_called_once()
        with patch.object(GlobalSearchDialog, 'exec', return_value=QDialog.Rejected):
            self.window.open_global_search()
        self.assertEqual(self.home.focus_session.status, 'running')
        self.assertTrue(self.home.timer.isActive())

    def test_paused_bar_refreshes_renamed_subject_immediately(self):
        self.home.focus_session.start('maths', minutes=25)
        self.home.focus_session.pause()
        self.home._sync_focus()
        self.window.navigate('documents', animate=False)
        subjects = self.ctx.db.get_subjects()
        next(row for row in subjects if row['id']=='maths')['name'] = 'Analyse appliquée'
        self.ctx.db.save_subjects(subjects)
        self.ctx.mark_changed('subjects')
        self.assertEqual(self.window.focus_bar.context_label.full_text, 'Analyse appliquée')

    def test_today_total_includes_autonomous_work(self):
        now = self.ctx.db._time_now().replace(hour=0, minute=0, second=0, microsecond=0)
        with patch.object(self.ctx.db, '_time_now', return_value=now + timedelta(hours=23)):
            self.ctx.db.add_time_entry('permanence', now.isoformat(timespec='minutes'),
                                       (now + timedelta(minutes=25)).isoformat(timespec='minutes'), 'Travail autonome')
            self.home.refresh()
        self.assertEqual(self.home.work_stat.value.text(), '25 min')


if __name__ == '__main__':
    unittest.main()
