"""Update notifications and the hand-off after a successful, durable shutdown."""
import hashlib
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QEvent, QLockFile
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid
from mpsi_desktop.app_updates import ReleaseInfo
from mpsi_desktop.context import AppContext
from mpsi_desktop.i18n import set_language
from mpsi_desktop.update_install import InstallRequest
from mpsi_desktop.window import MainWindow

APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class UpdateIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.ctx = AppContext(self.root / 'data')
        self.ctx.db.set_setting('desktop_reduced_motion', True)
        self.windows = []

    def tearDown(self):
        self.ctx.pending_installer = None
        for window in self.windows:
            if isValid(window):
                window.close()
                window.deleteLater()
        APP.sendPostedEvents(None, QEvent.DeferredDelete)
        APP.processEvents()
        self.ctx.close()
        self.temp.cleanup()
        set_language('fr')

    def window(self):
        window = MainWindow(self.ctx, show_welcome=False)
        window.show()
        self.windows.append(window)
        APP.processEvents()
        return window

    def ready(self):
        controller = self.ctx.updates
        controller.repository, controller.installed = 'publisher/PrepaPilot', True
        controller.release = ReleaseInfo('2.20.0', 'PrepaPilot-2.20.0-Setup.exe',
            'https://github.com/publisher/PrepaPilot/releases/download/v2.20.0/PrepaPilot-2.20.0-Setup.exe',
            'https://github.com/publisher/PrepaPilot/releases/download/v2.20.0/SHA256SUMS.txt',
            'https://github.com/publisher/PrepaPilot/releases/tag/v2.20.0', 128, 'publisher/PrepaPilot')
        controller.cache_dir.mkdir(parents=True)
        path = controller.cache_dir / controller.release.installer_name
        path.write_bytes(b'MZ' + b'x' * 126)
        controller.downloaded_path = path
        controller.downloaded_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        controller.state = 'ready'
        controller.changed.emit()
        return path

    def test_install_requires_confirmation_and_a_successful_focus_checkpoint(self):
        window = self.window()
        path = self.ready()
        with patch('mpsi_desktop.window.confirm', return_value=False):
            window.install_update(path)
        self.assertIsNone(self.ctx.pending_installer)
        self.assertFalse(window._closing)
        with patch('mpsi_desktop.window.confirm', return_value=True), \
                patch.object(window.pages['home'], 'shutdown_focus', side_effect=OSError('read only')):
            window.install_update(path)
        self.assertIsNone(self.ctx.pending_installer)
        self.assertFalse(window._closing)
        session = window.pages['home'].focus_session
        session.start('maths')
        with patch('mpsi_desktop.window.confirm', return_value=True), patch.object(APP, 'quit'):
            window.install_update(path)
        self.assertTrue(window._closing)
        self.assertEqual(self.ctx.pending_installer.path, path)
        self.assertEqual(session.status, 'paused')
        self.assertEqual(self.ctx.db.get_setting('desktop_focus_session')['status'], 'paused')

    def test_changed_download_is_rejected_without_closing_and_can_be_downloaded_again(self):
        window = self.window()
        path = self.ready()
        path.write_bytes(b'MZ' + b'altered' * 30)
        with patch('mpsi_desktop.window.show_error') as error, patch('mpsi_desktop.window.confirm') as confirm:
            window.install_update(path)
        error.assert_called_once()
        confirm.assert_not_called()
        self.assertFalse(window._closing)
        self.assertIsNone(self.ctx.pending_installer)
        self.assertIsNone(self.ctx.updates.downloaded_path)
        self.assertEqual(self.ctx.updates.state, 'available')

    def test_available_notice_and_preferences_survive_language_change(self):
        old = self.window()
        self.assertFalse(old.update_start_timer.isActive())
        self.assertFalse(old.update_check_timer.isActive())
        self.ready()
        self.ctx.updates.set_automatic(False)
        self.assertFalse(old.update_notice.isHidden())
        old.open_update_settings()
        self.assertEqual(old.current_key, 'settings')
        self.ctx.set_language('en')
        APP.processEvents()
        new = APP._prepapilot_window
        self.windows.append(new)
        self.assertIs(new.pages['settings'].update_panel.controller, self.ctx.updates)
        self.assertIn('2.20.0', new.update_notice_text.text())
        self.assertIn('available', new.update_notice_text.text())
        self.assertFalse(new.pages['settings'].update_panel.automatic.isChecked())

    def test_main_launches_installer_after_database_close_and_lock_release(self):
        from mpsi_desktop import main as entry
        saved = {}
        data = self.root / 'isolated-main'
        plan = InstallRequest(self.root / 'not-executed.exe', '2.20.0', 128, '0' * 64)

        class Window:
            def __init__(self, ctx, **_):
                saved['ctx'] = ctx
            def show(self):
                pass

        class Application:
            def __getattr__(self, name):
                return getattr(APP, name)
            def exec(self):
                saved['ctx'].pending_installer = plan
                return 0

        def launch(request, language):
            self.assertIs(request, plan)
            with self.assertRaises(sqlite3.ProgrammingError):
                saved['ctx'].db._connection.execute('SELECT 1')
            lock = QLockFile(str(data / 'application.lock'))
            self.assertTrue(lock.tryLock(0))
            lock.unlock()

        with patch.object(entry, 'QApplication', return_value=Application()), \
                patch.object(entry, 'MainWindow', Window), \
                patch.object(entry, 'run_initial_setup', return_value=True), \
                patch('mpsi_desktop.language_choice.choose_language', return_value=True), \
                patch('mpsi_desktop.update_install.launch_update', side_effect=launch) as launcher, \
                patch('sys.argv', ['prepapilot', '--data-dir', str(data)]):
            self.assertEqual(entry.main(), 0)
        launcher.assert_called_once()


if __name__ == '__main__':
    unittest.main()
