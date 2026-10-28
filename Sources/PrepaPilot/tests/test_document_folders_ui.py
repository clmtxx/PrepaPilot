"""Folders stay optional: global name search and original files remain available."""
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog
from mpsi_desktop.context import AppContext
from mpsi_desktop.documents_page import (
    DocumentsPage, DocumentFolderDialog, DocumentMetadataDialog, MoveDocumentsDialog,
)

APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class DocumentFoldersUITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.ctx = AppContext(self.root / 'data')
        self.ctx.db.set_setting('desktop_reduced_motion', True)
        self.errors = []
        self.previous_hook = sys.excepthook
        sys.excepthook = lambda kind, value, tb: self.errors.append((kind.__name__, str(value)))
        self.page = DocumentsPage(self.ctx)
        self.page.resize(1024, 680)
        self.page.show()
        self.folders = [self.ctx.db.create_document_folder(name) for name in ('Intégrales', 'Langues')]
        self.ids = [
            self.add('maths-source.txt', 'maths', 'cours', 'Cours intégrales', self.folders[0]),
            self.add('anglais-source.txt', 'anglais', 'td', 'Exercices intégrales', self.folders[1]),
            self.add('sans-dossier.txt', 'physique', 'tp', 'TP intégrales', None),
        ]
        self.ctx.mark_changed('documents')
        APP.processEvents()

    def tearDown(self):
        self.wait_jobs()
        self.page.close()
        self.page.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        APP.processEvents()
        self.ctx.close()
        self.temp.cleanup()
        sys.excepthook = self.previous_hook
        self.assertEqual(self.errors, [])

    def add(self, name, subject, kind, title, folder):
        source = self.root / name
        source.write_text('Original complet : ' + name, encoding='utf-8')
        return self.ctx.db.import_document(source, subject, kind, title=title, folder_id=folder)

    def wait_jobs(self):
        deadline = time.monotonic() + 5
        while self.ctx.busy and time.monotonic() < deadline:
            APP.processEvents()
            QTest.qWait(10)
        APP.processEvents()
        self.assertFalse(self.ctx.busy)

    def visible_ids(self):
        return {self.page.documents.item(i).data(Qt.UserRole) for i in range(self.page.documents.count())}

    def choose(self, control, value):
        index = control.findData(value)
        self.assertGreaterEqual(index, 0)
        control.setCurrentIndex(index)

    def search(self, query):
        self.page.search.setText(query)
        QTest.qWait(150)

    def test_name_search_ignores_all_filters_and_clearing_restores_folder(self):
        self.choose(self.page.folder_filter, self.folders[0])
        self.choose(self.page.subject_filter, 'maths')
        self.choose(self.page.kind_filter, 'cours')
        self.assertEqual(self.visible_ids(), {self.ids[0]})
        self.assertTrue(self.page.search_everywhere.isChecked())
        self.search('ANGLAIS-SOURCE')
        self.assertEqual(self.visible_ids(), {self.ids[1]})
        self.assertFalse(self.page.folder_filter.isEnabled())
        self.assertIn('PARTOUT', self.page.count.text())
        self.search('intégrales')
        self.assertEqual(self.visible_ids(), set(self.ids))
        self.search('')
        self.assertEqual(self.visible_ids(), {self.ids[0]})
        self.assertEqual(self.page.folder_filter.currentData(), self.folders[0])
        self.assertTrue(self.page.folder_filter.isEnabled())

    def test_scoped_search_respects_subject_type_and_folder(self):
        self.choose(self.page.folder_filter, self.folders[1])
        self.choose(self.page.subject_filter, 'anglais')
        self.choose(self.page.kind_filter, 'td')
        self.page.search_everywhere.setChecked(False)
        self.search('intégrales')
        self.assertEqual(self.visible_ids(), {self.ids[1]})
        self.choose(self.page.kind_filter, 'cours')
        self.assertEqual(self.visible_ids(), set())
        self.page.search_everywhere.setChecked(True)
        self.assertEqual(self.visible_ids(), set(self.ids))

    def test_ranger_moves_the_entire_selection_without_copying_files(self):
        before = {i: self.ctx.db.document_path(i) for i in self.ids}
        self.page.documents.clearSelection()
        for index in range(self.page.documents.count()):
            item = self.page.documents.item(index)
            item.setSelected(item.data(Qt.UserRole) in self.ids[:2])
        self.assertEqual(set(self.page.selected_document_ids()), set(self.ids[:2]))
        self.assertTrue(self.page.move_button.isEnabled())
        self.assertFalse(self.page.delete_button.isEnabled())
        observed = []
        def save_dialog(dialog):
            observed.extend(dialog.identities)
            self.choose(dialog.folder, None)
            dialog.save()
            return dialog.result()
        with patch.object(MoveDocumentsDialog, 'exec', save_dialog):
            self.page.move_selected()
        self.assertEqual(set(observed), set(self.ids[:2]))
        for identity in self.ids:
            self.assertIsNone(self.ctx.db.get_document(identity)['folder_id'])
            self.assertEqual(self.ctx.db.document_path(identity), before[identity])
            self.assertTrue(before[identity].is_file())

    def test_create_rename_and_remove_folder_preserve_documents(self):
        with patch.object(DocumentFolderDialog, 'exec', lambda dialog: QDialog.Rejected):
            self.page.new_folder()
        self.assertEqual(len(self.ctx.db.list_document_folders()), 2)
        def create(dialog):
            dialog.name.setText('Chapitre à réviser')
            dialog.save()
            return dialog.result()
        with patch.object(DocumentFolderDialog, 'exec', create):
            self.page.new_folder()
        created = self.page.folder_filter.currentData()
        self.assertNotIn(created, self.folders)
        with patch.object(DocumentFolderDialog, 'exec', lambda dialog: QDialog.Rejected):
            self.page.rename_folder()
        self.assertEqual(self.page.folder_filter.currentText(), 'Chapitre à réviser')
        def rename(dialog):
            dialog.name.setText('Révisions terminées')
            dialog.save()
            return dialog.result()
        with patch.object(DocumentFolderDialog, 'exec', rename):
            self.page.rename_folder()
        self.assertEqual(self.page.folder_filter.currentText(), 'Révisions terminées')
        self.choose(self.page.folder_filter, self.folders[0])
        original = self.ctx.db.document_path(self.ids[0]).read_bytes()
        with patch('mpsi_desktop.documents_page.confirm', return_value=False):
            self.page.delete_folder()
        self.assertEqual(self.ctx.db.get_document(self.ids[0])['folder_id'], self.folders[0])
        with patch('mpsi_desktop.documents_page.confirm', return_value=True):
            self.page.delete_folder()
        self.assertIsNone(self.ctx.db.get_document(self.ids[0])['folder_id'])
        self.assertEqual(self.ctx.db.document_path(self.ids[0]).read_bytes(), original)
        self.assertEqual(self.page.folder_filter.currentData(), 0)
        self.assertIn(self.ids[0], self.visible_ids())

    def test_import_into_folder_resets_search_and_edit_can_change_folder(self):
        self.search('aucun résultat')
        self.choose(self.page.subject_filter, 'anglais')
        self.choose(self.page.kind_filter, 'tp')
        source = self.root / 'nouveau-cours.txt'
        source.write_text('Nouveau cours intégral', encoding='utf-8')
        self.page.import_documents([source], 'maths', 'cours', folder_id=self.folders[0])
        self.wait_jobs()
        self.assertEqual(self.page.search.text(), '')
        self.assertIsNone(self.page.subject_filter.currentData())
        self.assertIsNone(self.page.kind_filter.currentData())
        self.assertEqual(self.page.folder_filter.currentData(), self.folders[0])
        identity = self.page._selected_id
        self.assertNotIn(identity, self.ids)
        self.assertEqual(self.ctx.db.get_document(identity)['folder_id'], self.folders[0])
        dialog = DocumentMetadataDialog(self.ctx, self.ctx.db.get_document(identity), parent=self.page)
        self.assertEqual(dialog.folder.currentData(), self.folders[0])
        dialog.title.setText('Cours corrigé')
        self.choose(dialog.folder, self.folders[1])
        dialog.save()
        self.assertEqual(dialog.result(), QDialog.Accepted)
        self.assertEqual(self.ctx.db.get_document(identity)['folder_id'], self.folders[1])
        self.search('nouveau-cours.txt')
        self.assertEqual(self.visible_ids(), {identity})

    def test_replacing_data_resets_folder_and_search_scope(self):
        self.choose(self.page.folder_filter, self.folders[0])
        self.page.search_everywhere.setChecked(False)
        self.search('intégrales')
        self.ctx.data_replaced.emit()
        self.assertEqual(self.page.search.text(), '')
        self.assertIsNone(self.page.folder_filter.currentData())
        self.assertTrue(self.page.search_everywhere.isChecked())
        self.assertEqual(self.visible_ids(), set(self.ids))

    def test_invalid_folder_name_and_cancelled_move_leave_library_unchanged(self):
        dialog = DocumentFolderDialog(self.ctx, parent=self.page)
        dialog.name.setText('   ')
        dialog.save()
        self.assertIsNone(dialog.saved_id)
        self.assertTrue(dialog.error.text())
        self.assertEqual(len(self.ctx.db.list_document_folders()), 2)
        move = MoveDocumentsDialog(self.ctx, self.ids[:2], self.folders[0], parent=self.page)
        self.choose(move.folder, None)
        move.reject()
        self.assertFalse(move.saved)
        self.assertEqual(self.ctx.db.get_document(self.ids[0])['folder_id'], self.folders[0])
        self.assertEqual(self.ctx.db.get_document(self.ids[1])['folder_id'], self.folders[1])

    def test_long_folder_names_do_not_force_page_or_dialog_overflow(self):
        long_name = 'Révisions ' + 'x' * 90
        identity = self.ctx.db.create_document_folder(long_name)
        self.ctx.mark_changed('documents')
        self.choose(self.page.folder_filter, identity)
        APP.processEvents()
        self.assertLessEqual(self.page.minimumSizeHint().width(), 1024)
        self.assertEqual(self.page.folder_filter.toolTip(), long_name)
        for dialog in (MoveDocumentsDialog(self.ctx, self.ids, identity, parent=self.page),
                       DocumentMetadataDialog(self.ctx, folder_id=identity, parent=self.page),
                       DocumentFolderDialog(self.ctx, {'id': identity, 'name': long_name}, parent=self.page)):
            dialog.show()
            APP.processEvents()
            self.assertLessEqual(dialog.width(), 1024)
            self.assertLessEqual(dialog.height(), 640)
            bottom = dialog.save_button.mapTo(dialog, dialog.save_button.rect().bottomRight()).y()
            self.assertLess(bottom, dialog.height())
            dialog.reject()
            dialog.deleteLater()


if __name__ == '__main__':
    unittest.main()
