"""Global search returns real local data without changing it or opening files."""
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
from mpsi_desktop.global_search import GlobalSearchDialog, find_results
from mpsi_desktop.i18n import set_language


APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class GlobalSearchTests(unittest.TestCase):
    def setUp(self):
        set_language('fr')
        self.temporary = tempfile.TemporaryDirectory()
        self.ctx = AppContext(Path(self.temporary.name) / 'data')
        self.ctx.db.set_setting('desktop_reduced_motion', True)
        self.dialogs = []
        self.sample = Path(self.temporary.name) / 'Cours d’électricité.txt'
        self.sample.write_text('Document fictif, jamais lu par la recherche.', encoding='utf-8')

    def tearDown(self):
        for dialog in self.dialogs:
            dialog.close()
            dialog.deleteLater()
        APP.sendPostedEvents(None, QEvent.DeferredDelete)
        APP.processEvents()
        self.ctx.close()
        self.temporary.cleanup()
        set_language('fr')

    def dialog(self):
        result = GlobalSearchDialog(self.ctx)
        self.dialogs.append(result)
        result.show()
        result.activateWindow()
        APP.processEvents()
        return result

    def seed(self):
        document = self.ctx.db.import_document(self.sample, 'maths', 'cours',
                                              title='Électricité appliquée', description='Révision des circuits')
        grade = self.ctx.db.add_grade('maths', 'cours', 14, 20, f'{self.ctx.year}-09-10', 'Électricité contrôle')
        self.ctx.db.remember('Projet électricité', 'Réviser les circuits et les tensions.')
        return document, grade

    def test_empty_query_performs_no_database_reads(self):
        with patch.object(self.ctx.db, '_rows', side_effect=AssertionError('Unexpected read')):
            self.assertEqual(find_results(self.ctx, '   '), [])
            self.assertEqual(find_results(self.ctx, ' !!! '), [])

    def test_decimal_grade_uses_the_interface_language(self):
        self.ctx.db.add_grade('maths', 'cours', 14.5, 20, f'{self.ctx.year}-09-10', 'Projet décimal')
        self.assertIn('14,5/20', find_results(self.ctx, 'décimal')[0]['subtitle'])
        self.ctx.set_language('en')
        self.assertIn('14.5/20', find_results(self.ctx, 'décimal')[0]['subtitle'])

    def test_search_matches_accents_multiple_fields_and_actual_identities(self):
        document, grade = self.seed()
        before = self.ctx.db._connection.total_changes
        rows = find_results(self.ctx, 'electricite')
        self.assertEqual({row['kind'] for row in rows}, {'document', 'grade', 'memory'})
        self.assertEqual(next(row['id'] for row in rows if row['kind'] == 'document'), document)
        self.assertEqual(next(row['id'] for row in rows if row['kind'] == 'grade'), grade)
        self.assertEqual(next(row['key'] for row in rows if row['kind'] == 'memory'), 'Projet électricité')
        rows = find_results(self.ctx, 'mathematiques circuits')
        self.assertEqual([(row['kind'], row['id']) for row in rows], [('document', document)])
        self.assertEqual(self.ctx.db._connection.total_changes, before)

    def test_filters_and_school_year_scope_do_not_return_old_grades(self):
        self.seed()
        old = self.ctx.db.add_grade('maths', 'cours', 10, 20, f'{self.ctx.year-1}-09-10', 'Électricité archive')
        grades = find_results(self.ctx, 'electricite', kind='grade')
        self.assertEqual(len(grades), 1)
        self.assertNotEqual(grades[0]['id'], old)
        self.assertTrue(all(row['kind'] == 'memory' for row in find_results(self.ctx, 'electricite', kind='memory')))
        self.assertEqual(find_results(self.ctx, "'); DROP TABLE grades; --"), [])
        self.assertEqual(len(self.ctx.db.list_grades()), 2)

    def test_title_relevance_precedes_content_and_output_is_bounded(self):
        for index in range(65):
            self.ctx.db.remember(f'Méthode {index:02}', 'Électricité dans le contenu')
        self.ctx.db.remember('Électricité', 'Un résultat exact')
        with patch.object(self.ctx.db, '_rows', wraps=self.ctx.db._rows) as reads:
            rows = find_results(self.ctx, 'electricite', limit=12)
        self.assertEqual(len(rows), 12)
        self.assertEqual(rows[0]['key'], 'Électricité')
        result_queries = [call for call in reads.call_args_list if 'pp_global_score' in call.args[0]]
        self.assertEqual(len(result_queries), 3)
        self.assertTrue(all('LIMIT ?' in call.args[0] for call in result_queries))
        self.assertTrue(all(call.args[1][-1] == 13 for call in result_queries))
        with self.assertRaises(ValueError):
            find_results(self.ctx, 'electricite', limit=1000)

    def test_search_never_reads_original_document_files(self):
        self.seed()
        with patch.object(Path, 'open', side_effect=AssertionError('Document file should not be opened')):
            self.assertEqual(len(find_results(self.ctx, 'electricite', kind='document')), 1)

    def test_typing_is_debounced_and_enter_opens_current_query(self):
        document, _ = self.seed()
        dialog = self.dialog()
        with patch('mpsi_desktop.global_search.find_results', wraps=find_results) as search:
            dialog.search.setText('elect')
            dialog.search.setText('electricite appliquee')
            search.assert_not_called()
            QTest.keyClick(dialog.search, Qt.Key_Return)
        self.assertEqual(search.call_count, 1)
        self.assertEqual(dialog.result(), QDialog.Accepted)
        self.assertEqual(dialog.selected_result['id'], document)
        self.assertEqual(dialog.selected_result['kind'], 'document')

    def test_keyboard_selection_and_clearing_never_open_stale_result(self):
        self.seed()
        dialog = self.dialog()
        dialog.search.setText('electricite')
        QTest.qWait(220)
        self.assertEqual(dialog.results.count(), 3)
        QTest.keyClick(dialog.search, Qt.Key_Down)
        self.assertEqual(dialog.results.currentRow(), 1)
        dialog.search.setText('introuvable xyz')
        self.assertEqual(dialog.results.count(), 0)
        QTest.keyClick(dialog.search, Qt.Key_Return)
        self.assertIsNone(dialog.selected_result)
        self.assertTrue(dialog.isVisible())
        self.assertFalse(dialog.open_button.isEnabled())
        dialog.search.clear()
        self.assertIn('Saisis', dialog.empty.text())

    def test_escape_stops_pending_search_and_does_not_write_data(self):
        dialog = self.dialog()
        before = self.ctx.db._connection.total_changes
        with patch('mpsi_desktop.global_search.find_results', wraps=find_results) as search:
            dialog.search.setText('electricite')
            QTest.keyClick(dialog.search, Qt.Key_Escape)
            QTest.qWait(220)
        search.assert_not_called()
        self.assertFalse(dialog.search_timer.isActive())
        self.assertIsNone(dialog.selected_result)
        self.assertEqual(self.ctx.db._connection.total_changes, before)


if __name__ == '__main__':
    unittest.main()
