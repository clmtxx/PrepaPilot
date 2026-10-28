"""User consent, safe worker handoff, local scheduling and translated update UI."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QObject, Signal, QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from mpsi_desktop.i18n import set_language
from mpsi_desktop.update_panel import UpdateController, UpdatePanel

APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class FakeContext(QObject):
    notice = Signal(str)
    jobs_changed = Signal(int)
    theme_changed = Signal(str)

    def __init__(self, root):
        super().__init__()
        self.data_dir = Path(root)
        self.theme = 'light'
        self.db = SimpleNamespace(get_setting=lambda _key, default=None: default)
        self.busy = False
        self.pending = []

    def run_job(self, work, success, error=None, finished=None):
        self.busy = True
        self.pending.append((work, success, error, finished))
        self.jobs_changed.emit(len(self.pending))

    def complete(self):
        work, success, error, finished = self.pending.pop(0)
        try:
            result = work()
        except Exception as exc:
            if error:
                error(str(exc))
        else:
            success(result)
        self.busy = bool(self.pending)
        self.jobs_changed.emit(len(self.pending))
        if finished:
            finished()


class UpdateUITests(unittest.TestCase):
    def setUp(self):
        set_language('fr')
        self.temp = tempfile.TemporaryDirectory()
        self.ctx = FakeContext(self.temp.name)
        self.release = SimpleNamespace(version='2.19.0', release_url='https://github.com/study/PrepaPilot/releases/tag/v2.19.0')
        self.check = Mock(return_value=self.release)
        self.path = Path(self.temp.name) / 'PrepaPilot-2.19.0-Setup.exe'
        self.path.write_bytes(b'verified-by-engine')
        self.download = Mock(return_value=self.path)
        self.controls = []

    def tearDown(self):
        for panel in self.controls:
            panel.deleteLater()
        self.ctx.deleteLater()
        APP.processEvents()
        APP.sendPostedEvents(None, QEvent.DeferredDelete)
        self.temp.cleanup()
        set_language('fr')

    def controller(self, repository='study/PrepaPilot', **kwargs):
        return UpdateController(self.ctx, repository, check_func=self.check,
                                download_func=self.download, **kwargs)

    def panel(self, controller):
        result = UpdatePanel(self.ctx, controller)
        self.controls.append(result)
        return result

    def test_unpublished_version_does_not_start_network_work(self):
        controller = self.controller(None)
        panel = self.panel(controller)
        self.assertEqual(controller.state, 'unavailable')
        self.assertFalse(controller.due())
        self.assertFalse(controller.check())
        self.assertFalse(panel.check_button.isEnabled())
        self.assertFalse(panel.automatic.isEnabled())
        self.assertTrue(panel.install_button.isHidden())
        self.assertIn('pas encore disponibles', panel.status.text())
        self.check.assert_not_called()

    def test_check_only_notifies_and_requires_explicit_download(self):
        controller = self.controller()
        available, installs = [], []
        controller.available.connect(available.append)
        controller.install_requested.connect(installs.append)
        self.assertTrue(controller.check())
        self.assertFalse(controller.check())
        self.assertEqual(controller.state, 'checking')
        self.ctx.complete()
        self.assertEqual(controller.state, 'available')
        self.assertEqual(available, [self.release])
        self.assertEqual(installs, [])
        self.download.assert_not_called()

    def test_install_handoff_occurs_after_worker_busy_state_is_released(self):
        controller = self.controller()
        panel = self.panel(controller)
        controller.check()
        self.ctx.complete()
        installed = []
        controller.install_requested.connect(lambda path: installed.append((path, self.ctx.busy)))
        self.assertTrue(panel.install_button.isEnabled())
        panel.install_button.click()
        self.assertEqual(controller.state, 'downloading')
        self.assertFalse(panel.install_button.isEnabled())
        self.assertEqual(installed, [])
        self.assertFalse(controller.download_and_install())
        self.ctx.complete()
        self.assertEqual(installed, [(self.path, False)])
        self.assertEqual(controller.state, 'ready')
        self.assertEqual(controller.downloaded_sha256, hashlib.sha256(b'verified-by-engine').hexdigest())
        self.assertEqual(panel.install_button.text(), 'Installer la mise à jour')

    def test_retry_keeps_original_verified_fingerprint_for_final_installer_validation(self):
        controller = self.controller()
        controller.check()
        self.ctx.complete()
        controller.download_and_install()
        self.ctx.complete()
        checksum = controller.downloaded_sha256
        self.path.write_bytes(b'changed after verification')
        controller.download_and_install()
        self.assertEqual(controller.downloaded_sha256, checksum)
        self.assertNotEqual(checksum, hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.download.assert_called_once()

    def test_final_validation_rejection_offers_a_fresh_download(self):
        controller = self.controller()
        panel = self.panel(controller)
        controller.check()
        self.ctx.complete()
        controller.download_and_install()
        self.ctx.complete()
        self.assertTrue(controller.invalidate_download())
        self.assertIsNone(controller.downloaded_path)
        self.assertIsNone(controller.downloaded_sha256)
        self.assertEqual(panel.install_button.text(), 'Télécharger et installer')
        controller.download_and_install()
        self.ctx.complete()
        self.assertEqual(self.download.call_count, 2)

    def test_verification_failure_never_emits_installer(self):
        class VerificationError(Exception):
            code = 'checksum_mismatch'
        self.download.side_effect = VerificationError('technical details')
        controller = self.controller()
        controller.check()
        self.ctx.complete()
        installed = []
        controller.install_requested.connect(installed.append)
        controller.download_and_install()
        self.ctx.complete()
        self.assertEqual(controller.state, 'error')
        self.assertIsNone(controller.downloaded_path)
        self.assertIn('pas pu être vérifié', controller.status_text())
        self.assertNotIn('technical', controller.status_text())
        self.assertEqual(installed, [])

    def test_network_failure_is_limited_to_one_automatic_attempt_per_day(self):
        class Offline(Exception):
            code = 'network'
        self.check.side_effect = Offline()
        controller = self.controller()
        now = datetime(2026, 10, 24, 15, tzinfo=timezone.utc)
        with patch('mpsi_desktop.update_panel._utc_now', return_value=now):
            self.assertTrue(controller.check(automatic=True))
            self.ctx.complete()
        self.assertEqual(controller.state, 'error')
        self.assertFalse(controller.due(now + timedelta(hours=23)))
        reopened = self.controller()
        self.assertFalse(reopened.due(now + timedelta(hours=23)))
        self.assertTrue(reopened.due(now + timedelta(days=1)))
        reopened.set_automatic(False)
        self.assertFalse(self.controller().due(now + timedelta(days=2)))

    def test_manual_checks_remain_available_when_automatic_checks_are_disabled(self):
        controller = self.controller()
        panel = self.panel(controller)
        panel.automatic.setChecked(False)
        self.assertFalse(controller.automatic)
        self.assertTrue(panel.check_button.isEnabled())
        panel.check_button.click()
        self.ctx.complete()
        self.check.assert_called_once()

    def test_portable_version_links_to_release_and_never_downloads_installer(self):
        controller = self.controller(installed=False)
        panel = self.panel(controller)
        controller.check()
        self.ctx.complete()
        self.assertEqual(panel.install_button.text(), 'Voir la nouvelle version')
        self.assertIn('Version portable', panel.detail.text())
        with patch('mpsi_desktop.update_panel.QDesktopServices.openUrl', return_value=True) as open_url:
            panel.install_button.click()
        self.assertEqual(open_url.call_args.args[0].toString(), self.release.release_url)
        self.assertFalse(controller.download_and_install())
        self.download.assert_not_called()
        self.assertEqual(self.ctx.pending, [])

    def test_recreated_english_panel_preserves_controller_state_without_checking_again(self):
        controller = self.controller()
        first = self.panel(controller)
        controller.check()
        self.ctx.complete()
        first.deleteLater()
        self.controls.remove(first)
        APP.sendPostedEvents(None, QEvent.DeferredDelete)
        set_language('en')
        second = self.panel(controller)
        self.assertEqual(second.status.text(), 'PrépaPilot 2.19.0 is available.')
        self.assertEqual(second.install_button.text(), 'Download and install')
        self.assertIn('once a day', second.automatic.text())
        self.check.assert_called_once()
        self.download.assert_not_called()

    def test_current_version_and_download_progress_are_visible(self):
        self.check.return_value = None
        controller = self.controller(current_version='2.18.0')
        panel = self.panel(controller)
        controller.check()
        self.ctx.complete()
        self.assertEqual(panel.status.text(), 'PrépaPilot est à jour.')
        self.assertIn('2.18.0', panel.version.text())
        self.check.return_value = self.release
        controller.check()
        self.ctx.complete()

        def download(_release, _cache, progress):
            progress(20, 100)
            self.assertEqual(panel.progress.value(), 20)
            return self.path
        controller._download = download
        controller.download_and_install()
        self.ctx.complete()
        self.assertEqual(controller.progress_percent, 100)
        self.assertTrue(panel.progress.isHidden())

    def test_real_context_worker_survives_panel_deletion_and_releases_busy_before_install(self):
        from mpsi_desktop.context import AppContext
        context = AppContext(Path(self.temp.name) / 'real-worker')
        controller = UpdateController(context, 'study/PrepaPilot', check_func=self.check,
                                      download_func=self.download)
        installs = []
        controller.install_requested.connect(lambda path: installs.append((path, context.busy)))

        def finish_worker(complete=lambda: True):
            for _ in range(500):
                APP.processEvents()
                if not context.busy and complete():
                    return
                QTest.qWait(10)
            self.fail('The update worker did not finish.')

        try:
            controller.check()
            finish_worker()
            self.assertEqual(controller.state, 'available')
            panel = UpdatePanel(context, controller)
            controller.download_and_install()
            panel.deleteLater()
            APP.sendPostedEvents(None, QEvent.DeferredDelete)
            finish_worker(lambda: len(installs) == 1)
            APP.processEvents()
            self.assertEqual(installs, [(self.path, False)])
            self.assertEqual(controller.state, 'ready')
        finally:
            context.close()
            context.deleteLater()
            APP.sendPostedEvents(None, QEvent.DeferredDelete)


if __name__ == '__main__':
    unittest.main()
