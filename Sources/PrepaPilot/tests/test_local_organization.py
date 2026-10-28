"""Local assistant proposals preserve originals and apply as one reviewed batch."""
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from mpsi_desktop.context import DesktopStore
from mpsi_desktop import local_organization as organization
from mpsi_desktop.i18n import english_catalog


class LocalOrganizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = DesktopStore(self.root / 'data' / 'mpsi.sqlite3')
        source = self.root / 'Suites numériques.txt'
        source.write_text('Cours original complet : ∑, limites et suites.', encoding='utf-8')
        self.content = source.read_bytes()
        self.identity = self.db.import_document(source, 'maths', 'cours')
        self.workspace = organization.prepare_workspace(self.db)

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def plan(self):
        return json.loads((self.workspace / 'proposition.json').read_text(encoding='utf-8'))

    def write(self, proposal):
        (self.workspace / 'proposition.json').write_text(json.dumps(proposal, ensure_ascii=False), encoding='utf-8')

    def state(self):
        return (self.db.list_documents(), self.db.list_document_folders(),
                {file.name: file.read_bytes() for file in self.db.document_directory.iterdir()},
                self.db._rows("SELECT * FROM settings WHERE key GLOB 'document_organization_session_*'"))

    def add_import(self, proposal, name='nouveau.txt', content='Nouveau cours'):
        source = self.workspace / 'A-importer' / name
        source.write_text(content, encoding='utf-8')
        proposal['imports'].append(dict(source='A-importer/' + name, title='Nouveau cours',
            subject='physique', kind='tp', description='Mesures', folder='Physique · TP'))
        return source

    def test_readable_catalogue_copies_and_notice_show_exact_locations(self):
        catalogue = json.loads((self.workspace / 'catalogue.json').read_text(encoding='utf-8'))
        document = catalogue['documents'][0]
        self.assertEqual(catalogue['data_directory'], str(self.db.document_directory.parent))
        self.assertEqual(catalogue['database_path'], str(Path(self.db.path).resolve()))
        self.assertEqual(document['original_path'], str(self.db.document_path(self.identity)))
        self.assertEqual(document['stored_path'], self.db.get_document(self.identity)['stored_path'])
        self.assertEqual(document['subject_name'], self.db.subject_labels()['maths'])
        self.assertIsNone(document['folder'])
        self.assertEqual((self.workspace / document['copy_path']).read_bytes(), self.content)
        self.assertIn('Suites numériques', Path(document['copy_path']).name)
        notice = (self.workspace / 'NOTICE-IA.md').read_text(encoding='utf-8')
        self.assertIn(str(self.db.document_directory), notice)
        self.assertIn('## English', notice)
        self.assertIn('NOTICE-IA.md', (self.workspace / 'AGENTS.md').read_text())
        previous = (self.workspace / 'proposition.json').read_bytes()
        another = organization.prepare_workspace(self.db)
        self.assertNotEqual(another, self.workspace)
        self.assertEqual((self.workspace / 'proposition.json').read_bytes(), previous)

    def test_preview_and_atomic_apply_existing_and_new_courses_then_replay_refused(self):
        proposal = self.plan()
        proposal['documents'][0].update(title='Suites : méthodes', folder='Maths · Analyse', description='Chapitre 4')
        source = self.add_import(proposal)
        self.write(proposal)
        before = self.state()
        report = organization.preview_plan(self.db, self.workspace)
        self.assertEqual((report['update_count'], report['import_count'], report['folder_count']), (1, 1, 2))
        self.assertEqual(self.state(), before)
        organization.apply_plan(self.db, self.workspace, report['digest'])
        self.assertEqual(len(self.db.list_documents()), 2)
        self.assertEqual(self.db.get_document(self.identity)['title'], 'Suites : méthodes')
        self.assertEqual(self.db.document_path(self.identity).read_bytes(), self.content)
        imported = next(row for row in self.db.list_documents() if row['id'] != self.identity)
        self.assertEqual(self.db.document_path(imported['id']).read_bytes(), source.read_bytes())
        with self.assertRaisesRegex(ValueError, 'déjà'):
            organization.apply_plan(self.db, self.workspace, report['digest'])

    def test_omitted_documents_and_changed_reading_copies_do_not_modify_originals(self):
        catalogue = json.loads((self.workspace / 'catalogue.json').read_text(encoding='utf-8'))
        (self.workspace / catalogue['documents'][0]['copy_path']).write_text('Copie modifiée', encoding='utf-8')
        proposal = self.plan()
        proposal['documents'] = []
        self.write(proposal)
        report = organization.preview_plan(self.db, self.workspace)
        self.assertEqual(report['changes'], [])
        self.assertEqual(self.db.document_path(self.identity).read_bytes(), self.content)

    def test_invalid_entry_rejects_entire_batch_without_creating_folder_or_import(self):
        proposal = self.plan()
        proposal['documents'][0]['folder'] = 'Nouveau dossier'
        self.add_import(proposal)
        proposal['imports'][0]['subject'] = 'matiere-inconnue'
        self.write(proposal)
        before = self.state()
        with self.assertRaises(ValueError):
            organization.preview_plan(self.db, self.workspace)
        self.assertEqual(self.state(), before)

    def test_strict_document_id_fields_and_folder_validation(self):
        good = self.plan()
        bad = []
        for identity in (True, 1.0, '1', -1, 999999):
            proposal = copy.deepcopy(good)
            proposal['documents'][0]['id'] = identity
            bad.append(proposal)
        for field, value in (('folder', ''), ('folder', 'X' * 101), ('folder', 'Cours\nTD'),
                             ('title', ''), ('title', 'X' * 241), ('subject', []),
                             ('kind', {}), ('description', 'X' * 10001)):
            proposal = copy.deepcopy(good)
            proposal['documents'][0][field] = value
            bad.append(proposal)
        proposal = copy.deepcopy(good)
        proposal['documents'].append(copy.deepcopy(proposal['documents'][0]))
        bad.append(proposal)
        proposal = copy.deepcopy(good)
        proposal['documents'][0]['stored_path'] = 'documents/other.txt'
        bad.append(proposal)
        before = self.state()
        for proposal in bad:
            with self.subTest(proposal=str(proposal)[:180]):
                self.write(proposal)
                with self.assertRaises(ValueError):
                    organization.preview_plan(self.db, self.workspace)
                self.assertEqual(self.state(), before)

    def test_import_paths_never_escape_exchange_and_reject_unsupported_formats(self):
        proposal = self.plan()
        self.add_import(proposal)
        before = self.state()
        for source in ('../nouveau.txt', '/A-importer/nouveau.txt', 'A-importer/../proposition.json',
                       'A-importer\\nouveau.txt', 'A-importer/./nouveau.txt',
                       'A-importer/nouveau.txt:stream', str(self.root / 'externe.txt'),
                       'Bibliotheque/nouveau.txt', 'A-importer/absent.txt'):
            with self.subTest(source=source):
                proposal['imports'][0]['source'] = source
                self.write(proposal)
                with self.assertRaises(ValueError):
                    organization.preview_plan(self.db, self.workspace)
                self.assertEqual(self.state(), before)
        (self.workspace / 'A-importer' / 'programme.exe').write_bytes(b'Executable')
        proposal['imports'][0]['source'] = 'A-importer/programme.exe'
        self.write(proposal)
        with self.assertRaises(ValueError):
            organization.preview_plan(self.db, self.workspace)

    def test_import_duplicate_case_alias_is_refused(self):
        proposal = self.plan()
        self.add_import(proposal)
        duplicate = copy.deepcopy(proposal['imports'][0])
        duplicate['source'] = duplicate['source'].replace('nouveau', 'NOUVEAU')
        proposal['imports'].append(duplicate)
        self.write(proposal)
        with self.assertRaises(ValueError):
            organization.preview_plan(self.db, self.workspace)

    def test_json_shape_duplicate_keys_nonfinite_and_size_limits_report_clear_errors(self):
        for raw in ('{', '[]', '{"version":1,"version":1}', '{"version":NaN}', '{"version":Infinity}'):
            with self.subTest(raw=raw):
                (self.workspace / 'proposition.json').write_text(raw, encoding='utf-8')
                with self.assertRaises(ValueError) as error:
                    organization.preview_plan(self.db, self.workspace)
                self.assertTrue(str(error.exception))
        (self.workspace / 'proposition.json').write_bytes(b' ' * 1025)
        with patch.object(organization, 'MAX_PLAN_BYTES', 1024), self.assertRaises(ValueError):
            organization.preview_plan(self.db, self.workspace)
        with patch.object(organization, 'MAX_ENTRIES', 0), self.assertRaises(ValueError):
            organization.prepare_workspace(self.db)

    def test_library_changes_make_plan_stale_even_with_same_second_timestamp(self):
        before = self.db.get_document(self.identity)
        self.db.update_document(self.identity, 'Changement manuel', 'maths', 'cours')
        self.db._change('UPDATE documents SET updated_at=? WHERE id=?', (before['updated_at'], self.identity))
        with self.assertRaisesRegex(ValueError, 'bibliothèque a changé'):
            organization.preview_plan(self.db, self.workspace)

    def test_changed_import_or_json_after_preview_needs_new_review(self):
        proposal = self.plan()
        source = self.add_import(proposal, content='ABC')
        self.write(proposal)
        report = organization.preview_plan(self.db, self.workspace)
        before = self.state()
        source.write_text('XYZ', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'changé'):
            organization.apply_plan(self.db, self.workspace, report['digest'])
        self.assertEqual(self.state(), before)
        report = organization.preview_plan(self.db, self.workspace)
        proposal['documents'][0]['folder'] = 'Classement différent'
        self.write(proposal)
        with self.assertRaisesRegex(ValueError, 'changé'):
            organization.apply_plan(self.db, self.workspace, report['digest'])
        self.assertEqual(self.state(), before)

    def test_sql_failure_rolls_back_updated_documents_new_folders_and_new_files(self):
        proposal = self.plan()
        proposal['documents'][0]['folder'] = 'Analyse'
        self.add_import(proposal)
        self.write(proposal)
        report = organization.preview_plan(self.db, self.workspace)
        before = self.state()
        self.db._change("CREATE TRIGGER reject_ai_import BEFORE INSERT ON documents BEGIN SELECT RAISE(ABORT,'test rollback'); END", ())
        with self.assertRaises(sqlite3.IntegrityError):
            organization.apply_plan(self.db, self.workspace, report['digest'])
        self.assertEqual(self.state(), before)
        self.assertEqual(list(self.db.document_directory.parent.glob('.document-ai-*')), [])
        self.db._change('DROP TRIGGER reject_ai_import', ())
        organization.apply_plan(self.db, self.workspace, report['digest'])
        self.assertEqual(len(self.db.list_documents()), 2)

    def test_failed_copy_does_not_commit_any_changes(self):
        proposal = self.plan()
        self.add_import(proposal)
        self.write(proposal)
        report = organization.preview_plan(self.db, self.workspace)
        before = self.state()
        with patch.object(organization.shutil, 'copyfile', side_effect=OSError('Disque plein')):
            with self.assertRaises(OSError):
                organization.apply_plan(self.db, self.workspace, report['digest'])
        self.assertEqual(self.state(), before)
        self.assertEqual(list(self.db.document_directory.parent.glob('.document-ai-*')), [])

    def test_session_cannot_be_reused_by_another_database_or_forged_catalogue(self):
        other = DesktopStore(self.root / 'other' / 'mpsi.sqlite3')
        try:
            with self.assertRaises(ValueError):
                organization.preview_plan(other, self.workspace)
        finally:
            other.close()
        (self.workspace / 'catalogue.json').write_text('{"documents":[]}', encoding='utf-8')
        self.db.update_document(self.identity, 'Autre titre', 'maths', 'cours')
        with self.assertRaises(ValueError):
            organization.preview_plan(self.db, self.workspace)

    def test_all_backend_user_messages_have_english_translations(self):
        import ast
        tree = ast.parse(Path(organization.__file__).read_text(encoding='utf-8'))
        catalogue = english_catalog()
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'tr'
                    and node.args and isinstance(node.args[0], ast.Constant)):
                self.assertIn(node.args[0].value, catalogue)


if __name__ == '__main__':
    unittest.main()
