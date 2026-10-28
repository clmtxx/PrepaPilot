"""Performance regressions expressed as bounded work, independent of CPU speed."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QObject, QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget
from mpsi_desktop.context import AppContext
from mpsi_desktop.documents_page import DocumentsPage
from mpsi_desktop.notes import NotesPage
from mpsi_desktop.ui_updates import updating

APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class RefreshPerformanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ctx = AppContext(Path(self.temp.name) / 'data')
        self.widgets = []

    def tearDown(self):
        for widget in self.widgets:
            widget.close()
            widget.deleteLater()
        APP.sendPostedEvents(None, QEvent.DeferredDelete)
        APP.processEvents()
        self.ctx.close()
        self.temp.cleanup()

    def test_grade_lookup_reads_year_once_for_large_history(self):
        with self.ctx.db._connection:
            self.ctx.db._connection.executemany(
                'INSERT INTO grades(subject,kind,score,scale,graded_on,label,coefficient) VALUES (?,?,?,?,?,?,?)',
                [('maths', 'cours', 12, 20, f'{self.ctx.year}-09-10', str(i), 1) for i in range(250)])
        queries = []
        self.ctx.db._connection.set_trace_callback(queries.append)
        self.assertEqual(len(self.ctx.grades()), 250)
        self.ctx.db._connection.set_trace_callback(None)
        self.assertLessEqual(len(queries), 2)

    def test_scoped_changes_skip_unrelated_pages_and_global_change_refreshes(self):
        notes, documents = NotesPage(self.ctx), DocumentsPage(self.ctx)
        self.widgets += [notes, documents]
        with patch.object(self.ctx.db, 'list_grades', wraps=self.ctx.db.list_grades) as grades, patch.object(self.ctx.db, 'list_documents', wraps=self.ctx.db.list_documents) as library:
            self.ctx.mark_changed('memories')
            grades.assert_not_called()
            library.assert_not_called()
            self.ctx.mark_changed('grades')
            self.assertEqual(grades.call_count, 1)
            library.assert_not_called()
            self.ctx.mark_changed()
            self.assertEqual(grades.call_count, 2)
            self.assertEqual(library.call_count, 1)

    def test_nested_notification_restores_outer_scope(self):
        seen = []
        def nested():
            if self.ctx.change_domains == frozenset({'grades'}):
                self.ctx.mark_changed('documents')
            seen.append(self.ctx.change_domains)
        self.ctx.data_changed.connect(nested)
        self.ctx.mark_changed('grades')
        self.assertEqual(seen, [frozenset({'documents'}), frozenset({'grades'})])
        self.assertIsNone(self.ctx.change_domains)

    def test_watch_lifetime_follows_page(self):
        calls = []
        class Receiver(QObject):
            def refresh(self):
                calls.append(True)
        owner = Receiver()
        self.ctx.watch_data(owner.refresh, 'grades')
        self.ctx.mark_changed('grades')
        owner.deleteLater()
        APP.sendPostedEvents(None, QEvent.DeferredDelete)
        self.ctx.mark_changed()
        self.assertEqual(calls, [True])

    def test_unchanged_notes_keep_cards_selection_and_table_items(self):
        identity = self.ctx.db.add_grade('maths', 'cours', 12, 20, f'{self.ctx.year}-09-10')
        notes = NotesPage(self.ctx)
        self.widgets.append(notes)
        notes.table.selectRow(0)
        original = notes.table.item(0, 0)
        card = notes.mean_stat
        notes.refresh()
        self.assertIs(notes.table.item(0, 0), original)
        self.assertIs(notes.mean_stat, card)
        self.assertEqual(notes.selected_grade()['id'], identity)
        self.ctx.db.update_grade(identity, 'maths', 'cours', 18, 20, f'{self.ctx.year}-09-10')
        self.ctx.mark_changed('grades')
        self.assertIn('18', notes.mean_stat.value.text())
        self.assertIs(notes.mean_stat, card)

    def test_document_refresh_has_no_per_document_subject_queries(self):
        source = Path(self.temp.name) / 'document.txt'
        source.write_text('Cours fictif', encoding='utf-8')
        for i in range(30):
            self.ctx.db.import_document(source, 'maths', 'cours', title=f'Cours {i}')
        page = DocumentsPage(self.ctx)
        self.widgets.append(page)
        with patch.object(self.ctx.db, 'get_subjects', wraps=self.ctx.db.get_subjects) as subjects:
            page.refresh()
        self.assertEqual(page.documents.count(), 30)
        self.assertLessEqual(subjects.call_count, 3)

    def test_document_search_coalesces_typing_and_filters_apply_immediately(self):
        page = DocumentsPage(self.ctx)
        self.widgets.append(page)
        with patch.object(self.ctx.db, 'list_documents', wraps=self.ctx.db.list_documents) as listing:
            for text in ('s', 'su', 'sui', 'suites'):
                page.search.setText(text)
            listing.assert_not_called()
            QTest.qWait(180)
            self.assertEqual(listing.call_count, 1)
            self.assertEqual(listing.call_args.args[2], 'suites')
            page.search.setText('autre')
            page.kind_filter.setCurrentIndex(page.kind_filter.findData('td'))
            self.assertEqual(listing.call_count, 2)
            self.assertFalse(page.search_timer.isActive())

    def test_bulk_update_restores_widget_on_error(self):
        widget = QWidget()
        self.widgets.append(widget)
        with self.assertRaises(ValueError):
            with updating(widget):
                self.assertFalse(widget.updatesEnabled())
                self.assertTrue(widget.signalsBlocked())
                raise ValueError('Interrupted update')
        self.assertTrue(widget.updatesEnabled())
        self.assertFalse(widget.signalsBlocked())


if __name__ == '__main__':
    unittest.main()
