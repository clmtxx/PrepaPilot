"""Original-file preservation, atomic recovery and library UI regression tests."""
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from mpsi_desktop.context import AppContext, DesktopStore
from mpsi_desktop.documents_page import DocumentsPage, DocumentMetadataDialog

APP=QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class DocumentStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name).resolve()
        self.db=DesktopStore(self.root/'data/mpsi.sqlite3')

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def source(self,name='cours.pdf',content=b'%PDF-original-complete\x00\xff'):
        path=self.root/name
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(content)
        return path

    def test_import_preserves_bytes_and_portable_metadata(self):
        source=self.source()
        identity=self.db.import_document(source,'physique','tp',title='Optique',description='Lentilles')
        row=self.db.get_document(identity)
        self.assertEqual(row['title'],'Optique')
        self.assertEqual(row['original_name'],'cours.pdf')
        self.assertEqual(row['size_bytes'],len(source.read_bytes()))
        self.assertTrue(row['stored_path'].startswith('documents/'))
        self.assertFalse(Path(row['stored_path']).is_absolute())
        self.assertNotIn(str(self.root),str(row))
        self.assertEqual(self.db.document_path(identity).read_bytes(),source.read_bytes())
        source.unlink()
        self.assertTrue(self.db.document_path(identity).is_file())

    def test_same_filename_copies_are_distinct_and_metadata_search_works(self):
        first=self.db.import_document(self.source('one/cours.txt',b'one'),'maths','td')
        second=self.db.import_document(self.source('two/cours.txt',b'two'),'anglais','cours')
        self.assertNotEqual(self.db.get_document(first)['stored_path'],self.db.get_document(second)['stored_path'])
        self.assertTrue(self.db.update_document(first,'Suites','maths','td','Récurrence'))
        self.assertEqual([row['id'] for row in self.db.list_documents('maths','td','RÉCURRENCE')],[first])
        self.assertEqual(self.db.list_documents(kind='tp'),[])
        self.assertEqual(self.db.document_path(second).read_bytes(),b'two')

    def test_invalid_batch_keeps_library_empty(self):
        valid=self.source('good.txt',b'ok')
        for invalid in (self.source('bad.exe'),self.root/'missing.pdf'):
            with self.assertRaises(ValueError):self.db.import_documents([valid,invalid],'maths','cours')
        with self.assertRaises(ValueError):self.db.import_document(valid,'bad-subject','cours')
        with self.assertRaises(ValueError):self.db.import_document(valid,'maths','bad-kind')
        self.assertEqual(self.db.list_documents(),[])
        self.assertEqual(list(self.db.document_directory.iterdir()),[])

    def test_copy_failure_rolls_back_entire_batch(self):
        paths=[self.source('one.txt',b'one'),self.source('two.txt',b'two')]
        original=shutil.copyfile
        copied=[]
        def fail_second(source,target):
            copied.append(source)
            if len(copied)==2:raise OSError('disk full')
            return original(source,target)
        with patch('mpsi_desktop.document_store.shutil.copyfile',side_effect=fail_second):
            with self.assertRaises(OSError):self.db.import_documents(paths,'maths','cours')
        self.assertEqual(self.db.list_documents(),[])
        self.assertEqual(list(self.db.document_directory.iterdir()),[])
        self.assertTrue(all(path.is_file() for path in paths))

    def test_slow_copy_keeps_database_available_and_staging_outside_library(self):
        source=self.source('large.pdf')
        entered=threading.Event()
        resume=threading.Event()
        result=[]
        original=shutil.copyfile
        def slow_copy(source,target):
            entered.set()
            if not resume.wait(3):raise TimeoutError('test copy timeout')
            return original(source,target)
        def work():
            try:result.append(self.db.import_document(source,'maths','cours'))
            except Exception as exc:result.append(exc)
        with patch('mpsi_desktop.document_store.shutil.copyfile',side_effect=slow_copy):
            worker=threading.Thread(target=work)
            worker.start()
            try:
                self.assertTrue(entered.wait(2))
                available=self.db._lock.acquire(timeout=1)
                try:
                    self.assertTrue(available,'Large copies must not block UI database reads')
                    self.assertEqual(list(self.db.document_directory.iterdir()),[])
                finally:
                    if available:self.db._lock.release()
            finally:
                resume.set()
                worker.join(3)
        self.assertEqual(len(result),1)
        self.assertIsInstance(result[0],int)
        self.assertEqual(list((self.root/'data').glob('.document-import-*.tmp')),[])

    def test_database_failure_rolls_back_copies_and_custom_title_import(self):
        with self.db._connection:
            self.db._connection.execute("CREATE TRIGGER fail_import BEFORE INSERT ON documents WHEN NEW.title='bad' BEGIN SELECT RAISE(ABORT,'test failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.import_documents([self.source('good.txt'),self.source('bad.txt')],'maths','cours')
        self.assertEqual(self.db.list_documents(),[])
        self.assertEqual(list(self.db.document_directory.iterdir()),[])
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.import_document(self.root/'good.txt','maths','cours',title='bad')
        self.assertEqual(self.db.list_documents(),[])
        self.assertEqual(list(self.db.document_directory.iterdir()),[])

    def test_invalid_paths_cannot_open_or_delete_outside_files(self):
        identity=self.db.import_document(self.source('safe.txt',b'safe'),'maths','cours')
        outside=self.source('outside.txt',b'keep')
        for unsafe in ('../outside.txt',str(outside),'documents/../../outside.txt',
                       'documents\\outside.txt','documents/payload.exe','file:///tmp/a.pdf'):
            self.db._change('UPDATE documents SET stored_path=? WHERE id=?',(unsafe,identity))
            with self.assertRaises(ValueError):self.db.document_path(identity)
            with self.assertRaises(ValueError):self.db.delete_document(identity)
            self.assertEqual(outside.read_bytes(),b'keep')
        with self.assertRaises(ValueError):self.db._resolve_document_path({'stored_path':None})

    def test_export_and_delete_preserve_user_source(self):
        source=self.source('original.docx',b'complete original bytes')
        identity=self.db.import_document(source,'francais','cours')
        managed=self.db.document_path(identity)
        output=self.root/'copy.docx'
        self.db.export_document(identity,output)
        self.assertEqual(output.read_bytes(),source.read_bytes())
        with self.assertRaises(ValueError):self.db.export_document(identity,self.root/'copy.exe')
        with self.assertRaises(ValueError):self.db.export_document(identity,managed)
        self.assertTrue(self.db.delete_document(identity))
        self.assertFalse(managed.exists())
        self.assertEqual(self.db.list_documents(),[])
        self.assertTrue(source.is_file())
        self.assertFalse(self.db.delete_document(identity))

    def test_failed_delete_restores_original_and_metadata(self):
        identity=self.db.import_document(self.source('course.txt',b'preserve'),'maths','cours')
        managed=self.db.document_path(identity)
        with self.db._connection:
            self.db._connection.execute("CREATE TRIGGER fail_delete BEFORE DELETE ON documents BEGIN SELECT RAISE(ABORT,'test failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):self.db.delete_document(identity)
        self.assertEqual(managed.read_bytes(),b'preserve')
        self.assertIsNotNone(self.db.get_document(identity))

    def test_entire_data_folder_remains_portable(self):
        identity=self.db.import_document(self.source('notes.md',b'# Course\nAll notes'),'si','tp')
        self.db.close()
        shutil.copytree(self.root/'data',self.root/'moved')
        moved=DesktopStore(self.root/'moved/mpsi.sqlite3')
        try:
            self.assertEqual(moved.document_path(identity).read_bytes(),b'# Course\nAll notes')
            self.assertTrue(moved.document_path(identity).is_relative_to(self.root/'moved'))
        finally:moved.close()

    def test_legacy_migration_is_idempotent_including_deleted_fiche(self):
        self.db._insert('INSERT INTO summaries(title,text,mode) VALUES (?,?,?)',('Ancienne fiche','Texte intégral <b>conservé</b>','off'))
        self.db.init_document_tables()
        rows=self.db.list_documents()
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['subject'],'autre')
        self.assertEqual(self.db.document_path(rows[0]['id']).read_text(encoding='utf-8'),'Texte intégral <b>conservé</b>')
        self.db.init_document_tables()
        self.assertEqual(len(self.db.list_documents()),1)
        self.db.delete_document(rows[0]['id'])
        self.db.init_document_tables()
        self.assertEqual(self.db.list_documents(),[])
        self.assertEqual(len(self.db._rows('SELECT * FROM summaries')),1)

    def test_custom_subject_rename_archive_and_historical_edit(self):
        subject = dict(id='subject_'+'a'*32, name='Astronomie', color='#123ABC', active=True)
        self.db.save_subjects(self.db.get_subjects()+[subject])
        identity = self.db.import_document(self.source('etoiles.txt',b'Original entier'), subject['id'], 'cours')
        original_path = self.db.document_path(identity)
        subjects = self.db.get_subjects()
        next(row for row in subjects if row['id'] == subject['id']).update(name='Astrophysique',color='#A123BC',active=False)
        self.db.save_subjects(subjects)
        self.assertEqual(self.db.subject_labels(include_archived=True)[subject['id']], 'Astrophysique')
        self.assertNotIn(subject['id'], self.db.subject_labels())
        self.assertTrue(self.db.update_document(identity,'Spectres stellaires',subject['id'],'td','Historique conservé'))
        self.assertEqual(self.db.document_path(identity), original_path)
        self.assertEqual(original_path.read_bytes(), b'Original entier')
        with self.assertRaises(ValueError):
            self.db.import_document(self.source('nouveau.txt'),subject['id'],'cours')
        other = self.db.import_document(self.source('maths.txt'),'maths','cours')
        with self.assertRaises(ValueError):
            self.db.update_document(other,'Pas un ancien document',subject['id'],'cours')

    def test_subject_archived_during_copy_does_not_commit_new_document(self):
        subject = dict(id='subject_'+'b'*32, name='Astronomie', color='#123ABC', active=True)
        self.db.save_subjects(self.db.get_subjects()+[subject])
        original_copy = shutil.copyfile
        def archive_while_copying(source, target):
            original_copy(source,target)
            subjects = self.db.get_subjects()
            next(row for row in subjects if row['id'] == subject['id'])['active'] = False
            self.db.save_subjects(subjects)
        with patch('mpsi_desktop.document_store.shutil.copyfile',side_effect=archive_while_copying):
            with self.assertRaises(ValueError):
                self.db.import_document(self.source('slow.txt'),subject['id'],'cours')
        self.assertEqual(self.db.list_documents(), [])
        self.assertEqual(list(self.db.document_directory.iterdir()), [])
        self.assertEqual(list((self.root/'data').glob('.document-import-*.tmp')), [])


class DocumentPageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.ctx=AppContext(self.root/'data')
        self.ctx.db.set_setting('desktop_reduced_motion',True)
        self.errors=[]
        self.previous_hook=sys.excepthook
        sys.excepthook=lambda kind,value,tb:self.errors.append((kind.__name__,str(value)))
        self.page=DocumentsPage(self.ctx)
        self.page.resize(1000,700)
        self.page.show()
        APP.processEvents()

    def tearDown(self):
        self.wait_jobs()
        self.page.close()
        self.page.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)
        APP.processEvents()
        self.ctx.close()
        self.temp.cleanup()
        sys.excepthook=self.previous_hook
        self.assertEqual(self.errors,[])

    def wait_jobs(self):
        deadline=time.monotonic()+5
        while self.ctx.busy and time.monotonic()<deadline:
            APP.processEvents()
            QTest.qWait(10)
        APP.processEvents()
        self.assertFalse(self.ctx.busy)

    def source(self,name='cours.txt'):
        path=self.root/name
        path.write_text('<script>Texte original complet</script>',encoding='utf-8')
        return path

    def test_batch_import_preview_selection_and_metadata_edit(self):
        self.page.import_documents([self.source(),self.source('second.md')],'maths','td')
        self.wait_jobs()
        self.assertEqual(self.page.documents.count(),2)
        self.assertIn('<script>',self.page.reader.toPlainText())
        selected=self.ctx.db.get_document(self.page._selected_id)
        dialog=DocumentMetadataDialog(self.ctx,selected,parent=self.page)
        dialog.title.setText('Nouveau chapitre')
        dialog.save()
        self.assertEqual(self.ctx.db.get_document(selected['id'])['title'],'Nouveau chapitre')
        self.page.search.setText('nouveau')
        QTest.qWait(160)
        self.assertEqual(self.page.documents.count(),1)
        self.page.search_everywhere.setChecked(False)
        self.page.kind_filter.setCurrentIndex(self.page.kind_filter.findData('tp'))
        self.assertEqual(self.page.documents.count(),0)

    def test_open_is_local_and_rejects_tampered_paths(self):
        identity=self.ctx.db.import_document(self.source(),'maths','cours')
        self.ctx.mark_changed()
        with patch('mpsi_desktop.documents_page.QDesktopServices.openUrl',return_value=True) as opened:
            self.page.open_selected()
            self.assertTrue(opened.call_args.args[0].isLocalFile())
            self.assertEqual(Path(opened.call_args.args[0].toLocalFile()),self.ctx.db.document_path(identity))
        self.ctx.db._change('UPDATE documents SET stored_path=? WHERE id=?',('../outside.txt',identity))
        with patch('mpsi_desktop.documents_page.QDesktopServices.openUrl') as opened, patch('mpsi_desktop.documents_page.show_error') as error:
            self.page.open_selected()
            opened.assert_not_called()
            error.assert_called_once()

    def test_cancel_delete_and_failed_import_preserve_library(self):
        identity=self.ctx.db.import_document(self.source(),'maths','cours')
        self.ctx.mark_changed()
        with patch('mpsi_desktop.documents_page.confirm',return_value=False):self.page.delete_selected()
        self.assertIsNotNone(self.ctx.db.get_document(identity))
        self.page.import_documents([self.root/'missing.pdf'],'maths','cours')
        self.wait_jobs()
        self.assertTrue(self.page.import_button.isEnabled())
        self.assertEqual(self.page.documents.count(),1)
        self.assertIn('introuvable',self.page.status.text())
        with patch('mpsi_desktop.documents_page.confirm',return_value=True):self.page.delete_selected()
        self.assertEqual(self.ctx.db.list_documents(),[])

    def test_custom_names_colors_filters_and_archived_document_editor(self):
        subject = dict(id='subject_'+'c'*32, name='Astronomie', color='#123ABC', active=True)
        self.ctx.db.save_subjects(self.ctx.db.get_subjects()+[subject])
        identity = self.ctx.db.import_document(self.source(), subject['id'], 'cours')
        self.ctx.mark_changed()
        self.assertIn('Astronomie', self.page.documents.item(0).text())
        item_color = self.page.documents.item(0).icon().pixmap(18,18).toImage().pixelColor(9,9)
        self.assertEqual(item_color.name(), '#123abc')
        self.assertGreaterEqual(self.page.subject_filter.findData(subject['id']), 0)
        subjects = self.ctx.db.get_subjects()
        next(row for row in subjects if row['id'] == subject['id']).update(name='Astrophysique',color='#A123BC',active=False)
        self.ctx.db.save_subjects(subjects)
        self.ctx.mark_changed()
        self.assertIn('Astrophysique', self.page.documents.item(0).text())
        self.assertIn('Astrophysique', self.page.meta_label.text())
        self.assertEqual(self.page.documents.item(0).icon().pixmap(18,18).toImage().pixelColor(9,9).name(), '#a123bc')
        new_dialog = DocumentMetadataDialog(self.ctx,parent=self.page)
        self.assertEqual(new_dialog.subject.findData(subject['id']), -1)
        edit_dialog = DocumentMetadataDialog(self.ctx,self.ctx.db.get_document(identity),parent=self.page)
        self.assertEqual(edit_dialog.subject.currentData(), subject['id'])
        self.assertIn('archivée',edit_dialog.subject.currentText())
        edit_dialog.title.setText('Historique modifiable')
        edit_dialog.save()
        self.assertEqual(self.ctx.db.get_document(identity)['title'],'Historique modifiable')
        self.ctx.db.save_subjects([])
        self.ctx.mark_changed()
        self.assertFalse(self.page.import_button.isEnabled())
        no_subject_dialog = DocumentMetadataDialog(self.ctx,parent=self.page)
        self.assertFalse(no_subject_dialog.save_button.isEnabled())

    def test_first_profile_with_only_biology_uses_active_subject_and_new_document_types(self):
        biology = dict(id='subject_'+'d'*32,name='Biologie',color='#008578',active=True)
        self.ctx.db.save_setup([biology],{'semesters':{'S1':[],'S2':[]}})
        self.assertEqual(self.ctx.db.subject_labels(),{biology['id']:'Biologie'})
        self.ctx.db.set_setting('documents_last_subject','maths')
        self.ctx.db.set_setting('documents_last_kind','removed-kind')
        self.ctx.mark_changed()
        self.assertTrue(self.page.import_button.isEnabled())
        dialog = DocumentMetadataDialog(self.ctx,parent=self.page)
        self.assertEqual(dialog.subject.currentData(),biology['id'])
        self.assertEqual(dialog.subject.currentIndex(),0)
        self.assertEqual(dialog.kind.currentData(),'cours')
        self.assertTrue(dialog.save_button.isEnabled())
        self.assertEqual(dialog.subject.findData('maths'),-1)
        for kind in ('projet','examen','stage'):
            index = dialog.kind.findData(kind)
            self.assertGreaterEqual(index,0)
            dialog.kind.setCurrentIndex(index)
            dialog.save()
            self.assertEqual(self.ctx.db.get_setting('documents_last_subject'),biology['id'])
            self.assertEqual(self.ctx.db.get_setting('documents_last_kind'),kind)
            self.page.import_documents([self.source(f'{kind}.txt')],biology['id'],kind)
            self.wait_jobs()
            self.assertEqual(self.ctx.db.list_documents(kind=kind)[0]['subject'],biology['id'])
        self.assertEqual(self.page.documents.count(),3)
        self.assertTrue(all('Biologie' in self.page.documents.item(index).text() for index in range(3)))


if __name__=='__main__':unittest.main()
