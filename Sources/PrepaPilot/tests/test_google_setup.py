"""Fresh installations use publisher setup; reminder checks never reach Google."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from datetime import timedelta
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication
from mpsi_desktop.context import AppContext
from mpsi_desktop.cloud_preferences import utc_now
from mpsi_desktop.i18n import set_language
from mpsi_desktop.settings_page import SettingsPage
from mpsi_desktop.window import MainWindow


APP = QApplication.instance() or QApplication([])


class GoogleSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ctx = AppContext(Path(self.temp.name) / 'data')
        self.addCleanup(self.ctx.close)
        self.page = SettingsPage(self.ctx)
        self.addCleanup(self.page.close)
        self.addCleanup(set_language, 'fr')
        self.page.cloud_preferences.update(first_seen=(utc_now() - timedelta(days=10)).isoformat())

    def test_unprepared_version_explains_publisher_setup_without_unusable_reminder(self):
        self.page.google_connection = SimpleNamespace(configured=False)
        with patch('mpsi_desktop.google_auth._open', side_effect=AssertionError('Must remain offline')):
            self.page.refresh_cloud()
        self.assertIn('éditeur', self.page.cloud_status.text())
        self.assertIn('.prepapilot', self.page.cloud_status.text())
        self.assertNotIn('Connecte Google', self.page.cloud_status.text())
        self.assertNotIn('nouvelle sauvegarde', self.page.cloud_status.text())

    def test_prepared_version_invites_account_connection(self):
        self.page.google_connection = SimpleNamespace(configured=True)
        self.page.refresh_cloud()
        self.assertIn('Connecte Google Drive', self.page.cloud_status.text())
        self.assertIn('nouvelle sauvegarde', self.page.cloud_status.text())
        self.assertNotIn('éditeur', self.page.cloud_status.text())

    def test_publisher_setup_explanation_is_translated(self):
        set_language('en')
        self.page.google_connection = SimpleNamespace(configured=False)
        self.page.refresh_cloud()
        self.assertIn('publisher', self.page.cloud_status.text())
        self.assertIn('once for all users', self.page.cloud_status.text())

    def test_due_banner_only_appears_when_this_version_can_connect_to_google(self):
        banner = SimpleNamespace(visible=None)
        banner.setVisible = lambda visible: setattr(banner, 'visible', visible)
        shell = SimpleNamespace(pages={'settings': self.page}, backup_reminder=banner)
        self.page.google_connection = SimpleNamespace(configured=False)
        MainWindow.refresh_backup_reminder(shell)
        self.assertFalse(banner.visible)
        self.page.google_connection.configured = True
        MainWindow.refresh_backup_reminder(shell)
        self.assertTrue(banner.visible)
        self.page.cloud_preferences.update(reminders=False)
        MainWindow.refresh_backup_reminder(shell)
        self.assertFalse(banner.visible)


if __name__ == '__main__':
    unittest.main()
