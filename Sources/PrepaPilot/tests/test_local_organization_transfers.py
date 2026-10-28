"""Applied organization survives transfers; exchange sessions stay on the device."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from zipfile import ZipFile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from mpsi_desktop.context import AppContext, DesktopStore
from mpsi_desktop import cloud_backup, transfers
from mpsi_desktop.local_organization import prepare_workspace, preview_plan, apply_plan
from tests.test_cloud_backup import FakeDrive

APP = QApplication.instance() or QApplication([])


class LocalOrganizationTransferTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = AppContext(self.root / 'source')
        self.target = AppContext(self.root / 'target')
        original = self.root / 'cours.txt'
        original.write_text('Cours conservé avec ses accents et ∑.', encoding='utf-8')
        self.identity = self.source.db.import_document(original, 'maths', 'cours')
        self.content = original.read_bytes()

    def tearDown(self):
        self.source.close()
        self.target.close()
        self.temp.cleanup()

    def organize(self):
        workspace = prepare_workspace(self.source.db)
        path = workspace / 'proposition.json'
        proposal = json.loads(path.read_text(encoding='utf-8'))
        proposal['documents'][0]['folder'] = 'Analyse · Suites'
        proposal['documents'][0]['title'] = 'Suites et limites'
        path.write_text(json.dumps(proposal, ensure_ascii=False), encoding='utf-8')
        report = preview_plan(self.source.db, workspace)
        apply_plan(self.source.db, workspace, report['digest'])
        self.source.db.set_setting('documents_organization_workspace', str(workspace))
        return workspace

    def assert_organized(self):
        document = self.target.db.get_document(self.identity)
        self.assertEqual(document['title'], 'Suites et limites')
        self.assertEqual(self.target.db.get_document_folder(document['folder_id'])['name'], 'Analyse · Suites')
        self.assertEqual(self.target.db.document_path(self.identity).read_bytes(), self.content)
        self.assertEqual(self.target.db._rows("SELECT key FROM settings WHERE key GLOB 'document_organization_session_*'"), [])
        self.assertIsNone(self.target.db.get_setting('documents_organization_workspace'))

    def test_full_export_restores_classification_without_local_session_authority(self):
        workspace = self.organize()
        archive = self.root / 'cours.prepapilot'
        transfers.export_archive(self.source, archive)
        with ZipFile(archive) as contents:
            self.assertFalse(any('Rangement-IA' in name for name in contents.namelist()))
            snapshot = self.root / 'export.sqlite3'
            snapshot.write_bytes(contents.read('data.sqlite3'))
        with closing(sqlite3.connect(snapshot)) as connection:
            self.assertEqual(connection.execute("SELECT key FROM settings WHERE key GLOB 'document_organization_session_*'").fetchall(), [])
        with transfers.inspect_archive(archive, DesktopStore) as plan:
            transfers.apply_import(self.target, plan)
        self.assert_organized()
        self.assertTrue(workspace.is_dir())
        self.assertTrue(self.source.db._rows("SELECT key FROM settings WHERE key GLOB 'document_organization_session_*'"))

    def test_drive_restores_classification_and_invalidates_previous_local_session(self):
        self.organize()
        prepare_workspace(self.target.db)
        drive = FakeDrive()
        result = cloud_backup.backup_to_drive(self.source, drive, 'root', ['documents'])
        manifest = json.loads(drive.payloads[result['snapshot_id']])
        settings = [json.loads(drive.payloads[manifest['objects'][digest]['id']])['values']['key']
                    for digest in manifest['records'].get('settings', [])]
        self.assertFalse(any(key.startswith('document_organization_session_') for key in settings))
        self.assertNotIn('documents_organization_workspace', settings)
        with cloud_backup.prepare_drive_restore(self.target, drive, 'root', result['snapshot_id']) as plan:
            cloud_backup.validate_restore_target(self.target, plan)
            transfers.apply_import(self.target, plan)
        self.assert_organized()


if __name__ == '__main__':
    unittest.main()
