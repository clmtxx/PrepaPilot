"""Storage paths are isolated from the developer's and portable users' data."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mpsi_core.storage import Store
from mpsi_desktop.context import prepare_data


class DataPathTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.application = self.root / 'Application' / 'PrepaPilot'
        self.application.mkdir(parents=True)
        self.local = self.root / 'Profil' / 'Local'
        root_patch = patch('mpsi_desktop.context.app_root', return_value=self.application)
        root_patch.start()
        self.addCleanup(root_patch.stop)
        environment_patch = patch.dict(os.environ, {'LOCALAPPDATA': str(self.local)})
        environment_patch.start()
        self.addCleanup(environment_patch.stop)

    def mark_installed(self, folder=None):
        marker = (folder or self.application) / 'installation.json'
        marker.write_text(json.dumps({'data_mode': 'localappdata'}), encoding='utf-8')

    def personal_data(self, folder, owner):
        folder.mkdir(parents=True, exist_ok=True)
        store = Store(folder / 'mpsi.sqlite3')
        try:
            store.remember('Propriétaire', owner)
        finally:
            store.close()
        documents = folder / 'documents'
        documents.mkdir()
        (documents / 'cours.txt').write_text(owner, encoding='utf-8')

    def test_portable_keeps_existing_data_next_to_executable(self):
        portable = self.application / 'data'
        self.personal_data(portable, 'Espace portable')
        original = (portable / 'mpsi.sqlite3').read_bytes()

        data, migrated = prepare_data()

        self.assertEqual(data, portable)
        self.assertFalse(migrated)
        self.assertEqual((data / 'mpsi.sqlite3').read_bytes(), original)
        self.assertFalse(self.local.exists())

    def test_installed_app_starts_empty_without_importing_any_portable_data(self):
        self.mark_installed()
        sources = [self.application / 'data',
                   self.application.parent / 'CompagnonMPSI' / 'data',
                   self.root / 'Archives' / 'Anciennes-versions' / 'outputs' / 'PrepaPilot' / 'data']
        for number, source in enumerate(sources):
            self.personal_data(source, f'Données personnelles {number}')
        original = {(source / 'mpsi.sqlite3'): (source / 'mpsi.sqlite3').read_bytes()
                    for source in sources}

        with patch('mpsi_desktop.context.snapshot_database') as snapshot:
            data, migrated = prepare_data()

        self.assertEqual(data, self.local / 'PrepaPilot' / 'data')
        self.assertFalse(migrated)
        self.assertEqual(list(data.iterdir()), [])
        snapshot.assert_not_called()
        for source in sources:
            self.assertEqual((source / 'mpsi.sqlite3').read_bytes(), original[source / 'mpsi.sqlite3'])
            self.assertTrue((source / 'documents' / 'cours.txt').is_file())

    def test_installed_app_retains_its_user_data_after_an_application_move(self):
        self.mark_installed()
        expected = self.local / 'PrepaPilot' / 'data'
        self.personal_data(expected, 'Espace installé')
        original = (expected / 'mpsi.sqlite3').read_bytes()
        data, migrated = prepare_data()
        self.assertEqual(data, expected)
        self.assertFalse(migrated)
        other = self.root / 'Nouvelle-version'
        other.mkdir()
        self.mark_installed(other)

        with patch('mpsi_desktop.context.app_root', return_value=other):
            data, migrated = prepare_data()

        self.assertEqual(data, expected)
        self.assertFalse(migrated)
        self.assertEqual((data / 'mpsi.sqlite3').read_bytes(), original)
        self.assertEqual((data / 'documents' / 'cours.txt').read_text(encoding='utf-8'), 'Espace installé')
        self.assertFalse((other / 'data').exists())
        self.assertFalse((self.application / 'data').exists())

    def test_explicit_root_takes_priority_over_installer_markers_for_self_test(self):
        self.mark_installed()
        disposable = self.root / 'Test-jetable'
        disposable.mkdir()
        self.mark_installed(disposable)
        self.personal_data(self.application / 'data', 'Ne pas ouvrir')
        with patch('mpsi_desktop.context._installed_data_directory') as installed:
            data, migrated = prepare_data(disposable, migrate=False)
        self.assertEqual(data, disposable / 'data')
        self.assertFalse(migrated)
        self.assertEqual(list(data.iterdir()), [])
        installed.assert_not_called()
        self.assertFalse(self.local.exists())

    def test_installer_mode_remains_active_when_migration_is_disabled(self):
        self.mark_installed()
        data, migrated = prepare_data(migrate=False)
        self.assertEqual(data, self.local / 'PrepaPilot' / 'data')
        self.assertFalse(migrated)
        self.assertFalse((self.application / 'data').exists())

    def test_unrecognised_markers_keep_the_existing_portable_contract(self):
        marker = self.application / 'installation.json'
        for contents in ('not json', '[]', 'null', '{}', '{"data_mode":"portable"}',
                         '{"data_mode":true}'):
            with self.subTest(contents=contents):
                marker.write_text(contents, encoding='utf-8')
                data, migrated = prepare_data(migrate=False)
                self.assertEqual(data, self.application / 'data')
                self.assertFalse(migrated)
        self.assertFalse(self.local.exists())

    def test_marker_with_utf8_bom_is_recognised(self):
        (self.application / 'installation.json').write_text(
            '{"data_mode":"localappdata"}', encoding='utf-8-sig')
        data, migrated = prepare_data()
        self.assertEqual(data, self.local / 'PrepaPilot' / 'data')
        self.assertFalse(migrated)

    def test_missing_localappdata_uses_windows_profile_without_portable_fallback(self):
        self.mark_installed()
        home = self.root / 'Profil-sans-variable'
        with patch.dict(os.environ, {'LOCALAPPDATA': ''}), \
             patch('mpsi_desktop.context.Path.home', return_value=home):
            data, migrated = prepare_data()
        self.assertEqual(data, home / 'AppData' / 'Local' / 'PrepaPilot' / 'data')
        self.assertFalse(migrated)
        self.assertFalse((self.application / 'data').exists())


if __name__ == '__main__':
    unittest.main()
