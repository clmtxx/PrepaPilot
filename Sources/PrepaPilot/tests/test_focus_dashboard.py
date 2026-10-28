"""Exercise focus sessions through the real dashboard and journal lifecycle."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from mpsi_desktop.context import AppContext
from mpsi_desktop.focus_session import FocusSession
from mpsi_desktop.focus_dialogs import FocusSetupDialog, FocusReviewDialog
from mpsi_desktop.window import MainWindow

APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class FocusDashboardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.ctx = AppContext(Path(self.temporary.name) / 'data')
        self.ctx.db.set_setting('desktop_reduced_motion', True)
        self.errors = []
        self.previous_hook = sys.excepthook
        sys.excepthook = lambda kind, value, tb: self.errors.append(str(value))
        self.window = MainWindow(self.ctx, show_welcome=False)
        self.window.resize(1024, 680)
        self.window.show()
        APP.processEvents()
        self.home = self.window.pages['home']
        self.clock = [datetime.now().replace(hour=20, minute=0, second=0, microsecond=0) - timedelta(days=1), 1000.0]
        self.home.focus_session = FocusSession(self.ctx.db, now=lambda: self.clock[0], monotonic=lambda: self.clock[1])

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        APP.processEvents()
        self.ctx.close()
        self.temporary.cleanup()
        sys.excepthook = self.previous_hook
        self.assertEqual(self.errors, [])

    def advance(self, seconds):
        for _ in range(seconds):
            self.clock[0] += timedelta(seconds=1)
            self.clock[1] += 1
            self.home.tick()

    def test_start_pause_resume_and_confirm_add_only_work_periods(self):
        def setup(dialog):
            dialog.category.setCurrentIndex(dialog.category.findData('maths'))
            dialog.minutes.setValue(40)
            dialog.title.setText('Intégrales')
            dialog.start()
            return dialog.result()

        with patch.object(FocusSetupDialog, 'exec', new=setup):
            QTest.mouseClick(self.home.focus_button, Qt.MouseButton.LeftButton)
        self.assertEqual(self.home.focus_session.status, 'running')
        self.assertEqual(self.home.dial.total_seconds, 2400)
        self.advance(120)
        self.home.toggle_focus()
        self.assertEqual(self.home.focus_session.status, 'paused')
        self.assertFalse(self.home.timer.isActive())
        self.clock[0] += timedelta(minutes=10)
        self.clock[1] += 600
        self.home.toggle_focus()
        self.advance(120)
        self.assertEqual(self.ctx.db.list_time_entries(self.clock[0].date().isoformat(), self.clock[0].date().isoformat()), [])

        def save(dialog):
            self.assertEqual(dialog.table.rowCount(), 2)
            dialog.save()
            return dialog.result()

        with patch.object(FocusReviewDialog, 'exec', new=save):
            self.home.finish_focus()
        self.assertEqual(self.home.focus_session.status, 'saved')
        rows = self.ctx.db.list_time_entries(self.clock[0].date().isoformat(), self.clock[0].date().isoformat())
        self.assertEqual(len(rows), 2)
        self.assertEqual(sum(row['minutes'] for row in rows), 4)
        self.assertTrue(all(row['status'] == 'completed' and row['category'] == 'maths' for row in rows))

    def test_timer_finishes_with_review_and_never_writes_journal_automatically(self):
        self.home.focus_session.start('maths', minutes=1)
        self.home._sync_focus()
        self.advance(60)
        self.assertEqual(self.home.focus_session.status, 'review')
        self.assertEqual(self.home.focus_button.text(), 'Voir le bilan')
        self.assertEqual(self.home.dial.seconds, 0)
        self.assertFalse(self.home.timer.isActive())
        self.assertEqual(self.ctx.db._rows("SELECT COUNT(*) AS n FROM time_entries WHERE source='manual'")[0]['n'], 0)

    def test_clock_gap_pauses_and_reopening_preserves_only_observed_work(self):
        self.home.focus_session.start(None, minutes=25)
        self.home._sync_focus()
        self.advance(20)
        self.clock[0] += timedelta(hours=2)
        self.clock[1] += 7200
        self.home.tick()
        self.assertEqual(self.home.focus_session.status, 'paused')
        self.assertLessEqual(self.home.focus_session.elapsed_seconds, 20)
        self.assertIn('interrompue', self.home.focus_status.text())
        self.window.close()
        recovered = FocusSession(self.ctx.db)
        self.assertEqual(recovered.status, 'paused')
        self.assertLessEqual(recovered.elapsed_seconds, 20)

    def test_restoring_data_replaces_draft_without_writing_old_session(self):
        self.home.focus_session.start('maths', minutes=25)
        self.home._sync_focus()
        self.advance(2)
        self.ctx.db.set_setting('desktop_focus_session', None)
        previous = self.ctx.db._connection.total_changes
        self.window.data_replaced()
        self.assertEqual(self.home.focus_session.status, 'idle')
        self.assertFalse(self.home.timer.isActive())
        self.assertEqual(self.ctx.db._connection.total_changes, previous)
        self.assertIsNone(self.ctx.db.get_setting('desktop_focus_session'))

    def test_discard_is_explicit_and_cancel_keeps_session(self):
        self.home.focus_session.start('maths', minutes=25)
        self.home._sync_focus()
        with patch('mpsi_desktop.dashboard.confirm', return_value=False):
            self.home.reset_focus()
        self.assertEqual(self.home.focus_session.status, 'running')
        with patch('mpsi_desktop.dashboard.confirm', return_value=True):
            self.home.reset_focus()
        self.assertEqual(self.home.focus_session.status, 'idle')
        self.assertFalse(self.home.timer.isActive())

    def test_failed_close_keeps_window_open_and_draft_available(self):
        self.home.focus_session.start(None, minutes=25)
        self.home._sync_focus()
        with patch.object(self.home.focus_session, 'shutdown', side_effect=sqlite3.OperationalError('Readonly')):
            self.window.close()
        self.assertTrue(self.window.isVisible())
        self.assertTrue(self.home.focus_session.active)

    def test_checkpoint_failure_updates_pause_controls_and_keeps_work(self):
        self.home.focus_session.start('maths', minutes=25)
        self.home._sync_focus()
        self.advance(14)
        with patch.object(self.home.focus_session, '_write', side_effect=sqlite3.OperationalError('Disk full')):
            self.advance(1)
        self.assertEqual(self.home.focus_session.status, 'paused')
        self.assertEqual(self.home.focus_button.text(), 'Reprendre')
        self.assertIn('interrompue', self.home.focus_status.text())
        self.assertFalse(self.home.timer.isActive())
        self.assertEqual(self.home.focus_session.elapsed_seconds, 15)
        self.home.toggle_focus()
        self.assertEqual(self.home.focus_session.status, 'running')


if __name__ == '__main__':
    unittest.main()
