"""Logical folders keep originals portable and all document operations atomic."""
from pathlib import Path
from contextlib import closing
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from mpsi_desktop.context import DesktopStore
from mpsi_desktop.document_store import normalize_document_folder_name


class DocumentFolderStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.database = self.root / 'data' / 'mpsi.sqlite3'
        self.db = DesktopStore(self.database)

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def source(self, name='cours.pdf', content=b'%PDF-complete-original\x00\xff'):
        path = self.root / name
        path.write_bytes(content)
        return path

    def document(self, name='cours.pdf', folder_id=None, subject='maths'):
        return self.db.import_document(self.source(name), subject, 'cours', folder_id=folder_id)

    def test_old_database_migration_keeps_originals_and_is_idempotent(self):
        identity = self.document()
        before = self.db.get_document(identity)
        path = self.db.document_path(identity)
        content = path.read_bytes()
        self.db.close()
        with closing(sqlite3.connect(self.database)) as connection:
            with connection:
                connection.execute('DROP INDEX documents_folder')
                connection.execute('ALTER TABLE documents DROP COLUMN folder_id')
                connection.execute('DROP TABLE document_folders')
        self.db = DesktopStore(self.database)
        after = self.db.get_document(identity)
        self.assertIsNone(after.pop('folder_id'))
        before.pop('folder_id')
        self.assertEqual(after, before)
        self.assertEqual(self.db.document_path(identity).read_bytes(), content)
        self.assertEqual(self.db.list_document_folders(), [])
        self.db.init_document_tables()
        self.assertEqual(len(self.db.list_documents()), 1)
        self.assertIsNone(self.db.get_document(identity)['folder_id'])
        indexes = {row['name'] for row in self.db._rows('PRAGMA index_list(documents)')}
        self.assertIn('documents_folder', indexes)

    def test_create_rename_counts_and_reopen(self):
        zed = self.db.create_document_folder('  Zèbre  ')
        alpha = self.db.create_document_folder('Analyse')
        self.document(folder_id=zed)
        self.assertEqual([row['id'] for row in self.db.list_document_folders()], [alpha, zed])
        self.assertEqual([row['document_count'] for row in self.db.list_document_folders()], [0, 1])
        self.assertEqual(self.db.get_document_folder(zed)['name'], 'Zèbre')
        self.assertTrue(self.db.rename_document_folder(zed, 'Électromagnétisme'))
        self.db.close()
        self.db = DesktopStore(self.database)
        self.assertEqual(self.db.get_document_folder(zed)['name'], 'Électromagnétisme')
        self.assertEqual(self.db.list_documents()[0]['folder_id'], zed)
        self.assertIsNone(self.db.get_document_folder(999))
        self.assertFalse(self.db.rename_document_folder(999, 'Absent'))

    def test_names_are_normalized_unique_and_reject_controls(self):
        first = self.db.create_document_folder('E\u0301quations')
        self.assertEqual(self.db.get_document_folder(first)['name'], 'Équations')
        for value in ('équations', ' ÉQUATIONS ', 'e\u0301quations'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.db.create_document_folder(value)
        second = self.db.create_document_folder('Analyse')
        with self.assertRaises(ValueError):
            self.db.rename_document_folder(second, 'ÉQUATIONS')
        self.assertEqual(self.db.get_document_folder(second)['name'], 'Analyse')
        self.assertTrue(self.db.rename_document_folder(first, 'ÉQUATIONS'))
        for value in ('', '   ', 'x' * 101, None, 7, 'A\nB', 'A\n', 'A\x00', 'A\u200bB', 'A\u2028B'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_document_folder_name(value)
        self.assertEqual(normalize_document_folder_name('  Chapitre / 1 : suites  '), 'Chapitre / 1 : suites')

    def test_folder_limit_does_not_prevent_rename(self):
        with self.db._connection:
            self.db._connection.executemany('INSERT INTO document_folders(name) VALUES (?)',
                                            [(f'Dossier {index}',) for index in range(1000)])
        with self.assertRaises(ValueError):
            self.db.create_document_folder('Un de plus')
        self.assertTrue(self.db.rename_document_folder(1, 'Nouveau nom'))
        self.assertEqual(len(self.db.list_document_folders()), 1000)

    def test_folder_ids_are_strict_integers(self):
        document = self.document()
        for value in (True, 0, -1, 1.0, '1', 2**63):
            for action in (lambda: self.db.get_document_folder(value),
                           lambda: self.db.list_documents(folder_id=value),
                           lambda: self.db.move_documents([document], value),
                           lambda: self.db.rename_document_folder(value, 'test'),
                           lambda: self.db.delete_document_folder(value)):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    action()
        self.assertIsNone(self.db.get_document(document)['folder_id'])

    def test_folder_delete_keeps_documents_and_every_original_byte(self):
        folder = self.db.create_document_folder('À revoir')
        identities = [self.document('premier.pdf', folder), self.document('second.pdf', folder)]
        originals = {identity: (self.db.document_path(identity), self.db.document_path(identity).read_bytes())
                     for identity in identities}
        self.assertTrue(self.db.delete_document_folder(folder))
        self.assertFalse(self.db.delete_document_folder(folder))
        self.assertEqual(self.db.list_document_folders(), [])
        self.assertEqual({row['id'] for row in self.db.list_documents(folder_id=None)}, set(identities))
        for identity, (path, content) in originals.items():
            self.assertEqual(self.db.document_path(identity), path)
            self.assertEqual(path.read_bytes(), content)

    def test_failed_folder_delete_rolls_back_document_detachment(self):
        folder = self.db.create_document_folder('Préserver')
        identity = self.document(folder_id=folder)
        with self.db._connection:
            self.db._connection.execute("CREATE TRIGGER fail_folder_delete BEFORE DELETE ON document_folders BEGIN SELECT RAISE(ABORT,'test failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.delete_document_folder(folder)
        self.assertIsNotNone(self.db.get_document_folder(folder))
        self.assertEqual(self.db.get_document(identity)['folder_id'], folder)
        self.assertTrue(self.db.document_path(identity).is_file())

    def test_move_multiple_keeps_paths_and_rejects_entire_invalid_selection(self):
        folder = self.db.create_document_folder('Chapitre 1')
        first, second = self.document(), self.document('second.pdf')
        old_paths = [self.db.document_path(identity) for identity in (first, second)]
        for selection, destination in (([first, 999], folder), ([first, second], 999),
                                       ([first, True], folder), ([second, '1'], folder)):
            with self.assertRaises(ValueError):
                self.db.move_documents(selection, destination)
            self.assertTrue(all(row['folder_id'] is None for row in self.db.list_documents()))
        self.assertEqual(self.db.move_documents([first, second, first], folder), 2)
        self.assertEqual([self.db.document_path(identity) for identity in (first, second)], old_paths)
        self.assertEqual({row['id'] for row in self.db.list_documents(folder_id=folder)}, {first, second})
        self.assertEqual(self.db.move_documents([first], None), 1)
        self.assertEqual([row['id'] for row in self.db.list_documents(folder_id=None)], [first])

    def test_failed_move_rolls_back_every_document(self):
        folder = self.db.create_document_folder('Destination')
        first, second = self.document(), self.document('second.pdf')
        with self.db._connection:
            self.db._connection.execute(f"CREATE TRIGGER fail_move BEFORE UPDATE OF folder_id ON documents WHEN NEW.id={second} BEGIN SELECT RAISE(ABORT,'test failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.move_documents([first, second], folder)
        self.assertTrue(all(row['folder_id'] is None for row in self.db.list_documents()))

    def test_single_and_batch_import_into_folder_and_update_preserves_default(self):
        folder = self.db.create_document_folder('Physique')
        first = self.db.import_document(self.source(), 'physique', 'td', title='Énergie', folder_id=folder)
        others = self.db.import_documents([self.source('second.pdf'), self.source('third.pdf')],
                                         'physique', 'td', folder_id=folder)
        self.assertEqual({row['id'] for row in self.db.list_documents(folder_id=folder)}, {first, *others})
        self.db.update_document(first, 'Mécanique', 'physique', 'cours', 'Exercices')
        self.assertEqual(self.db.get_document(first)['folder_id'], folder)
        self.db.update_document(first, 'Mécanique', 'physique', 'cours', folder_id=None)
        self.assertIsNone(self.db.get_document(first)['folder_id'])
        self.db.update_document(first, 'Mécanique', 'physique', 'cours', folder_id=folder)
        self.assertEqual(self.db.get_document(first)['folder_id'], folder)
        with self.assertRaises(ValueError):
            self.db.update_document(first, 'Changement invalide', 'physique', 'cours', folder_id=999)
        self.assertEqual(self.db.get_document(first)['title'], 'Mécanique')
        self.assertEqual(self.db.get_document(first)['folder_id'], folder)

    def test_import_checks_destination_before_copying(self):
        source = self.source()
        with patch('mpsi_desktop.document_store.shutil.copyfile') as copy:
            with self.assertRaises(ValueError):
                self.db.import_documents([source], 'maths', 'cours', folder_id=999)
            with self.assertRaises(ValueError):
                self.db.import_document(source, 'maths', 'cours', folder_id=999)
        copy.assert_not_called()
        self.assertEqual(self.db.list_documents(), [])

    def test_removed_folder_during_copy_rolls_back_whole_batch(self):
        folder = self.db.create_document_folder('Destination disparue')
        paths = [self.source('first.pdf'), self.source('second.pdf')]
        original_copy = shutil.copyfile
        copied = []
        def remove_destination(source, target):
            result = original_copy(source, target)
            copied.append(source)
            if len(copied) == 2:
                self.db.delete_document_folder(folder)
            return result
        with patch('mpsi_desktop.document_store.shutil.copyfile', side_effect=remove_destination):
            with self.assertRaises(ValueError):
                self.db.import_documents(paths, 'maths', 'cours', folder_id=folder)
        self.assertEqual(len(copied), 2)
        self.assertEqual(self.db.list_documents(), [])
        self.assertEqual(list(self.db.document_directory.iterdir()), [])
        self.assertEqual(list((self.root / 'data').glob('.document-import-*.tmp')), [])
        self.assertTrue(all(path.is_file() for path in paths))

    def test_global_search_covers_all_folders_and_original_filenames(self):
        first_folder = self.db.create_document_folder('Premier')
        second_folder = self.db.create_document_folder('Deuxième')
        first = self.document('examen-optique.pdf', first_folder, 'physique')
        second = self.document('examen-algebre.pdf', second_folder)
        unfiled = self.document('examen-libre.pdf')
        self.db.update_document(first, 'Titre personnalisé', 'physique', 'cours')
        self.assertEqual({row['id'] for row in self.db.list_documents(search='EXAMEN')}, {first, second, unfiled})
        self.assertEqual([row['id'] for row in self.db.list_documents(search='optique')], [first])
        self.assertEqual([row['id'] for row in self.db.list_documents(search='examen', folder_id=second_folder)], [second])
        self.assertEqual([row['id'] for row in self.db.list_documents(search='examen', folder_id=None)], [unfiled])
        self.assertEqual([row['id'] for row in self.db.list_documents('physique', 'cours', 'EXAMEN')], [first])
        self.assertEqual(self.db.get_document(first)['original_name'], 'examen-optique.pdf')


if __name__ == '__main__':
    unittest.main()
