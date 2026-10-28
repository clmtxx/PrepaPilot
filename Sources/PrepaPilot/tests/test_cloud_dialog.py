import os
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QEvent, QThread
from PySide6.QtWidgets import QApplication, QLabel, QScrollArea
from mpsi_desktop.context import AppContext
from mpsi_desktop.cloud_dialog import CloudBackupDialog, folder_identifier
from mpsi_desktop.cloud_preferences import utc_now
from mpsi_desktop.transfers import export_archive
from mpsi_desktop.i18n import set_language
from mpsi_desktop.theme import apply_theme
from zipfile import ZipFile

APP = QApplication.instance() or QApplication([])


class CloudDialogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ctx = AppContext(Path(self.temp.name) / 'data')
        self.connection = SimpleNamespace(configured=False, connected=False)
        self.dialog = CloudBackupDialog(self.ctx, connection=self.connection)

    def tearDown(self):
        self.ctx.pool.waitForDone()
        APP.processEvents()
        self.dialog.close()
        self.dialog.deleteLater()
        APP.processEvents()
        self.ctx.close()
        self.temp.cleanup()
        set_language('fr')

    def wait_finished(self):
        deadline = time.monotonic() + 5
        while (self.ctx.busy or self.dialog.running) and time.monotonic() < deadline:
            APP.processEvents()
            time.sleep(.005)
        APP.processEvents()
        self.assertFalse(self.ctx.busy)
        self.assertFalse(self.dialog.running)

    def test_missing_publisher_configuration_does_not_ask_user_to_create_google_client(self):
        self.assertFalse(self.dialog.connect_button.isEnabled())
        self.assertTrue(self.dialog.configure_button.isEnabled())
        self.assertTrue(self.dialog.advanced_options.isHidden())
        self.assertFalse(self.dialog.backup_button.isEnabled())
        self.assertIn('L’éditeur doit la préparer', self.dialog.connection_status.text())
        self.assertIn('aucun compte développeur à créer', self.dialog.connection_status.text())
        self.assertIn('Exporter toutes mes données', self.dialog.connection_status.text())
        self.assertNotIn('Google Cloud', self.dialog.connection_status.text())
        self.assertNotIn('JSON', self.dialog.connection_status.text())
        self.connection.configured = True
        self.dialog.refresh_controls()
        self.assertTrue(self.dialog.connect_button.isEnabled())
        self.assertIn('La connexion est prête', self.dialog.connection_status.text())

    def test_ready_connection_signs_in_directly_without_opening_configuration(self):
        self.connection.configured = True
        client = SimpleNamespace(list_backup_folders=Mock(return_value=[]))
        self.connection.client = Mock(return_value=client)
        self.connection.connect = Mock(side_effect=lambda **kwargs: setattr(self.connection, 'connected', True))
        self.dialog.refresh_controls()
        with patch('mpsi_desktop.cloud_dialog.QFileDialog.getOpenFileName') as choose_config, \
             patch('mpsi_desktop.cloud_dialog.confirm') as configure_confirmation:
            self.dialog.connect_button.click()
            self.wait_finished()
        self.connection.connect.assert_called_once()
        client.list_backup_folders.assert_called_once()
        choose_config.assert_not_called()
        configure_confirmation.assert_not_called()
        self.assertTrue(self.connection.connected)
        self.assertTrue(self.dialog.advanced_options.isHidden())
        self.assertFalse(self.dialog.configure_button.isEnabled())

    def test_manual_configuration_is_collapsed_and_available_as_an_advanced_option(self):
        self.assertTrue(self.dialog.advanced_options.isHidden())
        self.dialog.advanced_button.click()
        self.assertFalse(self.dialog.advanced_options.isHidden())
        configured = Path(self.temp.name) / 'custom-client.json'
        self.connection.configure = Mock(side_effect=lambda path: setattr(self.connection, 'configured', True))
        with patch('mpsi_desktop.cloud_dialog.confirm', return_value=True), \
             patch('mpsi_desktop.cloud_dialog.QFileDialog.getOpenFileName', return_value=(str(configured), '')):
            self.dialog.configure_google()
        self.connection.configure.assert_called_once_with(configured)
        self.assertTrue(self.dialog.connect_button.isEnabled())
        self.dialog.advanced_button.click()
        self.assertTrue(self.dialog.advanced_options.isHidden())

    def test_cancelled_advanced_configuration_preserves_current_configuration(self):
        self.connection.configured = True
        self.connection.configure = Mock()
        with patch('mpsi_desktop.cloud_dialog.confirm', return_value=False), \
             patch('mpsi_desktop.cloud_dialog.QFileDialog.getOpenFileName') as choose_config:
            self.dialog.configure_google()
        choose_config.assert_not_called()
        self.connection.configure.assert_not_called()
        self.assertTrue(self.connection.configured)

    def test_english_connection_copy_and_advanced_options_fit_small_window(self):
        set_language('en')
        apply_theme(APP, 'light')
        dialog = CloudBackupDialog(self.ctx, connection=SimpleNamespace(configured=False, connected=False))
        try:
            dialog.resize(680, 540)
            dialog.show()
            APP.processEvents()
            self.assertEqual(dialog.connect_button.text(), 'Sign in with Google')
            self.assertEqual(dialog.advanced_button.text(), 'Advanced options')
            self.assertIn('publisher', dialog.connection_status.text())
            self.assertIn('do not need a developer account', dialog.connection_status.text())
            area = dialog.findChild(QScrollArea)
            self.assertEqual(area.horizontalScrollBar().maximum(), 0)
            dialog.advanced_button.click()
            APP.processEvents()
            self.assertEqual(area.horizontalScrollBar().maximum(), 0)
            self.assertEqual(dialog.configure_button.text(), 'Import a personal configuration…')
            dialog.connection.configured = True
            dialog.refresh_controls()
            self.assertIn('connection is ready', dialog.connection_status.text())
        finally:
            dialog.close()
            dialog.deleteLater()
            APP.sendPostedEvents(None, QEvent.DeferredDelete)
            APP.processEvents()
            apply_theme(APP, 'light')

    def test_selection_and_folder_control_real_backup_availability(self):
        self.connection.configured = self.connection.connected = True
        self.dialog._set_folders([dict(id='valid_folder', name='Mes sauvegardes')])
        self.assertTrue(self.dialog.backup_button.isEnabled())
        for choice in self.dialog.choices.values():
            choice.setChecked(False)
        self.assertFalse(self.dialog.backup_button.isEnabled())
        self.dialog.choices['sleep'].setChecked(True)
        self.assertTrue(self.dialog.backup_button.isEnabled())
        self.assertTrue(self.dialog.save_preferences())
        self.assertEqual(self.dialog.preferences.read()['selection'], ['sleep'])

    def test_worker_finishes_before_gui_success_and_has_no_database_replacement_race(self):
        observed = []
        worker_threads = []
        def work(cancel):
            worker_threads.append(QThread.currentThread())
            return 'ready'
        def handler(value):
            observed.append((value, self.ctx.busy, QThread.currentThread() == APP.thread()))
        self.dialog._start(work, handler, 'Test')
        self.wait_finished()
        self.assertEqual(observed, [('ready', False, True)])
        self.assertNotEqual(worker_threads[0], APP.thread())

    def test_cancelling_prepared_restore_closes_plan_and_does_not_apply_it(self):
        entered = threading.Event()
        plan = SimpleNamespace(close=Mock())
        handler = Mock()
        def work(cancel):
            entered.set()
            cancel.wait(2)
            return plan
        self.dialog._start(work, handler, 'Test')
        self.assertTrue(entered.wait(1))
        self.dialog.reject()
        self.wait_finished()
        plan.close.assert_called_once()
        handler.assert_not_called()

    def test_failure_does_not_set_last_backup(self):
        def work(cancel):
            raise ValueError('Google est indisponible.')
        self.dialog._start(work, Mock(), 'Test')
        self.wait_finished()
        self.assertIsNone(self.dialog.preferences.read()['last_success'])
        self.assertIn('indisponible', self.dialog.status.text())

    def test_cancelled_confirmation_does_not_replace_data(self):
        plan = SimpleNamespace(cloud_selection=['grades'], cloud_counts={'grades': 2}, close=Mock())
        with patch('mpsi_desktop.cloud_dialog.confirm', return_value=False), patch('mpsi_desktop.cloud_dialog.apply_import') as apply:
            self.dialog._confirm_restore(plan)
        apply.assert_not_called()
        plan.close.assert_called_once()

    def test_stale_target_is_checked_before_any_import(self):
        plan = SimpleNamespace(cloud_selection=['sleep'], cloud_counts={'sleep': 1}, close=Mock())
        with patch('mpsi_desktop.cloud_dialog.confirm', return_value=True), \
             patch('mpsi_desktop.cloud_dialog.validate_restore_target', side_effect=ValueError('Données modifiées')), \
             patch('mpsi_desktop.cloud_dialog.apply_import') as apply:
            with self.assertRaisesRegex(ValueError, 'modifiées'):
                self.dialog._confirm_restore(plan)
        apply.assert_not_called()
        plan.close.assert_called_once()

    def test_local_cloud_credentials_and_preferences_are_not_in_portable_archive(self):
        private = self.ctx.data_dir / 'cloud'
        private.mkdir()
        (private / 'credentials.bin').write_bytes(b'personal account token')
        (private / 'client.json').write_text('{"private":true}', encoding='utf-8')
        self.dialog.preferences.ensure_started(utc_now())
        output = Path(self.temp.name) / 'portable.prepapilot'
        export_archive(self.ctx, output)
        with ZipFile(output) as archive:
            self.assertNotIn('cloud', '/'.join(archive.namelist()))
            self.assertFalse(any(b'personal account token' in archive.read(name) for name in archive.namelist()))

    def test_folder_links_are_bounded_to_google_drive(self):
        for value in ('https://drive.google.com/drive/folders/abc_123?usp=sharing', 'https://drive.google.com/drive/u/0/folders/abc_123', 'abc_123'):
            self.assertEqual(folder_identifier(value), 'abc_123')
        for value in ('https://example.com/drive/folders/foo', 'http://drive.google.com/drive/folders/foo', '../credentials', 'https://drive.google.com.evil.test/drive/folders/foo'):
            with self.assertRaises(ValueError):
                folder_identifier(value)


if __name__ == '__main__':
    unittest.main()
